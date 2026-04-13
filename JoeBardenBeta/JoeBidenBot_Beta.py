# -*-  coding: utf-8 -*-

#VERSION 2.1
#REFER TO PATCHNOTES FOR MORE DETAIL ON UPDATES
#Copyright LPSC LLC.

import os
import asyncio
import functools
import itertools
import json
import math
import random
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Optional, cast
from datetime import datetime, timedelta

import yt_dlp
import discord
from discord.ext import commands
from dotenv import load_dotenv
from yt_dlp.utils import DownloadError
import google.genai as genai

intents = discord.Intents.all()
load_dotenv()

token = os.getenv("DISCORD_TOKEN")
_music_channel_raw = os.getenv("MUSIC_CHANNEL_ID", "").strip()
MUSIC_CHANNEL_ID = int(_music_channel_raw) if _music_channel_raw else None
_cookies_env = os.getenv("YTDL_COOKIES_PATH", "").strip()
_cookies_default = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cookies.txt"))
YTDL_COOKIES_PATH = _cookies_env if _cookies_env else _cookies_default if os.path.isfile(_cookies_default) else None
URL_RESOLVE_TIMEOUT_SECONDS = 8
BOT_START_TIME = time.monotonic()

def get_best_available_model(client) -> Optional[str]:
    """Dynamically discover and select the best available Gemini model.
    
    Prioritizes models in order of preference (cheapest/most efficient first):
    1. gemini-2.5-flash (current, efficient)
    2. gemini-1.5-flash (fallback)
    3. gemini-1.5-pro (higher quality)
    4. gemini-2.0-flash (if still available)
    
    Returns the first model that supports generateContent, or None if none found.
    """
    # Preferred models in order (cheapest/most efficient first)
    preferred_models = [
        "gemini-2.5-flash",
        "gemini-1.5-flash", 
        "gemini-1.5-pro",
        "gemini-2.0-flash"
    ]
    
    print("🔍 Discovering available Gemini models...")
    
    try:
        # Get list of available models
        models = client.models.list()
        available_models = []
        
        for model in models:
            if hasattr(model, 'supported_actions') and 'generateContent' in model.supported_actions:
                model_name = model.name.split('/')[-1]  # Extract model name from full path
                available_models.append(model_name)
                print(f"✅ Found model: {model_name}")
        
        print(f"📋 Total models supporting generateContent: {len(available_models)}")
        
        # Find the best available model from our preferred list
        for preferred in preferred_models:
            if preferred in available_models:
                print(f"🎯 Selected model: {preferred}")
                return preferred
        
        # If none of preferred models found, use first available
        if available_models:
            fallback = available_models[0]
            print(f"⚠️  Using fallback model: {fallback}")
            return fallback
            
        print("❌ No models found that support generateContent")
        return None
        
    except Exception as e:
        print(f"❌ Error discovering models: {e}")
        # Fallback to hardcoded model if discovery fails
        print("🔄 Using fallback model: gemini-2.5-flash")
        return "gemini-2.5-flash"

# Initialize Gemini AI
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    client = genai.Client(api_key=gemini_api_key)
    gemini_model = get_best_available_model(client)
    available_models = []  # Store for fallback retries
    
    # Store available models for runtime fallback
    try:
        models = client.models.list()
        for model in models:
            if hasattr(model, 'supported_actions') and 'generateContent' in model.supported_actions:
                model_name = model.name.split('/')[-1]
                available_models.append(model_name)
    except Exception:
        pass  # Fallback will work even if this fails
else:
    client = None
    gemini_model = None
    available_models = []
    print("Warning: GEMINI_API_KEY not found in .env file")

def generate_content_with_fallback(contents: str) -> str:
    """Generate content with automatic model fallback on failure.
    
    Tries the current model first, then falls back to other available models
    if the current one fails with 404 or similar errors.
    """
    if not client or not gemini_model:
        raise Exception("Gemini client not initialized")
    
    # Models to try in order (current first, then others)
    models_to_try = [gemini_model] + [m for m in available_models if m != gemini_model]
    
    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents
            )
            return response.text if hasattr(response, 'text') else str(response)
        except Exception as error:
            last_error = error
            error_msg = str(error).lower()
            
            # If it's a 404 or model not found error, try next model
            if any(keyword in error_msg for keyword in ['404', 'not found', 'no longer available']):
                print(f"⚠️  Model {model_name} failed: {error}")
                print(f"🔄 Trying next model...")
                continue
            else:
                # For other errors, don't retry - they might be rate limits or other issues
                raise error
    
    # If all models failed, raise the last error
    raise last_error or Exception("All available models failed")

# AI usage tracking
AI_USAGE = {}
DAILY_LIMIT = 1500  # Gemini free tier limit

MOOD_QUERIES = {
    "happy": [
        "ytsearch:Uptown Funk",
        "ytsearch:Happy Pharrell Williams",
        "ytsearch:Can't Stop The Feeling",
    ],
    "chill": [
        "ytsearch:Lofi hip hop beats",
        "ytsearch:Cigarettes After Sex Apocalypse",
        "ytsearch:Petit Biscuit Sunset Lover",
    ],
    "rage": [
        "ytsearch:DMX X Gon Give It To Ya",
        "ytsearch:Eminem Till I Collapse",
        "ytsearch:Killing In The Name",
    ],
    "focus": [
        "ytsearch:Deep Focus Music",
        "ytsearch:Chillstep mix",
        "ytsearch:Instrumental study music",
    ],
}

DJ_ROASTS = [
    "that queue choice was a federal offense.",
    "your aux privileges are under review.",
    "the dance floor filed a noise complaint.",
    "that pick had zero bipartisan support.",
    "the playlist called and asked for better representation.",
]


def format_clock(seconds: int) -> str:
    minutes, secs = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02}:{minutes:02}:{secs:02}"
    return f"{minutes:02}:{secs:02}"


def is_spotify_url(value: str) -> bool:
    return bool(re.search(r"https?://open\.spotify\.com/", value, re.IGNORECASE))


def is_apple_music_url(value: str) -> bool:
    return bool(re.search(r"https?://music\.apple\.com/", value, re.IGNORECASE))


def _fetch_oembed_metadata(url: str, endpoint: str) -> Optional[dict]:
    query = urllib.parse.urlencode({"url": url, "format": "json"})
    target = f"{endpoint}?{query}"
    req = urllib.request.Request(
        target,
        headers={"Accept": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=URL_RESOLVE_TIMEOUT_SECONDS) as response:
        payload = response.read().decode("utf-8", errors="replace")
        return json.loads(payload)


def resolve_music_link_to_query(value: str) -> tuple[str, Optional[str]]:
    raw = value.strip()

    if is_spotify_url(raw):
        try:
            # Spotify oEmbed is public and returns title + artist context.
            data = _fetch_oembed_metadata(raw, "https://open.spotify.com/oembed") or {}
        except Exception as exc:
            return "", f"Spotify link resolve failed: {exc}"

        title = (data.get("title") or "").strip()
        if not title:
            return "", "Spotify link resolve failed: no title metadata returned."
        return title, None

    if is_apple_music_url(raw):
        data = None
        last_error = None
        for endpoint in ("https://music.apple.com/oembed", "https://music.apple.com/us/oembed"):
            try:
                # Apple Music oEmbed endpoints provide enough metadata for a ytsearch query.
                data = _fetch_oembed_metadata(raw, endpoint) or {}
                break
            except Exception as exc:
                last_error = exc

        if data is None:
            return "", f"Apple Music link resolve failed: {last_error}"

        title = (data.get("title") or "").strip()
        author = (data.get("author_name") or "").strip()
        if not title and not author:
            return "", "Apple Music link resolve failed: no usable metadata returned."
        query = f"{author} - {title}".strip(" -")
        return query, None

    return raw, None


def fetch_lyrics(query: str) -> tuple[Optional[str], Optional[str]]:
    value = query.strip()
    if " - " not in value:
        return None, "Use format: artist - title (example: Queen - Bohemian Rhapsody)."

    artist, title = value.split(" - ", 1)
    artist = artist.strip()
    title = title.strip()
    if not artist or not title:
        return None, "Use format: artist - title."

    endpoint = (
        "https://api.lyrics.ovh/v1/"
        f"{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"
    )

    req = urllib.request.Request(
        endpoint,
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=URL_RESOLVE_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return None, f"Lyrics lookup failed: {exc}"

    lyrics = (payload.get("lyrics") or "").strip()
    if not lyrics:
        return None, "No lyrics found for that song."
    return lyrics, None


def music_channel_only():
    async def predicate(ctx: commands.Context):
        if MUSIC_CHANNEL_ID is not None and ctx.channel.id != MUSIC_CHANNEL_ID:
            await ctx.send(
                f"❌ Use music commands in <#{MUSIC_CHANNEL_ID}> only."
            )
            return False
        return True
    return commands.check(predicate)

class VoiceError(Exception):
    pass


class YTDLError(Exception):
    pass


class YTDLSource(discord.PCMVolumeTransformer):
    YTDL_OPTIONS: dict[str, Any] = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': 'ytsearch',
        # Impersonate a real browser to reduce bot detection
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
        # Small random delay between requests to avoid machine-speed fingerprinting
        'sleep_interval': 1,
        'max_sleep_interval': 3,
        'sleep_interval_requests': 1,
        # Prevent hung connections
        'socket_timeout': 15,
        # Bypass geographic access checks
        'geo_bypass': True,
        **({'cookiefile': YTDL_COOKIES_PATH} if YTDL_COOKIES_PATH else {}),
    }



    FFMPEG_OPTIONS: dict[str, Any] = {
        'executable': 'ffmpeg',
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -b:a 192k'
    }



    ytdl = yt_dlp.YoutubeDL(cast(Any, YTDL_OPTIONS))

    def __init__(self, ctx: commands.Context, source: discord.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data

        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        date = data.get('upload_date')
        self.upload_date = "unknown"
        if date and len(date) == 8:
            self.upload_date = f"{date[6:8]}.{date[4:6]}.{date[0:4]}"
        self.title = data.get('title')
        self.thumbnail = data.get('thumbnail')
        self.description = data.get('description')
        self.duration = self.parse_duration(int(data.get('duration') or 0))
        self.duration_seconds = int(data.get('duration') or 0)
        self.tags = data.get('tags')
        self.url = data.get('webpage_url')
        self.views = data.get('view_count')
        self.likes = data.get('like_count')
        self.dislikes = data.get('dislike_count')
        self.stream_url = data.get('url')

    def __str__(self):
        return '**{0.title}** by **{0.uploader}**'.format(self)

    @classmethod
    async def create_source(
        cls,
        ctx: commands.Context,
        search: str,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        volume: float = 0.5,
    ):
        loop = loop or asyncio.get_running_loop()
        
        partial = functools.partial(
            cls.ytdl.extract_info,
            search,
            download=False
        )
        try:
            raw_data: Any = await loop.run_in_executor(None, partial)
        except DownloadError as exc:
            raise YTDLError(f"yt-dlp failed to fetch media: {exc}") from exc
        except Exception as exc:
            raise YTDLError(f"Unexpected extractor failure: {exc}") from exc

        if raw_data is None:
            raise YTDLError(f"Couldn't find anything that matches `{search}`")

        if isinstance(raw_data, dict) and 'entries' in raw_data:
            entries = raw_data.get('entries')
            if isinstance(entries, list):
                raw_data = None
                for item in entries:
                    if isinstance(item, dict):
                        raw_data = item
                        break
            else:
                raw_data = None

        if not isinstance(raw_data, dict):
            raise YTDLError(f"Couldn't find anything that matches `{search}`")

        data = cast(dict[str, Any], raw_data)

        stream_url = data.get('url')
        if not stream_url:
            raise YTDLError("Extractor returned no playable stream URL.")

        try:
            ffmpeg_source = discord.FFmpegPCMAudio(stream_url, **cls.FFMPEG_OPTIONS)
        except FileNotFoundError as exc:
            raise YTDLError("ffmpeg binary not found. Install ffmpeg and ensure it is in PATH.") from exc
        except discord.ClientException as exc:
            raise YTDLError(f"ffmpeg initialization failed: {exc}") from exc

        return cls(ctx, ffmpeg_source, data=data, volume=volume)


    @staticmethod
    def parse_duration(duration_seconds: int):
        if duration_seconds <= 0:
            return "Live/Unknown"

        minutes, seconds = divmod(duration_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        segments = []
        if days > 0:
            segments.append('{} days'.format(days))
        if hours > 0:
            segments.append('{} hours'.format(hours))
        if minutes > 0:
            segments.append('{} minutes'.format(minutes))
        if seconds > 0:
            segments.append('{} seconds'.format(seconds))

        return ', '.join(segments)


class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        embed = (discord.Embed(title='Now playing',
                               description='```css\n{0.source.title}\n```'.format(self),
                               color=discord.Color.blurple())
                 .add_field(name='Duration', value=self.source.duration)
                 .add_field(name='Requested by', value=self.requester.mention)
                 .add_field(name='Uploader', value='[{0.source.uploader}]({0.source.uploader_url})'.format(self))
                 .add_field(name='URL', value='[Click]({0.source.url})'.format(self))
                 .set_thumbnail(url=self.source.thumbnail))

        return embed


class SongQueue(asyncio.Queue):
    def _items(self):
        return cast(Any, getattr(self, "_queue"))

    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._items(), item.start, item.stop, item.step))
        else:
            return self._items()[item]

    def __iter__(self):
        return iter(self._items())

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._items().clear()

    def shuffle(self):
        random.shuffle(self._items())

    def remove(self, index: int):
        del self._items()[index]

    def put_front(self, item: Song):
        self._items().appendleft(item)


class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx

        self.current: Optional[Song] = None
        self.voice: Optional[discord.VoiceClient] = None
        self.next = asyncio.Event()
        self.songs = SongQueue()

        self._loop = False
        self._volume = 0.5
        self.skip_votes = set()
        self._playback_error: Optional[str] = None
        self.current_started_at: Optional[float] = None
        self.history: list[Song] = []
        self.history_limit = 20
        self.vote_mode = False
        self.nightcore = False
        self.slowmo = False
        self.vaporwave = False
        self.reverse = False
        self.bass = False
        self.lofi = False
        self.echo = False
        self.tremolo = False
        self.fadein = False
        self.songs_played = 0
        self._ffmpeg_process: Optional[asyncio.subprocess.Process] = None
        self._cleanup_lock = asyncio.Lock()

        self.audio_player = asyncio.create_task(self.audio_player_task())

    def __del__(self):
        audio_player = getattr(self, "audio_player", None)
        if audio_player:
            audio_player.cancel()
        # Cleanup ffmpeg process if it exists
        if hasattr(self, '_ffmpeg_process') and self._ffmpeg_process:
            try:
                self._ffmpeg_process.terminate()
                self._ffmpeg_process.wait(timeout=5)
            except:
                try:
                    self._ffmpeg_process.kill()
                except:
                    pass

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value

    @property
    def is_playing(self):
        return bool(self.voice and self.current)

    async def _send_player_error(self, channel, message: str):
        try:
            await channel.send(f"❌ {message}")
        except Exception:
            pass

    async def audio_player_task(self):
        while True:
            self.next.clear()

            if not self.loop:
                try:
                    async with asyncio.timeout(180):  # 3 minutes
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:
                    asyncio.create_task(self.stop())
                    return

            if self.current is None:
                continue

            self.skip_votes.clear()
            channel = self.current.source.channel
            source_metadata = self.current.source

            # Fix A: Re-resolve a fresh stream URL at play time to avoid stale/expired YouTube URLs.
            stream_url = None
            webpage_url = source_metadata.url
            if webpage_url:
                try:
                    loop = asyncio.get_running_loop()
                    partial = functools.partial(
                        YTDLSource.ytdl.extract_info,
                        webpage_url,
                        download=False
                    )
                    fresh_data = await loop.run_in_executor(None, partial)
                    if isinstance(fresh_data, dict) and 'entries' in fresh_data:
                        entries = fresh_data.get('entries') or []
                        fresh_data = next((e for e in entries if isinstance(e, dict)), None)
                    if isinstance(fresh_data, dict):
                        stream_url = fresh_data.get('url')
                except Exception as resolve_exc:
                    print(f"[Beta] Stream URL re-resolve failed, falling back to cached URL: {resolve_exc}")

            if not stream_url:
                stream_url = source_metadata.stream_url or source_metadata.data.get('url')
            if not stream_url:
                await self._send_player_error(channel, "No playable stream URL was returned for this track.")
                continue

            # Fix B: Use a flag so exception paths don't skip self.next.wait(), preventing queue desync.
            played = False
            try:
                # Re-create FFmpeg source at play time to reduce stale/expired stream issues.
                ffmpeg_options = dict(YTDLSource.FFMPEG_OPTIONS)
                
                # Apply audio effects
                if self.nightcore:
                    ffmpeg_options["options"] = "-vn -b:a 192k -af asetrate=48000*1.15,aresample=48000"
                elif self.slowmo:
                    ffmpeg_options["options"] = "-vn -b:a 192k -af atempo=0.85"
                elif self.vaporwave:
                    ffmpeg_options["options"] = "-vn -b:a 192k -af asetrate=48000*0.8,aresample=48000,aecho=0.8:0.9:1000|1800:0.9|0.9"
                elif self.reverse:
                    ffmpeg_options["options"] = "-vn -b:a 192k -af areverse"
                elif self.bass:
                    ffmpeg_options["options"] = "-vn -b:a 192k -af bass=g=15"
                elif self.lofi:
                    ffmpeg_options["options"] = "-vn -b:a 192k -af acrusher=level_in=1:level_out=1:bits=8:mode=log"
                elif self.echo:
                    ffmpeg_options["options"] = "-vn -b:a 192k -af aecho=0.8:0.5:1000|2000|3000:0.5|0.3|0.2"
                elif self.tremolo:
                    ffmpeg_options["options"] = "-vn -b:a 192k -af apulsator=mode=sine:hz=2"
                elif self.fadein:
                    ffmpeg_options["options"] = "-vn -b:a 192k -af afade=t=in:st=0:d=3"

                if not self.voice:
                    await self._send_player_error(channel, "Voice connection dropped before playback started.")
                else:
                    source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_options)
                    playback_source = discord.PCMVolumeTransformer(source, volume=self._volume)

                    # Store the ffmpeg process reference for cleanup
                    self._ffmpeg_process = getattr(source, '_process', None)

                    self.voice.play(playback_source, after=self.play_next_song)
                    self.current_started_at = time.monotonic()
                    self.songs_played += 1
                    self.history.append(self.current)
                    if len(self.history) > self.history_limit:
                        self.history.pop(0)
                    await channel.send(embed=self.current.create_embed())
                    played = True

            except FileNotFoundError:
                await self._send_player_error(channel, "ffmpeg is not installed or not in PATH.")
            except discord.ClientException as exc:
                await self._send_player_error(channel, f"Audio playback failed: {exc}")
            except Exception as exc:
                await self._send_player_error(channel, f"Unexpected playback failure: {exc}")

            if played:
                await self.next.wait()
                if self._playback_error:
                    await self._send_player_error(channel, f"Track playback error: {self._playback_error}")
                    self._playback_error = None




    def play_next_song(self, error=None):
        self._playback_error = str(error) if error else None
        
        # Cleanup ffmpeg process
        if hasattr(self, '_ffmpeg_process') and self._ffmpeg_process:
            try:
                self._ffmpeg_process.terminate()
            except:
                try:
                    self._ffmpeg_process.kill()
                except:
                    pass
            finally:
                self._ffmpeg_process = None
                
        self.bot.loop.call_soon_threadsafe(self.next.set)

    def skip(self):
        self.skip_votes.clear()

        if self.is_playing and self.voice:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()
        self.current_started_at = None

        async with self._cleanup_lock:
            # Cleanup any existing ffmpeg process
            if self._ffmpeg_process:
                try:
                    self._ffmpeg_process.terminate()
                    try:
                        await asyncio.wait_for(self._ffmpeg_process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        self._ffmpeg_process.kill()
                        await self._ffmpeg_process.wait()
                except Exception:
                    pass
                finally:
                    self._ffmpeg_process = None

        if self.voice:
            await self.voice.disconnect()
            self.voice = None


class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}
        self.playlists_path = os.path.join(os.path.dirname(__file__), "playlists.json")
        self.ai_conversations = {}  # Store conversation history

    def _read_playlists(self) -> dict[str, dict[str, list[str]]]:
        if not os.path.exists(self.playlists_path):
            return {}
        try:
            with open(self.playlists_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict):
                return cast(dict[str, dict[str, list[str]]], data)
        except Exception:
            pass
        return {}

    def _write_playlists(self, data: dict[str, dict[str, list[str]]]) -> None:
        with open(self.playlists_path, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state
        return state

    async def cog_unload(self):
        for state in self.voice_states.values():
            try:
                await state.stop()
            except Exception:
                pass  # Ignore errors during shutdown
        self.voice_states.clear()

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage('This command can\'t be used in DM channels.')

        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        await ctx.send('An error occurred: {}'.format(str(error)))

    @commands.command(name='help')
    async def _help(self, ctx: commands.Context):
        """Show an embedded command menu.

        Usage: $help
        """
        prefix = "#"
        embed = (
            discord.Embed(
                title="⚠️ BETA BUILD — Joe Barden Bot Command Center",
                description=(
                    "```\n"
                    "██████╗ ███████╗████████╗ █████╗ \n"
                    "██╔══██╗██╔════╝╚══██╔══╝██╔══██╗\n"
                    "██████╔╝█████╗     ██║   ███████║\n"
                    "██╔══██╗██╔══╝     ██║   ██╔══██║\n"
                    "██████╔╝███████╗   ██║   ██║  ██║\n"
                    "╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═╝\n"
                    "```\n"
                    "⚠️ **This is a BETA version. Expect bugs. AI features are disabled.**\n"
                    "Use the commands below in the configured music channel."
                ),
                color=discord.Color.orange(),
            )
            .add_field(
                name="Music",
                value=(
                    f"`{prefix}play <query|url>` Queue a track\n"
                    f"`{prefix}join` Join your voice channel\n"
                    f"`{prefix}leave` Disconnect and clear queue\n"
                    f"`{prefix}queue [page]` Show queue pages\n"
                    f"`{prefix}now` Show current song\n"
                    f"`{prefix}nowbar` Show progress bar\n"
                    f"`{prefix}history` Show recently played"
                ),
                inline=False,
            )
            .add_field(
                name="Playback Controls",
                value=(
                    f"`{prefix}pause` Pause (admin)\n"
                    f"`{prefix}resume` Resume (admin)\n"
                    f"`{prefix}stop` Stop and clear (admin)\n"
                    f"`{prefix}skip` Skip current track\n"
                    f"`{prefix}replay` Replay current track\n"
                    f"`{prefix}loop` Toggle loop\n"
                    f"`{prefix}volume <0-100>` Set volume"
                ),
                inline=False,
            )
            .add_field(
                name="🎛️ Audio Effects",
                value=(
                    f"`{prefix}effects` Show all effects\n"
                    f"`{prefix}nightcore on|off` Speed up music\n"
                    f"`{prefix}slowmo on|off` Slow down music\n"
                    f"`{prefix}vaporwave on|off` Aesthetic effect\n"
                    f"`{prefix}reverse on|off` Play backwards\n"
                    f"`{prefix}bass on|off` Heavy bass boost\n"
                    f"`{prefix}lofi on|off` Crunchy vintage sound\n"
                    f"`{prefix}echo on|off` Triple echo chamber\n"
                    f"`{prefix}tremolo on|off` Pulsing effect\n"
                    f"`{prefix}fadein on|off` Smooth fade-in"
                ),
                inline=False,
            )
            .add_field(
                name="Playlists and Discovery",
                value=(
                    f"`{prefix}playlist save <name>` Save queue\n"
                    f"`{prefix}playlist load <name>` Load saved playlist\n"
                    f"`{prefix}playlist list` List saved playlists\n"
                    f"`{prefix}mood <happy|chill|rage|focus>` Queue mood set\n"
                    f"`{prefix}lyrics <artist - title>` Fetch lyrics"
                ),
                inline=False,
            )
            .add_field(
                name="Community and Utility",
                value=(
                    f"`{prefix}usage` Simple how-to guide\n"
                    f"`{prefix}votemode on|off` Toggle vote skip mode\n"
                    f"`{prefix}stats` Show bot stats\n"
                    f"`{prefix}roastdj [@user]` Roast the DJ\n"
                    f"`{prefix}shuffle` Shuffle queue\n"
                    f"`{prefix}remove <index>` Remove queued track\n"
                    f"`{prefix}patchnotes` View changelog"
                ),
                inline=False,
            )
            .set_footer(text="⚠️ BETA BUILD — AI features are disabled in this version.")
        )

        await ctx.send(embed=embed)

    @commands.command(name='join', invoke_without_subcommand=True)
    @music_channel_only()
    async def _join(self, ctx: commands.Context):
        """Join your current voice channel.

        Usage: $join
        """

        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError('You are not connected to a voice channel.')

        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='summon')
    @music_channel_only()
    @commands.has_permissions(manage_guild=True)
    async def _summon(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        """Move the bot to a specific voice channel (admin only).

        Usage: $summon #voice-channel
        """

        if not channel and not ctx.author.voice:
            raise VoiceError('YOU ARENT CONNECTED TO SHIT DUMBASS')

        destination = channel or ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='leave', aliases=['disconnect'])
    @commands.has_permissions(manage_guild=True)
    async def _leave(self, ctx: commands.Context):
        """Stop playback, clear queue, and disconnect (admin only).

        Usage: $leave
        Alias: $disconnect
        """

        if not ctx.voice_state.voice:
            return await ctx.send('Not connected to any voice channel.')

        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]

    @commands.command(name='volume')
    async def _volume(self, ctx: commands.Context, *, volume: int):
        """Set playback volume from 0 to 100.

        Usage: $volume 60
        """
        if not ctx.voice_state.is_playing:
            return await ctx.send('You are not listening to anything.')

        if volume < 0 or volume > 100:
            return await ctx.send('Volume must be between 0 and 100.')

        ctx.voice_state.volume = volume / 100
        voice_source = getattr(ctx.voice_state.voice, "source", None)
        if voice_source and hasattr(voice_source, "volume"):
            voice_source.volume = ctx.voice_state.volume
        await ctx.send(f'Volume of the player set to {volume}%')


    @commands.command(name='now', aliases=['current', 'playing'])
    async def _now(self, ctx: commands.Context):
        """Show the currently playing track.

        Usage: $now
        Aliases: $current, $playing
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send('There is no song currently playing.')

        await ctx.send(embed=ctx.voice_state.current.create_embed())

    @commands.command(name='pause')
    @commands.has_permissions(manage_guild=True)
    async def _pause(self, ctx: commands.Context):
        """Pause the current track (admin only).

        Usage: $pause
        """

        if ctx.voice_state.voice and (ctx.voice_state.is_playing or ctx.voice_state.voice.is_playing()):
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction('⏯️')

    @commands.command(name='resume')
    @commands.has_permissions(manage_guild=True)
    async def _resume(self, ctx: commands.Context):
        """Resume a paused track (admin only).

        Usage: $resume
        """

        if ctx.voice_state.voice and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction('▶️')

    @commands.command(name='stop')
    @commands.has_permissions(manage_guild=True)
    async def _stop(self, ctx: commands.Context):
        """Stop playback and clear queued tracks (admin only).

        Usage: $stop
        """

        ctx.voice_state.songs.clear()

        if ctx.voice_state.is_playing:
            ctx.voice_state.voice.stop()
            await ctx.message.add_reaction('🛑')

    @commands.command(name='skip')
    async def _skip(self, ctx: commands.Context):
        """Skip the current song (vote-based when vote mode is enabled).

        Usage: $skip
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send('NO. MUSIC. PLAYING. WHAT ARE YOU DOING!?')

        voter = ctx.message.author
        if voter == ctx.voice_state.current.requester:
            await ctx.message.add_reaction('⏭')
            ctx.voice_state.skip()
            return

        if not ctx.voice_state.vote_mode:
            await ctx.message.add_reaction('⏭')
            ctx.voice_state.skip()
            return

        if voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            listeners = []
            if ctx.voice_state.voice and ctx.voice_state.voice.channel:
                listeners = [m for m in ctx.voice_state.voice.channel.members if not m.bot]
            required_votes = max(2, math.ceil(len(listeners) / 2)) if listeners else 2

            if total_votes >= required_votes:
                await ctx.message.add_reaction('⏭')
                ctx.voice_state.skip()
            else:
                await ctx.send('Skip vote added, currently at **{}/{}**'.format(total_votes, required_votes))

        else:
            await ctx.send('You have already voted to skip this song.')

    @commands.command(name='queue')
    async def _queue(self, ctx: commands.Context, *, page: int = 1):
        """Show the song queue.

        Usage: $queue
        Usage: $queue 2
        Notes: 10 tracks per page.
        """

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)
        if page < 1 or page > pages:
            return await ctx.send(f'Page must be between 1 and {pages}.')

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ''
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):
            queue += '`{0}.` [**{1.source.title}**]({1.source.url})\n'.format(i + 1, song)

        embed = (discord.Embed(description='**{} tracks:**\n\n{}'.format(len(ctx.voice_state.songs), queue))
                 .set_footer(text='Viewing page {}/{}'.format(page, pages)))
        await ctx.send(embed=embed)

    @commands.command(name='shuffle')
    async def _shuffle(self, ctx: commands.Context):
        """Shuffle the current queue.

        Usage: $shuffle
        """

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')

        ctx.voice_state.songs.shuffle()
        await ctx.message.add_reaction('🔀')

    @commands.command(name='remove')
    async def _remove(self, ctx: commands.Context, index: int):
        """Remove one queued song by position.

        Usage: $remove 3
        """

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('Empty queue.')
        if index < 1 or index > len(ctx.voice_state.songs):
            return await ctx.send(f'Index must be between 1 and {len(ctx.voice_state.songs)}.')

        ctx.voice_state.songs.remove(index - 1)
        await ctx.message.add_reaction('💥')

    @commands.command(name='loop')
    async def _loop(self, ctx: commands.Context):
        """Toggle loop for the current track.

        Usage: $loop
        """

        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing being played at the moment.')

        # Inverse boolean value to loop and unloop.
        ctx.voice_state.loop = not ctx.voice_state.loop
        await ctx.message.add_reaction('➰')

    @commands.command(name='patchnotes', aliases=['bugs', 'patch'])
    async def _patchnotes(self, ctx: commands.Context):
        """Show the latest bot patch notes.

        Usage: $patchnotes
        Aliases: $bugs, $patch
        """
        try:
            patchnotes_path = os.path.join(os.path.dirname(__file__), "patchnotes.txt")
            with open(patchnotes_path, encoding="utf-8") as patchnotes:
                await ctx.send(patchnotes.read())
        except FileNotFoundError:
            await ctx.send("patchnotes.txt was not found.")

    @commands.command(name='play')
    @music_channel_only()
    async def _play(self, ctx: commands.Context, *, search: str):
        """Play a track from a query or URL.

        Usage: $play never gonna give you up
        Usage: $play <youtube-url>
        Usage: $play <spotify-or-apple-music-url>
        Notes: Spotify/Apple links are resolved to a search query.
        """
        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)
        elif ctx.author.voice and ctx.voice_state.voice.channel != ctx.author.voice.channel:
            raise commands.CommandError('Im already in a voice channel. Even Im not that senile.')

        resolved_search, resolve_error = await asyncio.to_thread(resolve_music_link_to_query, search)
        if resolve_error:
            await ctx.send(f"❌ {resolve_error}")
            return

        if resolved_search != search:
            await ctx.send(f"🔎 Resolved link to search query: {resolved_search}")

        async with ctx.typing():
            try:
                source = await YTDLSource.create_source(
                    ctx,
                    resolved_search,
                    loop=asyncio.get_running_loop(),
                    volume=ctx.voice_state.volume,
                )
            except YTDLError as exc:
                await ctx.send(f"❌ Unable to queue track: {exc}")
                return
            except Exception as exc:
                await ctx.send(f"❌ Unexpected queue error: {exc}")
                return

            song = Song(source)
            await ctx.voice_state.songs.put(song)
            await ctx.send(f'Enqueued {str(source)}')

    @commands.command(name='lyrics')
    async def _lyrics(self, ctx: commands.Context, *, query: str = ""):
        """Fetch song lyrics by artist and title.

        Usage: $lyrics Queen - Bohemian Rhapsody
        Notes: If omitted, tries current track title.
        """
        lookup_query = query.strip()
        if not lookup_query:
            if not ctx.voice_state.current:
                return await ctx.send("Provide a song as: artist - title, or play a song first.")
            lookup_query = ctx.voice_state.current.source.title or ""

        lyrics, error = await asyncio.to_thread(fetch_lyrics, lookup_query)
        if error:
            return await ctx.send(f"❌ {error}")
        if not lyrics:
            return await ctx.send("❌ No lyrics were returned.")

        chunks = [lyrics[i:i + 1900] for i in range(0, len(lyrics), 1900)]
        for idx, chunk in enumerate(chunks, start=1):
            header = f"Lyrics ({idx}/{len(chunks)})\n" if len(chunks) > 1 else "Lyrics\n"
            await ctx.send(f"```\n{header}{chunk}\n```")

    @commands.command(name='nightcore')
    async def _nightcore(self, ctx: commands.Context, mode: str):
        """Toggle nightcore playback effect for upcoming tracks.

        Usage: $nightcore on
        Usage: $nightcore off
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $nightcore on|off")
        
        # Reset all other effects
        ctx.voice_state.slowmo = False
        ctx.voice_state.vaporwave = False
        ctx.voice_state.reverse = False
                
        ctx.voice_state.nightcore = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.nightcore else "disabled"
        await ctx.send(f"🎵 Nightcore is now {state}!")

    @commands.command(name='slowmo')
    async def _slowmo(self, ctx: commands.Context, mode: str):
        """Toggle slow-motion playback effect for upcoming tracks.

        Usage: $slowmo on
        Usage: $slowmo off
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $slowmo on|off")
        
        # Reset all other effects
        ctx.voice_state.nightcore = False
        ctx.voice_state.vaporwave = False
        ctx.voice_state.reverse = False
                
        ctx.voice_state.slowmo = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.slowmo else "disabled"
        await ctx.send(f"🐌 Slow-mo is now {state}!")

    @commands.command(name='vaporwave')
    async def _vaporwave(self, ctx: commands.Context, mode: str):
        """Toggle vaporwave aesthetic effect for upcoming tracks.

        Usage: $vaporwave on
        Usage: $vaporwave off
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $vaporwave on|off")
        
        # Reset all other effects
        ctx.voice_state.nightcore = False
        ctx.voice_state.slowmo = False
        ctx.voice_state.reverse = False
                
        ctx.voice_state.vaporwave = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.vaporwave else "disabled"
        await ctx.send(f"🌊 Vaporwave is now {state}!")

    @commands.command(name='reverse')
    async def _reverse(self, ctx: commands.Context, mode: str):
        """Toggle reverse playback effect for upcoming tracks.

        Usage: $reverse on
        Usage: $reverse off
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $reverse on|off")
        
        # Reset all other effects
        ctx.voice_state.slowmo = False
        ctx.voice_state.vaporwave = False
        ctx.voice_state.reverse = False
        ctx.voice_state.bass = False
        ctx.voice_state.lofi = False
        ctx.voice_state.echo = False
        ctx.voice_state.tremolo = False
        ctx.voice_state.fadein = False
        
        ctx.voice_state.reverse = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.reverse else "disabled"
        await ctx.send(f"⏪ Reverse is now {state}!")

    @commands.command(name='bass')
    async def _bass(self, ctx: commands.Context, mode: str):
        """Toggle bass boost effect for upcoming tracks.

        Usage: $bass on
        Usage: $bass off
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $bass on|off")
        
        # Reset all other effects
        ctx.voice_state.nightcore = False
        ctx.voice_state.slowmo = False
        ctx.voice_state.vaporwave = False
        ctx.voice_state.reverse = False
        ctx.voice_state.bass = False
        ctx.voice_state.lofi = False
        ctx.voice_state.echo = False
        ctx.voice_state.tremolo = False
        ctx.voice_state.fadein = False
        
        ctx.voice_state.bass = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.bass else "disabled"
        await ctx.send(f"🔊 Bass boost is now {state}!")

    @commands.command(name='lofi')
    async def _lofi(self, ctx: commands.Context, mode: str):
        """Toggle lo-fi effect for upcoming tracks.

        Usage: $lofi on
        Usage: $lofi off
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $lofi on|off")
        
        # Reset all other effects
        ctx.voice_state.slowmo = False
        ctx.voice_state.vaporwave = False
        ctx.voice_state.reverse = False
        ctx.voice_state.bass = False
        ctx.voice_state.lofi = False
        ctx.voice_state.echo = False
        ctx.voice_state.tremolo = False
        ctx.voice_state.fadein = False
        ctx.voice_state.reverse = False
        ctx.voice_state.bass = False
        ctx.voice_state.echo = False
        ctx.voice_state.tremolo = False
        ctx.voice_state.fadein = False
        
        ctx.voice_state.lofi = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.lofi else "disabled"
        await ctx.send(f"📻 Lo-fi is now {state}!")

    @commands.command(name='echo')
    async def _echo(self, ctx: commands.Context, mode: str):
        """Toggle echo chamber effect for upcoming tracks.

        Usage: $echo on
        Usage: $echo off
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $echo on|off")
        
        # Reset all other effects
        ctx.voice_state.slowmo = False
        ctx.voice_state.vaporwave = False
        ctx.voice_state.reverse = False
        ctx.voice_state.bass = False
        ctx.voice_state.lofi = False
        ctx.voice_state.echo = False
        ctx.voice_state.tremolo = False
        ctx.voice_state.fadein = False
        ctx.voice_state.reverse = False
        ctx.voice_state.bass = False
        ctx.voice_state.lofi = False
        ctx.voice_state.tremolo = False
        ctx.voice_state.fadein = False
        
        ctx.voice_state.echo = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.echo else "disabled"
        await ctx.send(f"🔊 Echo is now {state}!")

    @commands.command(name='tremolo')
    async def _tremolo(self, ctx: commands.Context, mode: str):
        """Toggle tremolo/pulsing effect for upcoming tracks.

        Usage: $tremolo on
        Usage: $tremolo off
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $tremolo on|off")
        
        # Reset all other effects
        ctx.voice_state.slowmo = False
        ctx.voice_state.vaporwave = False
        ctx.voice_state.reverse = False
        ctx.voice_state.bass = False
        ctx.voice_state.lofi = False
        ctx.voice_state.echo = False
        ctx.voice_state.tremolo = False
        ctx.voice_state.fadein = False
        ctx.voice_state.reverse = False
        ctx.voice_state.bass = False
        ctx.voice_state.lofi = False
        ctx.voice_state.echo = False
        ctx.voice_state.fadein = False
        
        ctx.voice_state.tremolo = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.tremolo else "disabled"
        await ctx.send(f"🌊 Tremolo is now {state}!")

    @commands.command(name='fadein')
    async def _fadein(self, ctx: commands.Context, mode: str):
        """Toggle fade-in effect for upcoming tracks.

        Usage: $fadein on
        Usage: $fadein off
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $fadein on|off")
        
        # Reset all other effects
        ctx.voice_state.slowmo = False
        ctx.voice_state.vaporwave = False
        ctx.voice_state.reverse = False
        ctx.voice_state.bass = False
        ctx.voice_state.lofi = False
        ctx.voice_state.echo = False
        ctx.voice_state.tremolo = False
        ctx.voice_state.fadein = False
        ctx.voice_state.reverse = False
        ctx.voice_state.bass = False
        ctx.voice_state.lofi = False
        ctx.voice_state.echo = False
        ctx.voice_state.tremolo = False
        
        ctx.voice_state.fadein = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.fadein else "disabled"
        await ctx.send(f"🎵 Fade-in is now {state}!")

    
    @commands.command(name='effects')
    async def _effects(self, ctx: commands.Context):
        """Show available audio effects and current status.

        Usage: $effects
        """
        embed = discord.Embed(
            title="🎛️ Audio Effects Studio",
            description="Fun audio effects to spice up your music!",
            color=discord.Color.purple()
        )
        
        # Current status
        active_effects = []
        if ctx.voice_state.nightcore:
            active_effects.append("🎵 Nightcore (sped up)")
        if ctx.voice_state.slowmo:
            active_effects.append("🐌 Slow-mo (slowed down)")
        if ctx.voice_state.vaporwave:
            active_effects.append("🌊 Vaporwave (aesthetic)")
        if ctx.voice_state.reverse:
            active_effects.append("⏪ Reverse (backwards)")
        if ctx.voice_state.bass:
            active_effects.append("🔊 Bass Boost (heavy bass)")
        if ctx.voice_state.lofi:
            active_effects.append("📻 Lo-Fi (crunchy vintage)")
        if ctx.voice_state.echo:
            active_effects.append("🔊 Echo Chamber (triple echo)")
        if ctx.voice_state.tremolo:
            active_effects.append("🌊 Tremolo (pulsing effect)")
        if ctx.voice_state.fadein:
            active_effects.append("🎵 Fade-In (smooth start)")
                
        if not active_effects:
            status = "🎵 No effects active"
        else:
            status = "\n".join(active_effects)
        
        embed.add_field(name="🎭 Currently Active", value=status, inline=False)
        
        # Available effects
        embed.add_field(
            name="🎛️ Available Effects",
            value=(
                "**$nightcore on/off** - Speed up music (15% faster)\n"
                "**$slowmo on/off** - Slow down music (15% slower)\n"
                "**$vaporwave on/off** - Aesthetic slowed + echo\n"
                "**$reverse on/off** - Play music backwards\n"
                "**$bass on/off** - Heavy bass boost\n"
                "**$lofi on/off** - Crunchy vintage sound\n"
                "**$echo on/off** - Triple echo chamber\n"
                "**$tremolo on/off** - Pulsing tremolo effect\n"
                "**$fadein on/off** - Smooth fade-in start"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💡 Party Tips",
            value=(
                "• Only one effect can be active at a time\n"
                "• Effects apply to upcoming songs\n"
                "• Use $reverse for backmasking fun 🔊\n"
                "• $slowmo + sad songs = mood maker 😢\n"
                "• $nightcore for party energy 🎉"
            ),
            inline=False
        )
        
        embed.set_footer(text="Experiment with different effects for maximum fun!")
        
        await ctx.send(embed=embed)

    @commands.command(name='replay')
    async def _replay(self, ctx: commands.Context):
        """Replay the current song from the beginning.

        Usage: $replay
        """
        if not ctx.voice_state.current or not ctx.voice_state.voice:
            return await ctx.send("Nothing is currently playing.")
        ctx.voice_state.songs.put_front(ctx.voice_state.current)
        ctx.voice_state.voice.stop()
        await ctx.message.add_reaction("🔁")

    @commands.command(name='history')
    async def _history(self, ctx: commands.Context):
        """Show recently played tracks.

        Usage: $history
        """
        if not ctx.voice_state.history:
            return await ctx.send("No tracks have been played yet.")

        recent = list(reversed(ctx.voice_state.history[-10:]))
        lines = [f"`{idx}.` **{song.source.title}**" for idx, song in enumerate(recent, start=1)]
        await ctx.send("Recently played:\n" + "\n".join(lines))

    @commands.command(name='playlist')
    async def _playlist(self, ctx: commands.Context, action: str = "", *, name: str = ""):
        """Manage saved playlists.

        Usage: $playlist save mymix
        Usage: $playlist load mymix
        Usage: $playlist list
        """
        action_key = action.strip().lower()
        all_playlists = self._read_playlists()
        guild_key = str(ctx.guild.id)

        if action_key == "list":
            names = sorted(all_playlists.get(guild_key, {}).keys())
            if not names:
                return await ctx.send("No saved playlists yet.")
            return await ctx.send("Saved playlists: " + ", ".join(names))

        if action_key == "save":
            playlist_name = name.strip()
            if not playlist_name:
                return await ctx.send("Usage: $playlist save <name>")

            entries: list[str] = []
            if ctx.voice_state.current and ctx.voice_state.current.source.url:
                entries.append(ctx.voice_state.current.source.url)
            entries.extend([song.source.url for song in ctx.voice_state.songs if song.source.url])
            if not entries:
                return await ctx.send("Queue is empty. Nothing to save.")

            all_playlists.setdefault(guild_key, {})[playlist_name] = entries
            self._write_playlists(all_playlists)
            return await ctx.send(f"Saved playlist '{playlist_name}' with {len(entries)} tracks.")

        if action_key == "load":
            playlist_name = name.strip()
            if not playlist_name:
                return await ctx.send("Usage: $playlist load <name>")

            loaded_entries = all_playlists.get(guild_key, {}).get(playlist_name)
            if not loaded_entries:
                return await ctx.send(f"Playlist '{playlist_name}' was not found.")

            if not ctx.voice_state.voice:
                await ctx.invoke(self._join)

            added = 0
            async with ctx.typing():
                for item in loaded_entries:
                    try:
                        source = await YTDLSource.create_source(
                            ctx,
                            item,
                            loop=asyncio.get_running_loop(),
                            volume=ctx.voice_state.volume,
                        )
                        await ctx.voice_state.songs.put(Song(source))
                        added += 1
                    except Exception:
                        continue

            return await ctx.send(f"Loaded playlist '{playlist_name}' with {added}/{len(loaded_entries)} tracks.")

        await ctx.send("Usage: $playlist save <name> | $playlist load <name> | $playlist list")

    @commands.command(name='votemode', aliases=['vote'])
    async def _votemode(self, ctx: commands.Context, mode: str):
        """Enable or disable vote-based skipping.

        Usage: $votemode on
        Usage: $votemode off
        Alias: $vote
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $votemode on|off")
        ctx.voice_state.vote_mode = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.vote_mode else "disabled"
        await ctx.send(f"Vote mode is now {state}.")

    @commands.command(name='mood')
    @music_channel_only()
    async def _mood(self, ctx: commands.Context, mood: str):
        """Queue a preset mood-based mini playlist.

        Usage: $mood happy
        Usage: $mood chill
        Usage: $mood rage
        Usage: $mood focus
        """
        mood_key = mood.strip().lower()
        if mood_key not in MOOD_QUERIES:
            return await ctx.send("Mood options: happy, chill, rage, focus")

        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)

        added = 0
        async with ctx.typing():
            for query in MOOD_QUERIES[mood_key]:
                try:
                    source = await YTDLSource.create_source(
                        ctx,
                        query,
                        loop=asyncio.get_running_loop(),
                        volume=ctx.voice_state.volume,
                    )
                    await ctx.voice_state.songs.put(Song(source))
                    added += 1
                except Exception:
                    continue

        await ctx.send(f"Mood '{mood_key}' queued with {added} tracks.")

    @commands.command(name='roastdj')
    async def _roastdj(self, ctx: commands.Context, target: Optional[discord.Member] = None):
        """Roast the current DJ or a tagged user.

        Usage: $roastdj
        Usage: $roastdj @user
        """
        roast_target = target
        if roast_target is None and ctx.voice_state.current:
            roast_target = ctx.voice_state.current.requester
        if roast_target is None:
            roast_target = ctx.author
        await ctx.send(f"{roast_target.mention}, {random.choice(DJ_ROASTS)}")

    @commands.command(name='stats')
    async def _stats(self, ctx: commands.Context):
        """Show bot and player stats.

        Usage: $stats
        """
        uptime_seconds = int(time.monotonic() - BOT_START_TIME)
        history_count = len(ctx.voice_state.history)
        queued = len(ctx.voice_state.songs)
        now_playing = ctx.voice_state.current.source.title if ctx.voice_state.current else "Nothing"

        embed = (
            discord.Embed(title="Bot Stats", color=discord.Color.blurple())
            .add_field(name="Uptime", value=format_clock(uptime_seconds), inline=True)
            .add_field(name="Songs Played", value=str(ctx.voice_state.songs_played), inline=True)
            .add_field(name="Queue Length", value=str(queued), inline=True)
            .add_field(name="History Size", value=str(history_count), inline=True)
            .add_field(name="Vote Mode", value="On" if ctx.voice_state.vote_mode else "Off", inline=True)
            .add_field(name="Nightcore", value="On" if ctx.voice_state.nightcore else "Off", inline=True)
            .add_field(name="Now Playing", value=now_playing, inline=False)
        )
        await ctx.send(embed=embed)

    @commands.command(name='nowbar')
    async def _nowbar(self, ctx: commands.Context):
        """Show a progress bar for the current track.

        Usage: $nowbar
        """
        if not ctx.voice_state.current:
            return await ctx.send("Nothing is currently playing.")

        duration = int(ctx.voice_state.current.source.duration_seconds or 0)
        if duration <= 0:
            return await ctx.send("This track is live or has unknown duration.")

        elapsed = 0
        if ctx.voice_state.current_started_at is not None:
            elapsed = int(time.monotonic() - ctx.voice_state.current_started_at)
        elapsed = max(0, min(elapsed, duration))

        bar_len = 20
        progress = elapsed / duration if duration else 0
        filled = int(progress * bar_len)
        bar = "█" * filled + "-" * (bar_len - filled)

        await ctx.send(
            f"Now Playing: **{ctx.voice_state.current.source.title}**\n"
            f"`{bar}` {format_clock(elapsed)} / {format_clock(duration)}"
        )

    @commands.command(name='play_spotify')
    async def _play_spotify(self, ctx: commands.Context):
        """Placeholder command for Spotify direct playback.

        Usage: $play_spotify
        Notes: Not currently implemented.
        """
        await ctx.send('This feature is currently not available. It is in development, check back later!')

        for _ in range(6):
            emoji = random_guild_emoji(ctx.guild)
            if emoji:
                await ctx.message.add_reaction(emoji)

    @commands.command(name='usage')
    async def _usage(self, ctx: commands.Context):
        """Show simple usage instructions.

        Usage: $usage
        """
        embed = discord.Embed(
            title="🎵 How to Use Joe Barden Bot",
            description="Simple music bot commands everyone can use!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🎶 Play Music",
            value=(
                "**$play song name** - Plays any song\n"
                "**$play YouTube link** - Copy paste any YouTube URL\n"
                "**$play Spotify link** - Works with Spotify too!\n"
                "**$mood happy** - Get a happy playlist"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎮 Control Music",
            value=(
                "**$skip** - Skip current song\n"
                "**$volume 50** - Change volume (0-100)\n"
                "**$queue** - See what's playing next\n"
                "**$now** - See current song info"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎛️ Audio Effects (Party Tricks!)",
            value=(
                "**$effects** - See all available effects\n"
                "**$nightcore on** - Speed up music (party mode!)\n"
                "**$slowmo on** - Slow down music (chill vibes)\n"
                "**$vaporwave on** - Aesthetic slowed + echo\n"
                "**$reverse on** - Play music backwards!\n"
                "**$bass on** - Heavy bass boost!\n"
                "**$lofi on** - Crunchy vintage sound!\n"
                "**$echo on** - Triple echo chamber!\n"
                "**$tremolo on** - Pulsing tremolo effect!\n"
                "**$fadein on** - Smooth fade-in start!"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📋 Other Fun Stuff",
            value=(
                "**$lyrics artist - song** - Get song lyrics\n"
                "**$history** - See recently played songs\n"
                "**$shuffle** - Mix up the playlist\n"
                "**$roastdj** - Roast the current DJ 😄"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🤖 AI Assistant",
            value=(
                "**$ask What's the meaning of life?** - Ask AI anything\n"
                "**$dj Suggest study music** - AI music recommendations\n"
                "**$chat** - Start private AI conversation\n"
                "**$aistats** - Check your AI usage limits"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💡 Pro Tips",
            value=(
                "• Works with YouTube, Spotify, and Apple Music links\n"
                "• Type song names or paste URLs - both work!\n"
                "• Use $help to see all commands\n"
                "• Bot joins your voice channel automatically\n"
                "• AI knows what music is playing! 🎵🤖"
            ),
            inline=False
        )
        
        embed.set_footer(text="Just start with $play and enjoy the music! 🎵")
        
        await ctx.send(embed=embed)

    # AI Helper Functions
    def _check_ai_limit(self, user_id: int) -> bool:
        """Check if user is within AI usage limits."""
        today = datetime.now().date()
        if today not in AI_USAGE:
            AI_USAGE[today] = {}
        
        user_requests = AI_USAGE[today].get(user_id, 0)
        total_requests = sum(AI_USAGE[today].values())
        
        return user_requests < 50 and total_requests < DAILY_LIMIT

    def _track_ai_usage(self, user_id: int):
        """Track AI usage for rate limiting."""
        today = datetime.now().date()
        if today not in AI_USAGE:
            AI_USAGE[today] = {}
        
        AI_USAGE[today][user_id] = AI_USAGE[today].get(user_id, 0) + 1

    def _get_music_context(self, ctx: commands.Context) -> str:
        """Get current music context for AI responses."""
        context = ""
        if ctx.voice_state:
            if ctx.voice_state.current:
                context += f"Currently playing: {ctx.voice_state.current.source.title}\n"
            
            if len(ctx.voice_state.songs) > 0:
                next_songs = [song.source.title for song in list(ctx.voice_state.songs)[:3]]
                context += f"Up next: {', '.join(next_songs)}\n"
            
            if ctx.voice_state.nightcore:
                context += "Audio effect: Nightcore (sped up)\n"
            elif ctx.voice_state.slowmo:
                context += "Audio effect: Slow-mo (slowed down)\n"
            elif ctx.voice_state.vaporwave:
                context += "Audio effect: Vaporwave (aesthetic)\n"
            elif ctx.voice_state.reverse:
                context += "Audio effect: Reverse (backwards)\n"
            elif ctx.voice_state.bass:
                context += "Audio effect: Bass Boost (heavy bass)\n"
            elif ctx.voice_state.lofi:
                context += "Audio effect: Lo-Fi (crunchy vintage)\n"
            elif ctx.voice_state.echo:
                context += "Audio effect: Echo Chamber (triple echo)\n"
            elif ctx.voice_state.tremolo:
                context += "Audio effect: Tremolo (pulsing effect)\n"
            elif ctx.voice_state.fadein:
                context += "Audio effect: Fade-In (smooth start)\n"
        
        return context

    @commands.command(name='ask')
    @commands.cooldown(1, 30, commands.BucketType.user)  # 1 request per 30 seconds per user
    async def _ask(self, ctx: commands.Context, *, question: str):
        """Ask the AI a question.

        Usage: $ask What's the meaning of life?
        """
        if not gemini_model:
            return await ctx.send("❌ AI is not available. Check API configuration.")
        
        if not self._check_ai_limit(ctx.author.id):
            return await ctx.send("⏰ You've reached your daily AI limit. Try again tomorrow!")
        
        try:
            await ctx.send("🤔 Thinking...")
            
            # Get music context for more relevant responses
            music_context = self._get_music_context(ctx)
            if music_context:
                enhanced_question = f"Music Context: {music_context}\n\nUser Question: {question}"
            else:
                enhanced_question = question
            
            response_text = generate_content_with_fallback(enhanced_question)
            self._track_ai_usage(ctx.author.id)
            
            # Split long responses to meet Discord's 2000 character limit
            if len(response_text) <= 1900:
                await ctx.send(f"🤖 **AI says:**\n{response_text}")
            else:
                # Split into chunks
                chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await ctx.send(f"🤖 **AI says (part {i+1}/{len(chunks)}):**\n{chunk}")
                    else:
                        await ctx.send(f"🤖 **Part {i+1}/{len(chunks)}:**\n{chunk}")
                        await asyncio.sleep(1)  # Small delay between chunks
                    
        except Exception as e:
            await ctx.send(f"❌ AI error: {str(e)}")

    @commands.command(name='chat')
    @commands.cooldown(1, 60, commands.BucketType.user)  # 1 request per minute per user
    async def _chat(self, ctx: commands.Context):
        """Start a private conversation with the AI.

        Usage: $chat
        """
        if not gemini_model:
            return await ctx.send("❌ AI is not available. Check API configuration.")
        
        if not self._check_ai_limit(ctx.author.id):
            return await ctx.send("⏰ You've reached your daily AI limit. Try again tomorrow!")
        
        try:
            # Create a DM channel with the user
            dm_channel = await ctx.author.create_dm()
            
            # Initialize conversation if not exists
            if ctx.author.id not in self.ai_conversations:
                self.ai_conversations[ctx.author.id] = []
            
            await dm_channel.send(
                "🤖 **AI Chat Started!**\n"
                "I'm now chatting with you privately. Just send me messages here and I'll respond!\n"
                "Type `!endchat` to stop the conversation.\n\n"
                "What would you like to talk about?"
            )
            
            await ctx.send("📩 Check your DMs! I've started a private chat with you.")
            
        except discord.Forbidden:
            await ctx.send("❌ I can't send you DMs. Please enable DMs from server members.")
        except Exception as e:
            await ctx.send(f"❌ Chat error: {str(e)}")

    @commands.command(name='dj')
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def _dj(self, ctx: commands.Context, *, request: str):
        """Ask the AI DJ for music suggestions and help.

        Usage: $dj What should I play for a study session?
        """
        if not gemini_model:
            return await ctx.send("❌ AI DJ is not available. Check API configuration.")
        
        if not self._check_ai_limit(ctx.author.id):
            return await ctx.send("⏰ You've reached your daily AI limit. Try again tomorrow!")
        
        try:
            await ctx.send("🎵 DJ AI is thinking...")
            
            # Get detailed music context
            music_context = self._get_music_context(ctx)
            
            # Create DJ-specific prompt
            dj_prompt = f"""You are a helpful AI DJ assistant. Current music context:
{music_context if music_context else "No music currently playing."}

User request: {request}

Provide helpful music suggestions, explain music concepts, or help with music-related questions. 
Be friendly, knowledgeable, and concise. If suggesting songs, explain why they fit the mood/occasion."""
            
            response_text = generate_content_with_fallback(dj_prompt)
            self._track_ai_usage(ctx.author.id)
            if len(response_text) <= 1900:
                await ctx.send(f"🎵 **DJ AI says:**\n{response_text}")
            else:
                chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await ctx.send(f"🎵 **DJ AI (part {i+1}/{len(chunks)}):**\n{chunk}")
                    else:
                        await ctx.send(f"🎵 **Part {i+1}/{len(chunks)}:**\n{chunk}")
                        await asyncio.sleep(1)
                        
        except Exception as e:
            await ctx.send(f"❌ DJ AI error: {str(e)}")

    @commands.command(name='aistats')
    async def _aistats(self, ctx: commands.Context):
        """Show AI usage statistics.

        Usage: $aistats
        """
        today = datetime.now().date()
        if today not in AI_USAGE:
            return await ctx.send("📊 No AI usage today.")
        
        total_requests = sum(AI_USAGE[today].values())
        user_requests = AI_USAGE[today].get(ctx.author.id, 0)
        remaining_user = 50 - user_requests
        remaining_total = DAILY_LIMIT - total_requests
        
        embed = discord.Embed(
            title="📊 AI Usage Statistics",
            description=f"Today's usage ({today})",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="🔢 Your Requests", value=f"{user_requests}/50", inline=True)
        embed.add_field(name="🌍 Total Requests", value=f"{total_requests}/{DAILY_LIMIT}", inline=True)
        embed.add_field(name="⏰ Your Remaining", value=f"{remaining_user}", inline=True)
        embed.add_field(name="⏰ Global Remaining", value=f"{remaining_total}", inline=True)
        
        if remaining_user <= 5:
            embed.add_field(name="⚠️ Notice", value="You're running low on requests!", inline=False)
        
        await ctx.send(embed=embed)

    @commands.command(name='shit', aliases=['tourette', 'fuck', 'youdonottellme'])
    async def _shit(self, ctx: commands.Context):
        """Send a random quote response.

        Usage: $shit
        Aliases: $tourette, $fuck, $youdonottellme
        """
        quotes = [
            'Piss. Holy shit. Damnit. Fuck the lottery, shit.',
            'I bought your colgate toothpaste, the one with tartar control and it made me feel like a piece of SHIT.',
            'I hope this is the puff daddy version of this song, not that sting piece of SHIT.... FUUUUUUCK. DAMN IT. Holy shit. PISS. You- ASS. Fuck you.',
            'Its emberrassing as FUCK to have an ASS',
            'Fuck you',
            'YOU HAVE BAAAAALLS',
            'FUCK YOU FUCK YOU FUCK YOU IN THE ASS',
            'Dont you EVER. Talk about my DICK. WITHOUT MY PERMISSION',
            'Lemme tell you about a porcupines balls, theyre small and they dont give a SHIT!',
            'If she was a car, she would be a Four Door Ford Whore, bitch',
            'BOB SAGET!',
            'FUCK YOU AND EVERY MALL SANTA THAT LOOKS LIKE YOU!',
            'I want two cheeseburgers, and I want pickles and ketchup on them. And dont load it up with a bunch of BULL shit!! I want a Biggie Fries, and give me some SHIT TO DRINK!',
            'I love my Grandma Jenelle, shes the sweetest person in the entire world, and God bless her. BUT SHES OLD AS FUCK!',
            'Tonight, on Unsolved Mysteries, find out who gives a shit about Big Foot. UPDATE! Apparently nobody gives a shit so FUCK HIM! UPDATE! Last night somebody broke in and stole over 500 dollars worth of shit from my PLACE! Thats right, 500 dollars worth of BULL SHIT!',
            'Shes a bitch. I called her a bitch right in front of her tits',
            'PISSING OUT THE WINDOW AND SHITTING OUT THE WINDOW ARE 2 DIFFERENT THINGS!',
            'ITS EASY FOR DENNIS TO GIVE A SHIT BECAUSE DENNIS IS SO FULL OF SHIT!',
            'I dont want to switch phone companies. You can stick those 5 cent Sundays up your fucking ass!',
            'Dom Deluise, he used to be a chef on TV, BUT NOW HE JUST SITS AT HOME WITH HIS ASS UP HIS ASS!',
            'ALRIGHT! WHO WRINKLED MY RANDY TRAVIS POSTER, PISSED IN THE SEAT, AND HID MY KEYS?',
            'SUCK MY DICK. OR COCK.',
            'IT SOUNDS LIKE CHEWBACCA TAKING A SHIT!'
        ]
        response = random.choice(quotes)
        await ctx.send(response)
        await ctx.message.add_reaction('🖕')


def random_guild_emoji(guild: Optional[discord.Guild]):
    if guild and guild.emojis:
        return random.choice(guild.emojis)
    return None


bot = commands.Bot(command_prefix='#', description='Im Joe Barden and I approve this message.', intents=intents, help_command=None)

@bot.event
async def on_message(message):
    print(f'MESSAGE RECEIVED: {message.content}')
    if message.author.bot:
        return

    # Handle AI chat in DMs
    if message.guild is None and gemini_model:  # DM message
        music_cog = bot.get_cog("Music")
        if music_cog and message.author.id in music_cog.ai_conversations:
            if message.content.lower() == '!endchat':
                del music_cog.ai_conversations[message.author.id]
                await message.send("👋 Chat ended! Type `$chat` in a server to start a new conversation.")
                return
            
            try:
                # Check AI limits
                if not music_cog._check_ai_limit(message.author.id):
                    await message.send("⏰ You've reached your daily AI limit. Try again tomorrow!")
                    return
                
                await message.send("🤔 Thinking...")
                
                response_text = generate_content_with_fallback(message.content)
                music_cog._track_ai_usage(message.author.id)
                if len(response_text) <= 1900:
                    await message.send(f"🤖 {response_text}")
                else:
                    chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                    for i, chunk in enumerate(chunks):
                        if i == 0:
                            await message.send(f"🤖 (part {i+1}/{len(chunks)})\n{chunk}")
                        else:
                            await message.send(f"🤖 Part {i+1}/{len(chunks)}:\n{chunk}")
                            await asyncio.sleep(1)
                            
            except Exception as e:
                await message.send(f"❌ AI error: {str(e)}")
            
            return

    await bot.process_commands(message)

    content = message.content.lower()

    if "sleepy joe" in content:
        await message.channel.send("That hurts my feelings.")
        await message.add_reaction("🖕")
        return

    if "president" in content:
        await message.channel.send("Hi. I'm the President. I like iced creams.")
        r = random_guild_emoji(message.guild)
        if r:
            await message.add_reaction(r)
    elif "fam" in content:
        await message.channel.send("That's lit as fuck fam.")
        r = random_guild_emoji(message.guild)
        if r:
            await message.add_reaction(r)
    elif "nixon" in content:
        await message.channel.send("TRICKY DICK NIXON!?")
        r = random_guild_emoji(message.guild)
        if r:
            await message.add_reaction(r)
    elif "deez" in content:
        await message.channel.send("NUTS 🖕")
        r = random_guild_emoji(message.guild)
        if r:
            await message.add_reaction(r)
    elif "lets get to bashing butts" in content:
        await message.channel.send("AS WELL AS DEEZ NUTS")
    elif "take that robe off" in content:
        await message.channel.send("Lets get to bashing 🍑 as well as DEEZ nuts")
    elif "you do not tell me" in content:
        await message.channel.send("YOU BLAHDY FACK")
        await message.channel.send("YOU BASTARD BITCH")
        await message.channel.send("BLAHDY FACK YOU")
        for _ in range(6):
            emoji = random_guild_emoji(message.guild)
            if emoji:
                await message.add_reaction(emoji)
    else:
        return
        
@bot.event
async def on_ready():
    print('Logged in as:\n{0.user.name}\n{0.user.id}'.format(bot))
    if bot.get_cog("Music") is None:
        await bot.add_cog(Music(bot))

if not token:
    raise RuntimeError("DISCORD_TOKEN is not set. Add it to your environment or .env file.")

bot.run(token)