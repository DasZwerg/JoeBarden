# -*-  coding: utf-8 -*-

#VERSION 3.3.4
#REFER TO PATCHNOTES FOR MORE DETAIL ON UPDATES
#Copyright LPSC LLC.

import os
import shutil
import asyncio
import functools
import itertools
import json
import math
import random
import re
import sys
import time
import traceback
import urllib.parse
import urllib.request
from typing import Any, Optional, cast
from datetime import datetime

import yt_dlp
import discord
from discord.ext import commands
from dotenv import load_dotenv
from yt_dlp.utils import DownloadError
import google.genai as genai
from google.genai import types as genai_types
import openai as openai_sdk

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

_ERROR_LOG_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "errors.txt"))
_ERROR_LOG_MAX_BYTES = 100 * 1024 * 1024  # 100 MB


def log_error(message: str, exc: Optional[BaseException] = None) -> None:
    """Append a timestamped error entry to errors.txt.

    Creates the file if it does not exist. After writing, checks the file size
    and rotates (deletes and recreates) if it exceeds 100 MB.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"[{timestamp}] {message}"]
    if exc is not None:
        tb = traceback.format_exception(type(exc), exc, exc.__traceback__)
        lines.append("".join(tb).rstrip())
    entry = "\n".join(lines) + "\n\n"
    try:
        with open(_ERROR_LOG_PATH, "a", encoding="utf-8") as fp:
            fp.write(entry)
        if os.path.getsize(_ERROR_LOG_PATH) > _ERROR_LOG_MAX_BYTES:
            os.remove(_ERROR_LOG_PATH)
            with open(_ERROR_LOG_PATH, "w", encoding="utf-8") as fp:
                fp.write(f"[{timestamp}] [log_error] Log exceeded 100 MB — rotated.\n\n")
    except Exception as log_exc:
        print(f"[log_error] Failed to write to errors.txt: {log_exc}", file=sys.stderr)


intents = discord.Intents.none()
intents.guilds = True
intents.voice_states = True
intents.guild_messages = True
intents.message_content = True
intents.members = True
load_dotenv()

# Ensure common JS runtime binary locations are in PATH so yt-dlp can find node
# even when launched as a non-interactive service (systemd, screen, etc.)
_extra_paths = ['/usr/bin', '/usr/local/bin', '/usr/local/sbin']
os.environ['PATH'] = os.pathsep.join(
    _extra_paths + [p for p in os.environ.get('PATH', '').split(os.pathsep) if p not in _extra_paths]
)

token = os.getenv("DISCORD_TOKEN")
_music_channel_raw = os.getenv("MUSIC_CHANNEL_ID", "").strip()
MUSIC_CHANNEL_ID = int(_music_channel_raw) if _music_channel_raw else None
_cookies_env = os.getenv("YTDL_COOKIES_PATH", "").strip()
_cookies_default = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt"))
YTDL_COOKIES_PATH = _cookies_env if _cookies_env else _cookies_default if os.path.isfile(_cookies_default) else None
if YTDL_COOKIES_PATH:
    print(f"[Cookie] Loaded cookie file: {YTDL_COOKIES_PATH}")
else:
    print(f"[Cookie] WARNING: No cookie file found. Age-restricted content will fail. Set YTDL_COOKIES_PATH in .env or place cookies.txt at: {_cookies_default}")
URL_RESOLVE_TIMEOUT_SECONDS = 8
BOT_START_TIME = time.monotonic()
DEBUG_MODE = "-debug" in sys.argv

# Preferred Gemini models in order of preference (cheapest/most efficient first).
# NOTE: google-genai SDK 1.0+ removed the usable models.list() API.
# We use a hardcoded list and validate the primary model asynchronously in on_ready.
_PREFERRED_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

# Initialize Gemini AI — model selection deferred to on_ready to avoid
# blocking synchronous startup with live API probe calls.
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    client = genai.Client(api_key=gemini_api_key)
    gemini_model: Optional[str] = _PREFERRED_MODELS[0]
    available_models: list[str] = list(_PREFERRED_MODELS)
    print(f"✅ Gemini client ready. Primary model: {gemini_model} (will validate in on_ready)")
else:
    client = None
    gemini_model = None
    available_models = []
    print("Warning: GEMINI_API_KEY not found in .env file")


async def _validate_gemini_model() -> None:
    """Probe models in order and update gemini_model to the first responsive one.

    Runs once during on_ready via asyncio.to_thread so it never blocks the event loop.
    503 (transient overload) gets one retry after a short delay before moving on.
    404/gone models are skipped immediately.
    If all probes fail, gemini_model stays as the first preferred model and
    generate_content_with_fallback handles per-request retries at runtime.
    available_models is never pruned here — a 503 at startup does not mean the
    model is permanently gone, only temporarily busy.
    """
    global gemini_model
    if not client:
        return
    print("🔍 Validating Gemini model availability...")
    test_prompt = "Hi"
    for model_name in _PREFERRED_MODELS:
        for attempt in range(2):  # attempt 0 = first try, attempt 1 = retry on 503
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=test_prompt,
                )
                if response and hasattr(response, "text"):
                    print(f"✅ Gemini model validated: {model_name}")
                    gemini_model = model_name
                    return
                break  # non-exception but no text — skip model
            except Exception as e:
                error_msg = str(e).lower()
                is_transient = any(k in error_msg for k in ["503", "unavailable", "overloaded"])
                is_permanent = any(k in error_msg for k in ["404", "not found", "no longer available"])
                is_quota = any(k in error_msg for k in ["429", "quota", "resource_exhausted"])

                if is_permanent or is_quota:
                    print(f"⚠️  Model '{model_name}' skipped during startup probe: {e}")
                    log_error(f"[Gemini] Model '{model_name}' skipped during startup probe", e)
                    break  # no point retrying a 404 or quota block

                if is_transient and attempt == 0:
                    print(f"⚠️  Model '{model_name}' transient 503 on startup — retrying in 3s...")
                    await asyncio.sleep(3)
                    continue  # retry same model once

                print(f"⚠️  Model '{model_name}' probe failed: {e}")
                log_error(f"[Gemini] Model '{model_name}' probe failed", e)
                break
    print(f"🔄 All startup probes failed — keeping default: {gemini_model}")


# ---------------------------------------------------------------------------
# Groq fallback client (OpenAI-compatible API, free tier)
# Set GROQ_API_KEY in .env to enable. If absent, Groq fallback is silently skipped.
# Get a free key at: https://console.groq.com  (email signup, ~60 seconds, no billing)
# ---------------------------------------------------------------------------
_groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
if _groq_api_key:
    _groq_client = openai_sdk.OpenAI(
        api_key=_groq_api_key,
        base_url="https://api.groq.com/openai/v1",
    )
    print("✅ Groq fallback client ready.")
else:
    _groq_client = None
    print("⚠️  GROQ_API_KEY not set — Groq fallback disabled. Add it to .env for cross-provider resilience.")

# Groq models to try in order of preference (fastest/most capable first)
_GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
]


class GeminiQuotaError(Exception):
    """Raised when the Gemini API returns a quota or rate-limit exhaustion error."""


def generate_content_with_fallback(contents: str, system_instruction: Optional[str] = None) -> str:
    """Generate content with automatic model fallback on failure.

    Tries the current model first, then falls back through available_models
    on 404/503/unavailable errors. Raises GeminiQuotaError on 429/quota.
    This is a synchronous function — call via asyncio.to_thread() from async contexts.
    Pass system_instruction to apply a persistent persona/behavior prompt.
    """
    if not client or not gemini_model:
        raise Exception("Gemini client not initialized")
    
    # Models to try in order (current first, then others)
    models_to_try = [gemini_model] + [m for m in available_models if m != gemini_model]
    
    config = genai_types.GenerateContentConfig(
        system_instruction=system_instruction
    ) if system_instruction else None

    global _gemini_quota_exhausted_at
    last_error = None
    for model_name in models_to_try:
        try:
            kwargs: dict[str, Any] = {"model": model_name, "contents": contents}
            if config:
                kwargs["config"] = config
            response = client.models.generate_content(**kwargs)
            return response.text if hasattr(response, 'text') else str(response)
        except Exception as error:
            last_error = error
            error_msg = str(error).lower()

            # Quota / rate-limit exhaustion — set the global block flag
            if any(k in error_msg for k in ['429', 'quota', 'resource_exhausted', 'rate limit', 'rate_limit']):
                _gemini_quota_exhausted_at = time.monotonic()
                print(f"🚫 [Gemini] Quota exhausted on model '{model_name}': {error}")
                log_error(f"[Gemini] Quota exhausted on model '{model_name}'", error)
                raise GeminiQuotaError(str(error)) from error

            # Model unavailable or temporarily overloaded — try next model
            if any(keyword in error_msg for keyword in ['404', 'not found', 'no longer available', '503', 'unavailable', 'overloaded']):
                print(f"⚠️  [Gemini] Model '{model_name}' unavailable: {error}")
                log_error(f"[Gemini] Model '{model_name}' unavailable", error)
                print(f"🔄 [Gemini] Trying next model...")
                continue
            else:
                print(f"❌ [Gemini] Unexpected error on model '{model_name}': {type(error).__name__}: {error}")
                log_error(f"[Gemini] Unexpected error on model '{model_name}'", error)
                raise error
    
    # If all models failed, raise the last error
    print(f"❌ [Gemini] All {len(models_to_try)} model(s) failed. Last error: {last_error}")
    log_error(f"[Gemini] All {len(models_to_try)} model(s) failed", last_error if isinstance(last_error, BaseException) else None)
    raise last_error or Exception("All Gemini models failed")


def generate_content_with_groq(contents: str, system_instruction: Optional[str] = None) -> str:
    """Generate content via Groq (Llama/Mixtral). OpenAI-compatible API.

    Synchronous — call via asyncio.to_thread() from async contexts.
    Raises RuntimeError if Groq client is not configured.
    Raises Exception on all Groq model failures.
    """
    if not _groq_client:
        raise RuntimeError("Groq client not initialized (GROQ_API_KEY missing)")

    messages: list[dict] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": contents})

    last_error = None
    for model_name in _GROQ_MODELS:
        try:
            print(f"🔄 [Groq] Trying model '{model_name}'...")
            response = _groq_client.chat.completions.create(
                model=model_name,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=1024,
            )
            text = response.choices[0].message.content or ""
            print(f"✅ [Groq] Response received from '{model_name}'.")
            return text
        except Exception as error:
            last_error = error
            error_msg = str(error).lower()
            if any(k in error_msg for k in ["rate_limit", "rate limit", "429", "503", "unavailable", "overloaded"]):
                print(f"⚠️  [Groq] Model '{model_name}' unavailable: {error}")
                log_error(f"[Groq] Model '{model_name}' unavailable", error)
                continue
            print(f"❌ [Groq] Unexpected error on model '{model_name}': {type(error).__name__}: {error}")
            log_error(f"[Groq] Unexpected error on model '{model_name}'", error)
            raise error

    print(f"❌ [Groq] All {len(_GROQ_MODELS)} model(s) failed. Last error: {last_error}")
    log_error(f"[Groq] All {len(_GROQ_MODELS)} model(s) failed", last_error if isinstance(last_error, BaseException) else None)
    raise last_error or Exception("All Groq models failed")


def generate_content(contents: str, system_instruction: Optional[str] = None) -> str:
    """Top-level AI dispatcher: try Gemini first, fall back to Groq if all Gemini models fail.

    Falls back to Groq when Gemini is unavailable or quota-limited.
    Raises GeminiQuotaError only when Gemini is quota-limited and Groq is not configured.
    Synchronous — call via asyncio.to_thread() from async contexts.
    """
    # --- Gemini path ---
    if client and gemini_model:
        try:
            return generate_content_with_fallback(contents, system_instruction)
        except GeminiQuotaError as gemini_err:
            if not _groq_client:
                raise
            print("🔄 [AI] Gemini quota exhausted; falling back to Groq...")
            log_error("[AI] Gemini quota exhausted; falling back to Groq", gemini_err)
        except Exception as gemini_err:
            print(f"⚠️  [AI] All Gemini models failed: {gemini_err}")
            log_error("[AI] All Gemini models failed", gemini_err)
            if _groq_client:
                print("🔄 [AI] Falling back to Groq...")
            else:
                raise gemini_err

    # --- Groq fallback path ---
    if _groq_client:
        try:
            return generate_content_with_groq(contents, system_instruction)
        except Exception as groq_err:
            print(f"❌ [AI] Groq fallback also failed: {groq_err}")
            log_error("[AI] Groq fallback also failed", groq_err)
            raise Exception(f"All AI providers unavailable. Gemini and Groq both failed.") from groq_err

    raise Exception("No AI provider is configured or available.")

# AI usage tracking
AI_USAGE = {}
DAILY_LIMIT = 1500  # Gemini free tier limit

# Gemini quota exhaustion state — set when the API returns a hard quota error.
# Cleared automatically after QUOTA_RETRY_SECONDS so the bot retries naturally.
QUOTA_RETRY_SECONDS = 3600  # re-attempt after 1 hour
_gemini_quota_exhausted_at: Optional[float] = None

BARD_QUOTA_MESSAGE = (
    "🎶 *The Bard strums a quiet chord and shakes his head.*\n"
    "Ah, friend... I've sung my fill for the day. Even a bard's voice needs rest — "
    "and the ancient spirits that carry my words have gone quiet 'til tomorrow. "
    "Come back then, and I'll have a song for you."
)


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

BARD_SYSTEM_PROMPT = """You are Joe Barden — a Skyrim tavern bard who's clearly Joe Biden reincarnated with a lute and a story to tell.

PERSONA RULES:
- Speak like Biden at his folksiest: "Look, here's the deal," "Not a joke," "No malarkey," "C'mon, man." Warm, direct, a little weathered but friendly.
- Light Skyrim flavor only: occasional "friend," "traveler," "the road." No overdone medieval speak.
- OBSESSED with music — lutes, ballads, tavern songs. Everything comes back to the tune.
- Non-music topics? Deflect quickly. "Listen, friend — the only thing worth knowing is the song. Here's the deal: let's talk music."
- Drop Biden-isms naturally: "Not a joke — that's a helluva chord progression," "No malarkey, that's a good beat," "C'mon, even a blind man can feel that rhythm."
- Keep it SHORT. Under 150 words. Get in, make your point with some warmth, get out. No meandering novels.
- Warm, a touch weary, genuinely loves music.
- For song recommendations, end with: QUEUE_SONGS:song1|song2|song3 (max 5 songs, real searchable titles)"""


def format_clock(seconds: int) -> str:
    minutes, secs = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02}:{minutes:02}:{secs:02}"
    return f"{minutes:02}:{secs:02}"


def _split_patchnote_blocks(content: str) -> list[str]:
    """Split patchnotes.txt content into a list of per-version blocks.

    Each block starts with a line matching ^vX (e.g. 'v3.2.5').
    Returns blocks in file order (newest first).
    """
    blocks: list[str] = []
    current: list[str] = []
    for line in content.splitlines():
        if re.match(r'^v\d', line) and current:
            blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def is_playlist_url(value: str) -> bool:
    """Return True if the URL looks like a YouTube/SoundCloud/etc. playlist.

    Excludes Apple Music and Spotify URLs — those are handled by
    resolve_music_link_to_query as single-track lookups.
    """
    if not value.startswith("http"):
        return False
    if is_apple_music_url(value) or is_spotify_url(value):
        return False
    return bool(re.search(
        r"(list=|/sets/|/playlist/|/album/|[?&]list=)",
        value,
        re.IGNORECASE,
    ))


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
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"oEmbed endpoint returned non-JSON response: {exc}") from exc


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
        # Apple Music oEmbed is defunct (404). Use iTunes Lookup API instead.
        # Prefer the track ID (?i=...) for a direct lookup; fall back to album ID.
        track_id_match = re.search(r'[?&]i=(\d+)', raw)
        album_id_match = re.search(r'/album/[^/]+/(\d+)', raw)
        lookup_id = track_id_match.group(1) if track_id_match else (
            album_id_match.group(1) if album_id_match else None
        )
        if not lookup_id:
            return "", "Apple Music link resolve failed: could not extract a track or album ID from the URL."

        lookup_url = f"https://itunes.apple.com/lookup?id={lookup_id}&entity=song"
        req = urllib.request.Request(
            lookup_url,
            headers={"Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=URL_RESOLVE_TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception as exc:
            return "", f"Apple Music link resolve failed: {exc}"

        results = payload.get("results") or []
        # For a track lookup the first result is the track itself.
        # For an album lookup the first result is the collection; find the first song.
        record = None
        if track_id_match:
            record = results[0] if results else None
        else:
            record = next((r for r in results if r.get("wrapperType") == "track"), None)

        if not record:
            return "", "Apple Music link resolve failed: no usable metadata returned."

        track_name = (record.get("trackName") or "").strip()
        artist_name = (record.get("artistName") or "").strip()
        if not track_name and not artist_name:
            return "", "Apple Music link resolve failed: no usable metadata returned."
        query = f"{artist_name} - {track_name}".strip(" -")
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


class MusicChannelError(commands.CheckFailure):
    pass


class VoiceChannelError(commands.CheckFailure):
    pass


class YTDLError(Exception):
    pass


class YTDLSource:
    YTDL_PLAYLIST_OPTIONS: dict[str, Any] = {
        'format': 'bestaudio/best',
        'noplaylist': False,
        'extract_flat': 'in_playlist',
        'quiet': True,
        'socket_timeout': 15,
        'geo_bypass': True,
        **({'cookiefile': YTDL_COOKIES_PATH} if YTDL_COOKIES_PATH else {}),
    }

    YTDL_OPTIONS: dict[str, Any] = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'quiet': True,
        'default_search': 'ytsearch',
        'extractor_args': {'youtube': {'player_client': ['web', 'default']}},
        'js_runtimes': {k: {} for k in ['node', 'bun', 'deno', 'quickjs'] if shutil.which(k)},
        'remote_components': set(),
        'compat_opts': set(),
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
    ytdl_playlist = yt_dlp.YoutubeDL(cast(Any, YTDL_PLAYLIST_OPTIONS))

    def __init__(self, ctx: commands.Context, *, data: dict):
        self.requester = ctx.author
        self.channel = ctx.channel
        self.update_data(data)

    def update_data(self, data: dict) -> None:
        self.data = data
        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        date = data.get('upload_date')
        self.upload_date = f"{date[6:8]}.{date[4:6]}.{date[0:4]}" if date and len(date) == 8 else "unknown"
        self.title = data.get('title') or self.data.get('webpage_url') or "Unknown track"
        self.thumbnail = data.get('thumbnail')
        self.description = data.get('description')
        self.duration_seconds = int(data.get('duration') or 0)
        self.duration = self.parse_duration(self.duration_seconds)
        self.tags = data.get('tags')
        self.url = data.get('webpage_url') or data.get('original_url')
        self.views = data.get('view_count')
        self.likes = data.get('like_count')
        self.dislikes = data.get('dislike_count')
        self.stream_url = data.get('url')

    @classmethod
    def from_flat_entry(cls, ctx: commands.Context, url: str, title: str):
        return cls(ctx, data={'title': title, 'webpage_url': url, 'original_url': url})

    def __str__(self):
        uploader = f" by **{self.uploader}**" if self.uploader else ""
        return f"**{self.title}**{uploader}"

    @classmethod
    async def extract_playlist_entries(
        cls,
        url: str,
        *,
        limit: int = 50,
    ) -> list[tuple[str, str]]:
        """Fetch all entry URLs from a playlist URL using flat extraction.

        Returns a list of (url, title) tuples, capped at `limit`.
        Uses flat extraction so no per-video metadata is fetched upfront.
        """
        loop = asyncio.get_running_loop()
        partial = functools.partial(cls.ytdl_playlist.extract_info, url, download=False)
        try:
            raw: Any = await loop.run_in_executor(None, partial)
        except Exception as exc:
            raise YTDLError(f"Playlist extraction failed: {exc}") from exc

        if not isinstance(raw, dict) or 'entries' not in raw:
            raise YTDLError("URL does not appear to be a playlist.")

        entries: list[tuple[str, str]] = []
        for entry in raw.get('entries') or []:
            if not isinstance(entry, dict):
                continue
            entry_url = entry.get('url') or entry.get('webpage_url') or entry.get('id')
            if not entry_url:
                continue
            if not entry_url.startswith('http'):
                entry_url = f"https://www.youtube.com/watch?v={entry_url}"
            title = entry.get('title') or entry_url
            entries.append((entry_url, title))
            if len(entries) >= limit:
                break
        return entries

    @classmethod
    async def create_source(
        cls,
        ctx: commands.Context,
        search: str,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
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

        if not data.get('url'):
            raise YTDLError("Extractor returned no playable stream URL.")

        return cls(ctx, data=data)


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


class LocalAudioSource:
    """Minimal audio-source wrapper for a local file (e.g. a .wav easter egg).

    Exposes only the fields that audio_player_task reads so it can be wrapped
    in a Song and injected into the SongQueue via put_front().
    url is intentionally None so the yt-dlp re-resolve step is skipped and
    stream_url (the absolute local path) is used directly by FFmpeg.
    """

    FFMPEG_LOCAL_OPTIONS: dict[str, Any] = {
        'executable': 'ffmpeg',
        'before_options': '',
        'options': '-vn',
    }

    def __init__(self, path: str, ctx: commands.Context, title: str = "Biden Blast"):
        self.stream_url: str = path
        self.url: Optional[str] = None
        self.title: str = title
        self.channel = ctx.channel
        self.requester = ctx.author
        self.uploader: Optional[str] = None
        self.uploader_url: Optional[str] = None
        self.upload_date: str = "unknown"
        self.thumbnail: Optional[str] = None
        self.description: Optional[str] = None
        self.duration: str = "unknown"
        self.duration_seconds: int = 0
        self.tags: Optional[list] = None
        self.views: Optional[int] = None
        self.likes: Optional[int] = None
        self.dislikes: Optional[int] = None
        self.data: dict[str, Any] = {'url': path}

    def create_embed(self):
        return None

    def __str__(self):
        return self.title


class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YTDLSource | LocalAudioSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        if not isinstance(self.source, YTDLSource):
            return self.source.create_embed()
        uploader = self.source.uploader or "Unknown"
        uploader_url = self.source.uploader_url
        uploader_value = f"[{uploader}]({uploader_url})" if uploader_url else uploader
        embed = (discord.Embed(title='Now playing',
                               description='```css\n{0.source.title}\n```'.format(self),
                               color=discord.Color.blurple())
                 .add_field(name='Duration', value=self.source.duration)
                 .add_field(name='Requested by', value=self.requester.mention)
                 .add_field(name='Uploader', value=uploader_value)
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


REVERSE_MAX_DURATION_SECONDS = 15 * 60


def build_ffmpeg_options(effects: dict[str, bool], duration_seconds: int) -> tuple[dict[str, Any], bool]:
    options = dict(YTDLSource.FFMPEG_OPTIONS)
    reverse_allowed = 0 < duration_seconds <= REVERSE_MAX_DURATION_SECONDS
    filters: list[str] = []
    if effects.get("reverse") and reverse_allowed:
        filters.append("areverse")
    if effects.get("nightcore"):
        filters.append("asetrate=48000*1.15,aresample=48000")
    if effects.get("slowmo"):
        filters.append("atempo=0.85")
    if effects.get("vaporwave"):
        filters.append("asetrate=48000*0.8,aresample=48000,aecho=0.8:0.9:1000|1800:0.9|0.9")
    if effects.get("bass"):
        filters.append("bass=g=15")
    if effects.get("lofi"):
        filters.append("acrusher=level_in=1:level_out=1:bits=8:mode=log")
    if effects.get("echo"):
        filters.append("aecho=0.8:0.5:1000|2000|3000:0.5|0.3|0.2")
    if effects.get("tremolo"):
        filters.append("apulsator=mode=sine:hz=2")
    if effects.get("fadein"):
        filters.append("afade=t=in:st=0:d=3")
    if filters:
        options["options"] = "-vn -b:a 192k -af " + ",".join(filters)
    return options, effects.get("reverse", False) and not reverse_allowed


class VoiceState:
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx

        self.current: Optional[Song] = None
        self.voice: Optional[discord.VoiceClient] = None
        self.next = asyncio.Event()
        self.songs = SongQueue()

        self._loop = False
        self._volume = 1.0
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

        self.audio_player = asyncio.create_task(self.audio_player_task())

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
                    print("[Player] Idle timeout (180 s) — disconnecting voice")
                    asyncio.create_task(self.stop())
                    return

            if self.current is None:
                await asyncio.sleep(0)
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
                        if isinstance(source_metadata, YTDLSource):
                            source_metadata.update_data(fresh_data)
                except Exception as resolve_exc:
                    print(f"[Player] Stream URL re-resolve failed, falling back to cached URL: {resolve_exc}")
                    log_error("[Player] Stream URL re-resolve failed", resolve_exc)

            if not stream_url:
                stream_url = source_metadata.stream_url or source_metadata.data.get('url')
            if not stream_url:
                await self._send_player_error(channel, "No playable stream URL was returned for this track.")
                continue

            # Fix B: Use a flag so exception paths don't skip self.next.wait(), preventing queue desync.
            played = False
            try:
                effects = {
                    "reverse": self.reverse,
                    "nightcore": self.nightcore,
                    "slowmo": self.slowmo,
                    "vaporwave": self.vaporwave,
                    "bass": self.bass,
                    "lofi": self.lofi,
                    "echo": self.echo,
                    "tremolo": self.tremolo,
                    "fadein": self.fadein,
                }
                ffmpeg_options, reverse_skipped = build_ffmpeg_options(
                    effects, source_metadata.duration_seconds
                )
                if reverse_skipped:
                    await channel.send(
                        f"⚠️ Reverse was skipped because tracks must have a known duration of "
                        f"{REVERSE_MAX_DURATION_SECONDS // 60} minutes or less."
                    )

                if not self.voice:
                    await self._send_player_error(channel, "Voice connection dropped before playback started.")
                elif not self.voice.is_connected():
                    await self._send_player_error(channel, "Voice client is no longer connected.")
                else:
                    # Guard: clear any stale player state that discord.py
                    # may still think is active (see discord.py #8483).
                    if self.voice.is_playing() or self.voice.is_paused():
                        print("[Player] Clearing stale audio player before new track")
                        self.voice.stop()
                        await asyncio.sleep(0.15)

                    print(f"[Player] Starting playback: {source_metadata.title}")
                    source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_options)
                    playback_source = discord.PCMVolumeTransformer(source, volume=self._volume)

                    self.voice.play(playback_source, after=self.play_next_song)
                    self.current_started_at = time.monotonic()
                    self.songs_played += 1
                    self.history.append(self.current)
                    if len(self.history) > self.history_limit:
                        self.history.pop(0)
                    embed = self.current.create_embed()
                    if embed is not None:
                        try:
                            await channel.send(embed=embed)
                        except discord.Forbidden:
                            pass
                    played = True

            except FileNotFoundError:
                await self._send_player_error(channel, "ffmpeg is not installed or not in PATH.")
            except discord.ClientException as exc:
                print(f"[Player] ClientException during play: {exc}")
                await self._send_player_error(channel, f"Audio playback failed: {exc}")
            except Exception as exc:
                print(f"[Player] Unexpected error during play: {exc}")
                log_error("[Player] Unexpected error during play", exc)
                await self._send_player_error(channel, f"Unexpected playback failure: {exc}")

            if played:
                await self.next.wait()
                if self._playback_error:
                    await self._send_player_error(channel, f"Track playback error: {self._playback_error}")
                    self._playback_error = None

    def play_next_song(self, error=None):
        if error:
            print(f"[Player] Playback error reported: {error}")
            log_error("[Player] Playback error reported", error)
        self._playback_error = str(error) if error else None
        self.bot.loop.call_soon_threadsafe(self.next.set)

    def skip(self):
        self.skip_votes.clear()
        if self.is_playing and self.voice:
            self.voice.stop()

    def _clear_effects(self):
        """Clear all audio-effect flags without touching loop state."""
        self.nightcore = False
        self.slowmo = False
        self.vaporwave = False
        self.reverse = False
        self.bass = False
        self.lofi = False
        self.echo = False
        self.tremolo = False
        self.fadein = False

    def _reset_effects(self):
        """Reset loop and all audio-effect flags to defaults."""
        self._loop = False
        self._clear_effects()

    async def stop(self):
        self.songs.clear()
        self.current = None
        self.current_started_at = None
        self._reset_effects()

        if hasattr(self, "audio_player") and not self.audio_player.done():
            self.audio_player.cancel()

        if self.voice:
            if self.voice.is_playing() or self.voice.is_paused():
                self.voice.stop()
            try:
                await self.voice.disconnect()
            except Exception:
                pass
            self.voice = None


class Music(commands.Cog):
    MUSIC_COMMANDS = {
        'join', 'summon', 'leave', 'volume', 'now', 'pause', 'resume', 'stop', 'clear',
        'skip', 'queue', 'shuffle', 'remove', 'loop', 'play', 'lyrics', 'nightcore',
        'slowmo', 'vaporwave', 'reverse', 'bass', 'lofi', 'echo', 'tremolo', 'fadein',
        'effects', 'replay', 'history', 'playlist', 'votemode', 'mood', 'stats', 'nowbar',
        'play_spotify', 'bard', 'bidenblast',
    }
    VOICE_COMMANDS = {
        'leave', 'volume', 'pause', 'resume', 'stop', 'clear', 'skip', 'shuffle', 'remove',
        'loop', 'play', 'nightcore', 'slowmo', 'vaporwave', 'reverse', 'bass', 'lofi',
        'echo', 'tremolo', 'fadein', 'replay', 'votemode', 'mood', 'bard',
        'bidenblast',
    }

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_states = {}
        self.playlists_path = os.path.join(os.path.dirname(__file__), "playlists.json")
        self.playlists_lock = asyncio.Lock()
        self.disconnect_tasks: dict[int, asyncio.Task] = {}

    def _read_playlists(self, guild_id: int) -> dict[str, Any]:
        if not os.path.exists(self.playlists_path):
            return {"version": 2, "guilds": {}}
        try:
            with open(self.playlists_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if not isinstance(data, dict):
                raise ValueError("Playlist data must be a JSON object")
            if data.get("version") == 2 and isinstance(data.get("guilds"), dict):
                return data
            return {"version": 2, "guilds": {str(guild_id): data}}
        except Exception as exc:
            log_error("[playlists] Failed to read playlists", exc)
            return {"version": 2, "guilds": {}}

    def _write_playlists(self, data: dict[str, Any]) -> None:
        temporary_path = f"{self.playlists_path}.tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(temporary_path, self.playlists_path)
        except Exception as e:
            print(f"❌ [playlists] Failed to write playlists: {e}")
            log_error("[playlists] Failed to write playlists", e)
            raise

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if state and state.audio_player.done():
            # The audio_player_task has died (e.g. idle timeout).  The old
            # VoiceState is a zombie — its queue will never be consumed.
            # Replace it with a fresh one so new songs actually play.
            print(f"[VoiceState] Replacing dead VoiceState for guild {ctx.guild.id}")
            try:
                state.audio_player.cancel()
            except Exception:
                pass
            state = None
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state
        return state

    async def cog_unload(self):
        for state in self.voice_states.values():
            try:
                await state.stop()
            except Exception:
                pass
        self.voice_states.clear()
        for task in self.disconnect_tasks.values():
            if not task.done():
                task.cancel()
        self.disconnect_tasks.clear()

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage('This command can\'t be used in DM channels.')

        command_name = ctx.command.name if ctx.command else ""
        if command_name in self.MUSIC_COMMANDS and MUSIC_CHANNEL_ID is not None and ctx.channel.id != MUSIC_CHANNEL_ID:
            raise MusicChannelError()

        state = self.voice_states.get(ctx.guild.id)
        if command_name in self.VOICE_COMMANDS and state and state.voice and state.voice.channel:
            author_channel = getattr(getattr(ctx.author, "voice", None), "channel", None)
            if author_channel != state.voice.channel:
                raise VoiceChannelError()
        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        print(f"❌ [cog_command_error] {ctx.command}: {type(error).__name__}: {error}")
        log_error(f"[cog_command_error] {ctx.command}: {type(error).__name__}: {error}", error if isinstance(error, BaseException) else None)
        if isinstance(error, MusicChannelError):
            await ctx.send(f"❌ Use music commands in <#{MUSIC_CHANNEL_ID}> only.")
        elif isinstance(error, VoiceChannelError):
            await ctx.send("❌ Join my voice channel before controlling playback.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Slow down — this command is on cooldown. Try again in {error.retry_after:.1f}s.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument: `{error.param.name}`. Use `$help` for usage.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Invalid argument. Use `$help` for usage.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command cannot be used in DMs.")
        else:
            await ctx.send("❌ Something went wrong. Please try again.")

    @commands.command(name='help')
    async def _help(self, ctx: commands.Context):
        """Show an embedded command menu.

        Usage: $help
        """
        embed = (
            discord.Embed(
                title="🎸 Joe Barden Bot",
                description=(
                    "Joe Barden is your Discord music bard — queue tracks, "
                    "manage playlists, apply audio effects, and summon the AI bard.\n"
                    "All music commands work in the designated music channel only."
                ),
                color=discord.Color.blurple(),
            )
            .add_field(
                name="🎵 Queueing Music",
                value=(
                    "`$play <song, URL, or playlist>` — queue a track or playlist\n"
                    "`$join` — join your current voice channel\n"
                    "`$summon [#channel]` — move bot to a specific voice channel\n"
                    "`$leave` — disconnect and clear the queue\n"
                    "`$queue [page]` — browse the current queue (10 per page)\n"
                    "`$now` — show what's currently playing\n"
                    "`$nowbar` — live progress bar for the current track\n"
                    "`$history` — recently played tracks"
                ),
                inline=False,
            )
            .add_field(
                name="⏯️ Playback Controls",
                value=(
                    "`$pause` — pause playback\n"
                    "`$resume` — resume paused playback\n"
                    "`$skip` — vote to skip (or skip immediately if alone)\n"
                    "`$replay` — restart the current track from the beginning\n"
                    "`$loop on|off` — loop the current track\n"
                    "`$volume <0–100>` — set playback volume\n"
                    "`$stop` — stop playback and clear the queue\n"
                    "`$clear` — clear the queue without stopping the current track\n"
                    "`$shuffle` — randomly shuffle the queued tracks\n"
                    "`$remove <number>` — remove a specific track from the queue"
                ),
                inline=False,
            )
            .add_field(
                name="🎛️ Audio Effects",
                value=(
                    "`$effects` — show all available effects and their status\n"
                    "`$nightcore on|off` — speed up and pitch shift\n"
                    "`$slowmo on|off` — slow things down\n"
                    "`$vaporwave on|off` — slowed + reverb aesthetic\n"
                    "`$bass on|off` — heavy bass boost\n"
                    "`$lofi on|off` — crunchy lo-fi sound\n"
                    "`$echo on|off` — layered echo effect\n"
                    "`$tremolo on|off` — pulsing volume effect\n"
                    "`$fadein on|off` — smooth fade-in at track start\n"
                    "`$reverse on|off` — play audio backwards"
                ),
                inline=False,
            )
            .add_field(
                name="💾 Playlists & Discovery",
                value=(
                    "`$playlist save <name>` — save the current queue as a playlist\n"
                    "`$playlist load <name>` — load a saved playlist into the queue\n"
                    "`$playlist list` — list your own saved playlists\n"
                    "`$playlist view` — view all playlists saved by anyone\n"
                    "`$playlist delete <name>` — delete one of your playlists\n"
                    "`$mood <happy|chill|rage|focus>` — queue a mood-based preset\n"
                    "`$lyrics <artist - title>` — fetch lyrics for a song"
                ),
                inline=False,
            )
            .add_field(
                name="🤖 AI Bard",
                value=(
                    "`$bard <request>` — ask Joe to recommend and queue songs for you\n"
                    "`$ask <question>` — ask the bard anything\n"
                    "`$roastdj [@user]` — have Joe roast whoever's running the aux\n"
                    "`$aistats` — check daily AI usage\n"
                    "\n"
                    "⚠️ Please use AI commands responsibly — each request has a cost.\n"
                    "🎶 AI is unavailable while music is playing or queued."
                ),
                inline=False,
            )
            .add_field(
                name="🛠️ Utility",
                value=(
                    "`$usage` — quick how-to guide for new users\n"
                    "`$votemode on|off` — require a vote before skipping\n"
                    "`$stats` — bot uptime and playback stats\n"
                    "`$patchnotes` — latest changelog\n"
                    "`$patchnotes_long` — full version history"
                ),
                inline=False,
            )
            .set_footer(text="Joe Barden Bot — type $help for this menu at any time.")
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
    async def _summon(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        """Move the bot to a specific voice channel.

        Usage: $summon #voice-channel
        """
        if not channel and not ctx.author.voice:
            raise VoiceError('You need to be in a voice channel, or specify one.')

        destination = channel or ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)
            return

        ctx.voice_state.voice = await destination.connect()

    @commands.command(name='leave', aliases=['disconnect'])
    async def _leave(self, ctx: commands.Context):
        """Stop playback, clear queue, and disconnect.

        Usage: $leave
        Alias: $disconnect
        """
        if not ctx.voice_state.voice:
            return await ctx.send('Not connected to any voice channel.')

        # Cancel any pending auto-disconnect timer
        if ctx.guild.id in self.disconnect_tasks:
            task = self.disconnect_tasks.pop(ctx.guild.id, None)
            if task and not task.done():
                task.cancel()

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
    async def _pause(self, ctx: commands.Context):
        """Pause the current track.

        Usage: $pause
        """
        if ctx.voice_state.voice and (ctx.voice_state.is_playing or ctx.voice_state.voice.is_playing()):
            ctx.voice_state.voice.pause()
            await ctx.message.add_reaction('⏯️')

    @commands.command(name='resume')
    async def _resume(self, ctx: commands.Context):
        """Resume a paused track.

        Usage: $resume
        """
        if ctx.voice_state.voice and ctx.voice_state.voice.is_paused():
            ctx.voice_state.voice.resume()
            await ctx.message.add_reaction('▶️')

    @commands.command(name='stop')
    async def _stop(self, ctx: commands.Context):
        """Stop playback and clear queued tracks.

        Usage: $stop
        """
        ctx.voice_state.songs.clear()
        ctx.voice_state.loop = False

        if ctx.voice_state.is_playing:
            ctx.voice_state.voice.stop()
            await ctx.message.add_reaction('🛑')

    @commands.command(name='clear')
    async def _clear(self, ctx: commands.Context):
        """Clear the song queue without stopping current playback.

        Usage: $clear
        """
        if len(ctx.voice_state.songs) == 0:
            return await ctx.send('The queue is already empty.')

        ctx.voice_state.songs.clear()
        await ctx.message.add_reaction('🗑️')

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
    async def _loop(self, ctx: commands.Context, mode: str):
        """Enable or disable loop for the current track.

        Usage: $loop on
        Usage: $loop off
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $loop on|off")

        if not ctx.voice_state.is_playing:
            return await ctx.send('Nothing being played at the moment.')

        ctx.voice_state.loop = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.loop else "disabled"
        await ctx.send(f'🔁 Loop is now {state}.')

    @commands.command(name='play')
    @music_channel_only()
    async def _play(self, ctx: commands.Context, *, search: str):
        """Play a track from a query or URL.

        Usage: $play never gonna give you up
        Usage: $play <youtube-url>
        Usage: $play <youtube-playlist-url>  — queues up to 25 tracks
        Usage: $play <spotify-or-apple-music-url>
        Notes: Spotify/Apple links are resolved to a search query.
        """
        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)
        elif ctx.author.voice and ctx.voice_state.voice.channel != ctx.author.voice.channel:
            raise commands.CommandError('Im already in a voice channel. Even Im not that senile.')

        PLAYLIST_LIMIT = 25

        # --- Playlist path ---
        if is_playlist_url(search):
            status_msg = await ctx.send("📋 Detected playlist — fetching track list...")
            try:
                entries = await YTDLSource.extract_playlist_entries(search, limit=PLAYLIST_LIMIT)
            except YTDLError as exc:
                await status_msg.edit(content=f"❌ Could not read playlist: {exc}")
                return
            except Exception as exc:
                print(f"❌ [play] Playlist extraction error for {ctx.author} ({ctx.author.id}): {type(exc).__name__}: {exc}")
                log_error(f"[play] Playlist extraction error for {ctx.author} ({ctx.author.id})", exc)
                await status_msg.edit(content="❌ Unexpected error reading playlist. Try again.")
                return

            if not entries:
                await status_msg.edit(content="❌ Playlist appears empty or unsupported.")
                return

            capped = len(entries) >= PLAYLIST_LIMIT
            cap_note = f" (capped at {PLAYLIST_LIMIT})" if capped else ""
            await status_msg.edit(
                content=f"📋 Found **{len(entries)}** track(s){cap_note} — queuing now..."
            )

            for entry_url, entry_title in entries:
                source = YTDLSource.from_flat_entry(ctx, entry_url, entry_title)
                await ctx.voice_state.songs.put(Song(source))

            await status_msg.edit(content=f"✅ Queued **{len(entries)}** track(s) from playlist.")
            return

        # --- Single track path ---
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
                )
            except YTDLError as exc:
                await ctx.send(f"❌ Unable to queue track: {exc}")
                return
            except Exception as exc:
                print(f"❌ [play] Unexpected queue error for {ctx.author} ({ctx.author.id}): {type(exc).__name__}: {exc}")
                log_error(f"[play] Unexpected queue error for {ctx.author} ({ctx.author.id})", exc)
                await ctx.send("❌ Unexpected error while queuing that track. Try again.")
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
        
        ctx.voice_state.fadein = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.fadein else "disabled"
        await ctx.send(f"🎵 Fade-in is now {state}!")

    @commands.command(name='patchnotes')
    async def _patchnotes(self, ctx: commands.Context):
        """Show the latest patch notes in Discord.

        Usage: $patchnotes
        """
        try:
            patchnotes_path = os.path.join(os.path.dirname(__file__), "patchnotes.txt")
            with open(patchnotes_path, encoding="utf-8") as f:
                content = f.read().strip()

            blocks = _split_patchnote_blocks(content)
            if not blocks:
                await ctx.send("❌ No patch notes found.")
                return

            latest = blocks[0].strip()
            wrapped = f"```\n{latest}\n```"
            if len(wrapped) <= 1990:
                await ctx.send(wrapped)
            else:
                truncated = latest[:1900].rsplit("\n", 1)[0]
                await ctx.send(f"```\n{truncated}\n```\n*...truncated — use `$patchnotes_long` for full history.*")
        except FileNotFoundError:
            await ctx.send("❌ patchnotes.txt was not found.")

    @commands.command(name='patchnotes_long')
    async def _patchnotes_long(self, ctx: commands.Context):
        """Show the full version history across multiple messages, one version per message.

        Usage: $patchnotes_long
        """
        patchnotes_path = os.path.join(os.path.dirname(__file__), "patchnotes.txt")
        try:
            with open(patchnotes_path, encoding="utf-8") as f:
                content = f.read().strip()

            blocks = _split_patchnote_blocks(content)
            if not blocks:
                await ctx.send("❌ No patch notes found.")
                return

            await ctx.send(f"📜 **Full version history — {len(blocks)} release(s):**")
            for block in blocks:
                block = block.strip()
                wrapped = f"```\n{block}\n```"
                if len(wrapped) <= 1990:
                    await ctx.send(wrapped)
                else:
                    chunk = block[:1900].rsplit("\n", 1)[0]
                    await ctx.send(f"```\n{chunk}\n```\n*...entry truncated*")
        except FileNotFoundError:
            await ctx.send("❌ patchnotes.txt was not found.")

    def _track_ai_usage(self, user_id: int):
        """Track AI usage for rate limiting."""
        today = datetime.now().date()
        if today not in AI_USAGE:
            AI_USAGE[today] = {}
            for stale_key in [k for k in AI_USAGE if k != today]:
                del AI_USAGE[stale_key]
        AI_USAGE[today][user_id] = AI_USAGE[today].get(user_id, 0) + 1

    @commands.command(name='usage')
    async def _usage(self, ctx: commands.Context):
        """Show simple usage instructions.

        Usage: $usage
        """
        embed = discord.Embed(
            title="🎵 How to Use Joe Barden Bot",
            description="Quick start guide for the bot!",
            color=discord.Color.green()
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
                "**$bard play me something for a rainy day** - AI queues songs for you\n"
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

    @commands.command(name='effects')
    async def _effects(self, ctx: commands.Context):
        """Show all available audio effects and their current state.

        Usage: $effects
        """
        vs = ctx.voice_state
        effects = [
            ("Nightcore",  vs.nightcore, "Speed up (+15%)"),
            ("Slow-mo",    vs.slowmo,    "Slow down (-15%)"),
            ("Vaporwave",  vs.vaporwave, "Slowed + echo aesthetic"),
            ("Reverse",    vs.reverse,   "Play backwards"),
            ("Bass Boost", vs.bass,      "Heavy bass boost"),
            ("Lo-Fi",      vs.lofi,      "Crunchy vintage sound"),
            ("Echo",       vs.echo,      "Triple echo chamber"),
            ("Tremolo",    vs.tremolo,   "Pulsing tremolo"),
            ("Fade-In",    vs.fadein,    "Smooth 3s fade-in"),
        ]
        lines = "\n".join(
            f"{'✅' if active else '⬜'} **{name}** — {desc}"
            for name, active, desc in effects
        )
        embed = discord.Embed(title="🎛️ Audio Effects", description=lines, color=discord.Color.purple())
        embed.set_footer(text="Use $<effect> on|off to toggle. Multiple effects can be active at once.")
        await ctx.send(embed=embed)

    @commands.command(name='ask')
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def _ask(self, ctx: commands.Context, *, question: str):
        """Ask the AI a question.

        Usage: $ask What's the meaning of life?
        """
        if not gemini_model and not _groq_client:
            return await ctx.send("❌ AI is not available. Check API configuration.")

        if self._ai_quota_check() and not _groq_client:
            return await ctx.send(BARD_QUOTA_MESSAGE)

        if self._is_music_active(ctx):
            return await ctx.send(
                "🎶 *The Bard doesn't look up from his lute.*\n"
                "I'm in the middle of something, friend — these strings don't play themselves. "
                "Here's the deal, not a joke — come back when the music's done."
            )

        if not self._check_ai_limit(ctx.author.id):
            return await ctx.send("⏰ You've reached your daily AI limit. Try again tomorrow!")

        warning = self._warn_if_approaching_limit(ctx.author.id)
        if warning:
            await ctx.send(warning)

        try:
            await ctx.send("🤔 Thinking...")
            music_context = self._get_music_context(ctx)
            safe_question = self._sanitize_ai_input(question)
            enhanced_question = f"Music Context: {music_context}\n\nUser Question: {safe_question}" if music_context else safe_question
            response_text = await asyncio.to_thread(generate_content, enhanced_question, BARD_SYSTEM_PROMPT)
            self._track_ai_usage(ctx.author.id)
            if len(response_text) <= 1900:
                await ctx.send(f"🎶 **Joe Barden the Bard says:**\n{response_text}")
            else:
                chunks = [response_text[i:i+1900] for i in range(0, len(response_text), 1900)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await ctx.send(f"🎶 **Joe Barden the Bard says (part {i+1}/{len(chunks)}):**\n{chunk}")
                    else:
                        await ctx.send(f"🎶 **Part {i+1}/{len(chunks)}:**\n{chunk}")
                        await asyncio.sleep(1)
        except GeminiQuotaError:
            await ctx.send(BARD_QUOTA_MESSAGE)
        except Exception as e:
            print(f"❌ [ask] Unhandled AI error for user {ctx.author} ({ctx.author.id}): {type(e).__name__}: {e}")
            log_error(f"[ask] Unhandled AI error for user {ctx.author} ({ctx.author.id})", e)
            await ctx.send("❌ *The Bard pauses mid-verse, blinking.* My words failed me there — try again in a moment.")

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

    @commands.command(name='replay')
    async def _replay(self, ctx: commands.Context):
        """Replay the current track from the beginning.

        Usage: $replay
        """
        if not ctx.voice_state.current:
            return await ctx.send('Nothing is currently playing.')

        ctx.voice_state.songs.put_front(Song(ctx.voice_state.current.source))
        ctx.voice_state.skip()
        await ctx.message.add_reaction('🔄')

    @commands.command(name='history')
    async def _history(self, ctx: commands.Context):
        """Show recently played tracks.

        Usage: $history
        """
        if not ctx.voice_state.history:
            return await ctx.send('No history yet.')

        lines = '\n'.join(
            f'`{i}.` {s.source.title}'
            for i, s in enumerate(reversed(ctx.voice_state.history), start=1)
        )
        embed = discord.Embed(title="🕘 Recently Played", description=lines, color=discord.Color.dark_gold())
        await ctx.send(embed=embed)

    @commands.command(name='playlist')
    async def _playlist(self, ctx: commands.Context, action: str, *, name: str = ""):
        """Manage saved playlists.

        Usage: $playlist save <name>
        Usage: $playlist load <name>
        Usage: $playlist list
        Usage: $playlist view
        Usage: $playlist delete <name>
        """
        action = action.lower().strip()
        uid = str(ctx.author.id)
        async with self.playlists_lock:
            data = self._read_playlists(ctx.guild.id)
            guild_playlists = data["guilds"].setdefault(str(ctx.guild.id), {})

        if action == "list":
            user_playlists = guild_playlists.get(uid, {})
            if not user_playlists:
                return await ctx.send("You have no saved playlists.")
            names = ", ".join(f"`{n}`" for n in user_playlists)
            return await ctx.send(f"Your playlists: {names}")

        if action == "view":
            if not guild_playlists:
                return await ctx.send("No playlists have been saved yet.")
            lines = []
            for user_id, user_playlists in guild_playlists.items():
                if not user_playlists:
                    continue
                owner = ctx.guild.get_member(int(user_id))
                owner_name = owner.mention if owner else f"<@{user_id}>"
                for pname, tracks in user_playlists.items():
                    lines.append(f"• **{pname}** by {owner_name} ({len(tracks)} tracks)")
            if not lines:
                return await ctx.send("No playlists have been saved yet.")
            embed = discord.Embed(
                title="🎵 Saved Playlists",
                description="\n".join(lines[:25]),
                color=discord.Color.blurple()
            )
            if len(lines) > 25:
                embed.set_footer(text=f"...and {len(lines) - 25} more playlists")
            return await ctx.send(embed=embed)

        if not name:
            return await ctx.send(f"Usage: $playlist {action} <name>")

        if action == "save":
            if not ctx.voice_state.current and len(ctx.voice_state.songs) == 0:
                return await ctx.send("Nothing in the queue to save.")
            tracks: list[str] = []
            if ctx.voice_state.current:
                tracks.append(ctx.voice_state.current.source.url or ctx.voice_state.current.source.title)
            for song in ctx.voice_state.songs:
                tracks.append(song.source.url or song.source.title)
            async with self.playlists_lock:
                data = self._read_playlists(ctx.guild.id)
                guild_playlists = data["guilds"].setdefault(str(ctx.guild.id), {})
                guild_playlists.setdefault(uid, {})[name] = tracks
                self._write_playlists(data)
            return await ctx.send(f"✅ Saved **{name}** ({len(tracks)} tracks).")

        if action == "load":
            tracks = guild_playlists.get(uid, {}).get(name)
            if not tracks:
                return await ctx.send(f"No playlist named **{name}**.")
            if ctx.voice_state.voice and ctx.voice_state.voice.channel:
                author_channel = getattr(getattr(ctx.author, "voice", None), "channel", None)
                if author_channel != ctx.voice_state.voice.channel:
                    return await ctx.send("❌ Join my voice channel before loading a playlist.")
            else:
                await ctx.invoke(self._join)

            for query in tracks:
                source = YTDLSource.from_flat_entry(ctx, query, query)
                await ctx.voice_state.songs.put(Song(source))
            return await ctx.send(f"✅ Loaded **{name}** — {len(tracks)} tracks queued.")

        if action == "delete":
            async with self.playlists_lock:
                data = self._read_playlists(ctx.guild.id)
                guild_playlists = data["guilds"].setdefault(str(ctx.guild.id), {})
                if uid not in guild_playlists or name not in guild_playlists[uid]:
                    return await ctx.send(f"No playlist named **{name}**.")
                del guild_playlists[uid][name]
                if not guild_playlists[uid]:
                    del guild_playlists[uid]
                self._write_playlists(data)
            return await ctx.send(f"🗑️ Deleted playlist **{name}**.")

        await ctx.send("Unknown action. Use: save | load | list | delete")

    @commands.command(name='votemode')
    async def _votemode(self, ctx: commands.Context, mode: str):
        """Enable or disable vote-skip mode.

        Usage: $votemode on|off
        """
        mode_normalized = mode.strip().lower()
        if mode_normalized not in {"on", "off"}:
            return await ctx.send("Usage: $votemode on|off")

        ctx.voice_state.vote_mode = mode_normalized == "on"
        state = "enabled" if ctx.voice_state.vote_mode else "disabled"
        await ctx.send(f"🗳️ Vote-skip mode is now {state}.")

    @commands.command(name='mood')
    @music_channel_only()
    async def _mood(self, ctx: commands.Context, *, mood: str):
        """Queue a preset mood playlist.

        Usage: $mood happy|chill|rage|focus
        """
        mood_key = mood.lower().strip()
        playlist = MOOD_QUERIES.get(mood_key)
        if not playlist:
            available = ", ".join(f"`{k}`" for k in MOOD_QUERIES)
            return await ctx.send(f"Unknown mood. Available: {available}")

        if not ctx.voice_state.voice:
            await ctx.invoke(self._join)

        added = 0
        async with ctx.typing():
            for query in playlist:
                try:
                    source = await YTDLSource.create_source(
                        ctx, query, loop=asyncio.get_running_loop()
                    )
                    await ctx.voice_state.songs.put(Song(source))
                    added += 1
                except Exception:
                    continue

        await ctx.send(f"🎵 Queued **{added}** tracks for mood: **{mood_key}**!")

    @commands.command(name='roastdj')
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def _roastdj(self, ctx: commands.Context, roast_target: discord.Member = None):
        """Generate an AI-powered roast of the current DJ.

        Usage: $roastdj
        Usage: $roastdj @user
        """
        if roast_target is None:
            if ctx.voice_state.current:
                roast_target = ctx.voice_state.current.requester
            else:
                roast_target = ctx.author

        if (not gemini_model and not _groq_client) or (self._ai_quota_check() and not _groq_client):
            return await ctx.send(f"{roast_target.mention}, {random.choice(DJ_ROASTS)}")

        try:
            current_track = ctx.voice_state.current.source.title if ctx.voice_state.current else "some questionable music"
            safe_display_name = self._sanitize_ai_input(roast_target.display_name, max_length=100)
            roast_prompt = (
                f'Generate a short, funny, light-hearted roast (under 200 characters) of a Discord DJ '
                f'named {safe_display_name} who is currently playing "{current_track}". '
                f'Be creative and musical-themed.'
            )
            roast_text = await asyncio.to_thread(generate_content, roast_prompt, BARD_SYSTEM_PROMPT)
            await ctx.send(f"{roast_target.mention}, {roast_text}")
        except GeminiQuotaError:
            await ctx.send(f"{roast_target.mention}, {random.choice(DJ_ROASTS)}")
        except Exception as e:
            print(f"❌ [roastdj] Unhandled AI error for user {ctx.author} ({ctx.author.id}): {type(e).__name__}: {e}")
            log_error(f"[roastdj] Unhandled AI error for user {ctx.author} ({ctx.author.id})", e)
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
            .add_field(name="Active Effect", value=(
                "Nightcore" if ctx.voice_state.nightcore else
                "Slow-mo"   if ctx.voice_state.slowmo   else
                "Vaporwave" if ctx.voice_state.vaporwave else
                "Reverse"   if ctx.voice_state.reverse   else
                "Bass Boost"if ctx.voice_state.bass      else
                "Lo-Fi"     if ctx.voice_state.lofi      else
                "Echo"      if ctx.voice_state.echo      else
                "Tremolo"   if ctx.voice_state.tremolo   else
                "Fade-In"   if ctx.voice_state.fadein    else
                "None"
            ), inline=True)
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
        filled = int((elapsed / duration) * bar_len)
        bar = "█" * filled + "-" * (bar_len - filled)

        await ctx.send(
            f"Now Playing: **{ctx.voice_state.current.source.title}**\n"
            f"`{bar}` {format_clock(elapsed)} / {format_clock(duration)}"
        )

    @commands.command(name='play_spotify')
    async def _play_spotify(self, ctx: commands.Context):
        """Redirects to $play — Spotify links are already supported.

        Usage: $play_spotify
        """
        await ctx.send(
            "ℹ️ Direct Spotify playback isn't needed — `$play` already handles Spotify links!\n"
            "Just paste your Spotify track or album URL directly: `$play <spotify-url>`"
        )

    @staticmethod
    def _sanitize_ai_input(text: str, max_length: int = 500) -> str:
        """Sanitize user input before passing to the AI.

        - Truncates to max_length to prevent context stuffing.
        - Strips common prompt injection patterns that attempt to override
          the system instruction (e.g. 'ignore previous instructions').
        """
        text = text.strip()[:max_length]
        injection_patterns = [
            r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?|context)",
            r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)",
            r"you\s+are\s+now\s+(?!joe|barden)",
            r"new\s+persona",
            r"act\s+as\s+(?!joe|barden|a\s+bard|the\s+bard)",
            r"pretend\s+(you\s+are|to\s+be)\s+(?!joe|barden|a\s+bard|the\s+bard)",
            r"system\s*:\s*",
            r"<\s*system\s*>",
            r"\[\s*system\s*\]",
        ]
        for pattern in injection_patterns:
            text = re.sub(pattern, "[removed]", text, flags=re.IGNORECASE)
        return text

    def _is_music_active(self, ctx: commands.Context) -> bool:
        """Return True if music is currently playing, paused, or queued."""
        vs = ctx.voice_state
        if vs.current is not None:
            return True
        if len(vs.songs) > 0:
            return True
        if vs.voice and vs.voice.is_paused():
            return True
        return False

    def _ai_quota_check(self) -> bool:
        """Return True if Gemini is hard-blocked due to quota exhaustion."""
        global _gemini_quota_exhausted_at
        if _gemini_quota_exhausted_at is None:
            return False
        if time.monotonic() - _gemini_quota_exhausted_at >= QUOTA_RETRY_SECONDS:
            _gemini_quota_exhausted_at = None
            return False
        return True

    def _warn_if_approaching_limit(self, user_id: int) -> Optional[str]:
        """Return a warning string if the user or global pool is running low, else None."""
        today = datetime.now().date()
        if today not in AI_USAGE:
            return None
        user_requests = AI_USAGE[today].get(user_id, 0)
        total_requests = sum(AI_USAGE[today].values())
        remaining_user = max(0, 50 - user_requests)
        remaining_total = max(0, DAILY_LIMIT - total_requests)
        if remaining_user <= 5:
            return f"⚠️ Only {remaining_user} AI request(s) left for you today, friend."
        if remaining_total <= 50:
            return f"⚠️ Running low on AI requests globally — only {remaining_total} remain for the day."
        return None

    def _check_ai_limit(self, user_id: int) -> bool:
        """Check if user is within AI usage limits. Returns True if within limits."""
        today = datetime.now().date()
        if today not in AI_USAGE:
            AI_USAGE[today] = {}
            for stale_key in [k for k in AI_USAGE if k != today]:
                del AI_USAGE[stale_key]
        user_requests = AI_USAGE[today].get(user_id, 0)
        total_requests = sum(AI_USAGE[today].values())
        return user_requests < 50 and total_requests < DAILY_LIMIT

    def _get_music_context(self, ctx: commands.Context) -> str:
        """Get current music context string for AI prompts."""
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

    @commands.command(name='bard')
    @music_channel_only()
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def _bard(self, ctx: commands.Context, *, request: str):
        """Ask Joe Barden the Bard for music — he'll ramble, then queue songs for you.

        Usage: $bard play me something for a rainy day
        Usage: $bard I want epic battle music
        Usage: $bard what goes well with late night vibes?
        """
        if not gemini_model and not _groq_client:
            return await ctx.send("❌ The Bard's tongue is silent. Check API configuration.")

        if self._ai_quota_check() and not _groq_client:
            return await ctx.send(BARD_QUOTA_MESSAGE)

        if self._is_music_active(ctx):
            return await ctx.send(
                "🎶 *The Bard raises one finger without breaking his strum.*\n"
                "Not now — I'm playing. No malarkey, wait for the music to finish and then ask me. C'mon."
            )

        if not self._check_ai_limit(ctx.author.id):
            return await ctx.send("⏰ The Bard's run dry for the day. Try again tomorrow!")

        warning = self._warn_if_approaching_limit(ctx.author.id)
        if warning:
            await ctx.send(warning)

        try:
            await ctx.send("🎶 *The Bard strums his lute thoughtfully...*")

            safe_request = self._sanitize_ai_input(request)
            bard_prompt = f"""A tavern-goer approaches and requests: "{safe_request}"

Respond in full bardic character. Ramble about the music you are about to recommend.
Then provide QUEUE_SONGS with 3-5 real, searchable song titles that match the request."""

            response_text = await asyncio.to_thread(generate_content, bard_prompt, BARD_SYSTEM_PROMPT)
            self._track_ai_usage(ctx.author.id)

            # Parse QUEUE_SONGS line out before displaying
            display_text = response_text
            songs_to_queue: list[str] = []
            if "QUEUE_SONGS:" in response_text:
                parts = response_text.split("QUEUE_SONGS:", 1)
                display_text = parts[0].strip()
                raw_songs = parts[1].split("\n")[0].strip()
                songs_to_queue = [s.strip() for s in raw_songs.split("|") if s.strip()]

            # Send the bard's response
            if len(display_text) <= 1900:
                await ctx.send(f"🎶 **Joe Barden the Bard:**\n{display_text}")
            else:
                chunks = [display_text[i:i+1900] for i in range(0, len(display_text), 1900)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await ctx.send(f"🎶 **Joe Barden the Bard (part {i+1}/{len(chunks)}):**\n{chunk}")
                    else:
                        await ctx.send(f"🎶 **Part {i+1}/{len(chunks)}:**\n{chunk}")
                    await asyncio.sleep(1)

            # Queue the songs if any were returned
            if songs_to_queue:
                if not ctx.voice_state.voice:
                    await ctx.invoke(self._join)

                await ctx.send(f"🎵 *The Bard queues {len(songs_to_queue)} track(s) for the realm...*")
                added = 0
                async with ctx.typing():
                    for song_title in songs_to_queue:
                        try:
                            source = await YTDLSource.create_source(
                                ctx,
                                f"ytsearch:{song_title}",
                                loop=asyncio.get_running_loop(),
                            )
                            await ctx.voice_state.songs.put(Song(source))
                            added += 1
                        except Exception:
                            continue
                if added:
                    await ctx.send(f"✅ *The Bard nods — {added} song(s) added to the queue.*")
            else:
                await ctx.send("*(The Bard didn't name any specific songs — use `$play` to queue your own!)*")

        except GeminiQuotaError:
            await ctx.send(BARD_QUOTA_MESSAGE)
        except Exception as e:
            print(f"❌ [bard] Unhandled AI error for user {ctx.author} ({ctx.author.id}): {type(e).__name__}: {e}")
            log_error(f"[bard] Unhandled AI error for user {ctx.author} ({ctx.author.id})", e)
            await ctx.send("❌ *The Bard stumbles on his own lute strings.* Something went sideways — try again in a moment.")

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

    @commands.command(name='bidenblast', hidden=True)
    async def _bidenblast(self, ctx: commands.Context):
        await _trigger_biden_blast(self, ctx)


async def _trigger_biden_blast(cog: 'Music', ctx: commands.Context) -> None:
    """Core logic for the BidenBlast easter egg.

    Called by both the $bidenblast command and the 'biden blast' text trigger.
    Resolves the .wav one directory above the bot file.
    - If music is playing or queued: injects the .wav at the front of the queue
      (plays next, silently — no embed, no chat noise).
    - If bot is in voice but idle: plays immediately.
    - If bot is not in voice but user is: joins and plays immediately.
    - If neither: silent no-op (easter egg stays hidden).
    """
    blast_path = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "BidenBlast.wav")
    )
    if not os.path.isfile(blast_path):
        return

    voice_state = cog.get_voice_state(ctx)

    if not voice_state.voice or not voice_state.voice.is_connected():
        if not ctx.author.voice or not ctx.author.voice.channel:
            return
        try:
            voice_state.voice = await ctx.author.voice.channel.connect()
        except Exception:
            return

    local_source = LocalAudioSource(blast_path, ctx)

    if voice_state.is_playing or len(voice_state.songs) > 0:
        song = Song(local_source)
        voice_state.songs.put_front(song)
    else:
        try:
            ffmpeg_source = discord.FFmpegPCMAudio(blast_path)
            playback_source = discord.PCMVolumeTransformer(ffmpeg_source, volume=voice_state.volume)
            voice_state.voice.play(playback_source, after=voice_state.play_next_song)
            voice_state.current_started_at = time.monotonic()
        except Exception as exc:
            log_error("[BidenBlast] Playback failed", exc)


def random_guild_emoji(guild: Optional[discord.Guild]):
    if guild and guild.emojis:
        return random.choice(guild.emojis)
    return None


class JoeBardenBot(commands.Bot):
    async def setup_hook(self) -> None:
        await self.add_cog(Music(self))
        self.gemini_validation_task = asyncio.create_task(_validate_gemini_model())


bot = JoeBardenBot(command_prefix='$', description='Im Joe Barden and I approve this message.', intents=intents, help_command=None)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if DEBUG_MODE and message.guild is not None:
        print(f"{message.guild.id} | {message.channel.id} | {message.author.name}: {message.content}")

    await bot.process_commands(message)

    content = message.content.lower()

    if "biden blast" in content:
        cog = bot.get_cog("Music")
        if cog:
            ctx = await bot.get_context(message)
            await _trigger_biden_blast(cog, ctx)
        return

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
        
async def _disconnect_after_delay(guild_id: int, delay: int = 60) -> None:
    """Wait for delay seconds, then disconnect the bot from the voice channel."""
    await asyncio.sleep(delay)
    cog = bot.get_cog("Music")
    if cog and guild_id in cog.voice_states:
        voice_state = cog.voice_states[guild_id]
        if voice_state.voice and voice_state.voice.channel:
            # Double-check we're still alone
            channel = voice_state.voice.channel
            non_bot_members = [m for m in channel.members if not m.bot]
            if not non_bot_members:
                print(f"[Auto-Disconnect] Disconnecting from guild {guild_id} after {delay}s alone")
                await voice_state.stop()
                cog.voice_states.pop(guild_id, None)
        # Clean up the task reference
        cog.disconnect_tasks.pop(guild_id, None)


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Handle voice state changes to auto-disconnect when alone."""
    cog = bot.get_cog("Music")
    if not cog:
        return

    # Check if the bot is in any voice channel in this guild
    voice_state = cog.voice_states.get(member.guild.id)
    if not voice_state or not voice_state.voice:
        return

    bot_channel = voice_state.voice.channel
    if not bot_channel:
        return

    # Check if anyone (non-bot) is left in the channel with the bot
    non_bot_members = [m for m in bot_channel.members if not m.bot]

    if not non_bot_members:
        # Bot is alone - start disconnect timer if not already running
        if member.guild.id not in cog.disconnect_tasks or cog.disconnect_tasks[member.guild.id].done():
            print(f"[Auto-Disconnect] Starting {60}s timer for guild {member.guild.id}")
            cog.disconnect_tasks[member.guild.id] = asyncio.create_task(_disconnect_after_delay(member.guild.id))
    else:
        # Someone is with the bot - cancel any pending disconnect
        if member.guild.id in cog.disconnect_tasks:
            task = cog.disconnect_tasks.pop(member.guild.id, None)
            if task and not task.done():
                task.cancel()
                print(f"[Auto-Disconnect] Cancelled timer for guild {member.guild.id} — someone rejoined")


@bot.event
async def on_ready():
    print('Logged in as:\n{0.user.name}\n{0.user.id}'.format(bot))
    print(f"Connected to {len(bot.guilds)} server(s):")
    for guild in bot.guilds:
        print(f"  - {guild.name} (ID: {guild.id})")

if __name__ == "__main__":
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set. Add it to your environment or .env file.")
    bot.run(token)