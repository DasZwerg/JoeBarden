# JoeBardenBot3

A Discord music bot with audio effects, AI integration, and way too many features. Uses discord.py, yt-dlp for audio, Google Gemini AI, and falls back to Groq when Gemini hits its limits.

---

## What it does

### Music
- **Plays audio**: YouTube, Spotify, and Apple Music links work
- **Smart playback**: Automatically fixes dead streams and reconnects
- **Queue management**: Full control over what's playing, with history
- **Playlists**: Save, load, and delete playlists for each server
- **Mood playlists**: Pre-made playlists for different vibes

### Audio effects
- **Nightcore**: Speed up music by 15% for energy
- **Slow-mo**: Slow down by 15% to chill
- **Vaporwave**: Slowed + echo for aesthetic vibes
- **Reverse**: Play music backwards
- **Bass Boost**: Heavy bass for parties
- **Lo-Fi**: Crunchy vintage sound for studying
- **Echo**: Triple echo for atmosphere
- **Tremolo**: Pulsing effect for raves
- **Fade-In**: Smooth fade-in for clean starts

> Multiple effects can be stacked at once. Use `$effects` to see what's active.

### AI
- **General Q&A**: Ask anything with `$ask` — knows what song is playing
- **Music DJ**: Get song recommendations with `$bard`
- **Roast DJ**: AI roasts whoever's controlling the queue with `$roastdj`
- **Usage tracking**: Check AI usage with `$aistats`
- **Dual AI**: Uses Gemini first, falls back to Groq when needed

### Other
- **Joe Biden theme**: Presidential quotes and responses
- **Lyrics**: Get song lyrics
- **Stats**: Track uptime and playback metrics
- **Vote skipping**: Skip songs democratically
- **Progress bar**: Live progress with `$nowbar`

---

## Installation & Setup

### Prerequisites

- Python 3.10 or higher
- FFmpeg installed and in PATH
- A Discord bot token
- A Google Gemini API key (free tier works)

### 1. Clone and install

```bash
git clone <repository-url>
cd JoeBarden
```

### 2. Set up a virtual environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

### 2a. Tmux recommended for hosting POTS server + Barden on the same device. It's a huge pain in the ass otherwise.

**macOS:**
```bash
brew install tmux
```

**Linux:**
```bash
sudo apt install tmux
```
To actually use tmux, type "tmux" after installation, it will open a virtual window so you can run one of the py scripts. Then press ctrl+b then d to exit the session without closing it. You can then type "tmux" again to start a second session, start the other py script, then ctrl+b then d to exit again. To reconnect to one of the sessions, you can find the number of the session with "tmux ls" then "tmux attach-session -t 0/1/2/etc". |
I'm fairly certain there are alternatives to tmux, it's just my preference. You will need to activate the venv per tmux session, so keep that in mind.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Install FFmpeg

FFmpeg must be installed and available on your system PATH.

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows:**
Download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html), extract, and add the `bin` folder to your system PATH.

Verify with:
```bash
ffmpeg -version
```

### 5. Get your API keys

**Discord Bot Token (required):**
1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create new application → Bot → Reset Token
3. Enable **Message Content Intent** under Privileged Gateway Intents
4. Invite the bot using the OAuth2 URL Generator (scopes: `bot`, permissions listed below)

**Gemini API Key (required for AI):**
1. Go to [aistudio.google.com](https://aistudio.google.com/)
2. Sign in with Google → Get API key
3. Free tier works — no billing needed

**Groq API Key (optional — AI fallback):**
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up (~60 seconds, no billing needed)
3. Create a key under API Keys

**yt-dlp Cookies (optional — age-restricted content):**

Some YouTube content (age restricted videos, regional content) requires authenticated cookies. The recommended approach uses yt-dlp directly rather than a browser extension:

```bash
# Extract cookies from your logged-in browser (Chrome example)
yt-dlp --cookies-from-browser chrome --cookies cookies.txt "https://www.youtube.com"
```

This exports all browser cookies for all sites to `cookies.txt`. Keep this file private. Other supported browsers: `firefox`, `edge`, `safari`, `brave`, `chromium`.

Alternatively, use the [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) extension for Chrome, or [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/) for Firefox. The file must be in Netscape/Mozilla format. The first line should read `# Netscape HTTP Cookie File`.

Save the file as `cookies.txt` in the project root, or point `YTDL_COOKIES_PATH` at it.

### 6. Configure the bgutil POT provider (recommended)

`bgutil-ytdlp-pot-provider` generates proof of origin tokens (POT) that make yt-dlp's YouTube requests appear more legitimate to Google's bot detection. Without it, requests from server IPs are more likely to hit 403 errors or the "Sign in to confirm you're not a bot" block.

The plugin Python package is already listed in `requirements.txt` and installed via `pip install -r requirements.txt`. You still need to set up the token generation backend separately.

**Requirements:** Node.js ≥ 20 or Deno ≥ 2.0.0, plus `git`.

**Option A — HTTP server (recommended):**

```bash
# Clone the provider repo (replace 1.3.1 with the latest release tag)
git clone --single-branch --branch 1.3.1 \
  https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git
cd bgutil-ytdlp-pot-provider/server

# With Node.js:
npm ci
npx tsc
node build/main.js

# Or with Deno:
deno install --allow-scripts=npm:canvas --frozen
cd node_modules && deno run \
  --allow-env --allow-net --allow-ffi=. --allow-read=. ../src/main.ts
```

The server runs on `http://127.0.0.1:4416` by default. Once it's running, yt-dlp will automatically detect and use it — no additional configuration needed in the bot.

To run on a different port:
```bash
node build/main.js --port 8080
# Then pass to yt-dlp manually:
# --extractor-args "youtubepot-bgutilhttp:base_url=http://127.0.0.1:8080"
```

**Option B — Docker (simplest):**

```bash
docker run --name bgutil-provider -d --init brainicism/bgutil-ytdlp-pot-provider
```

Exposes port 4416. No Node.js/Deno required.

**Option C — Script mode (no server required):**

After cloning the repo as above, the plugin will invoke the script directly per yt-dlp call. This is slower and not suitable for high concurrency, but requires no running server. Just ensure `node` or `deno` is in PATH.

See the [full bgutil README](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) for advanced configuration.

### 7. Configure environment variables

Create a `.env` file in the project root:

```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
GROQ_API_KEY=your_groq_api_key        # optional
MUSIC_CHANNEL_ID=123456789            # optional
YTDL_COOKIES_PATH=/path/to/cookies.txt  # optional
```

| Variable | Required | What it does |
|---|---|---|
| `DISCORD_TOKEN` | ✅ Yes | Your Discord bot token |
| `GEMINI_API_KEY` | ✅ Yes (for AI) | Powers `$ask`, `$bard`, `$roastdj` |
| `GROQ_API_KEY` | ⚪ Optional | AI fallback when Gemini is at quota |
| `MUSIC_CHANNEL_ID` | ⚪ Optional | Restricts music commands to one channel |
| `YTDL_COOKIES_PATH` | ⚪ Optional | Path to cookies.txt for age-restricted content |

### 8. Bot permissions

These Discord permissions are required when inviting the bot:

| Permission | Why |
|---|---|
| Connect | Join voice channels |
| Speak | Play audio |
| Read Messages / View Channels | Read commands |
| Send Messages | Respond to commands |
| Embed Links | Show now-playing embeds |
| Add Reactions | React to commands (skip votes, etc.) |

### 9. Dependencies

| Package | What it does |
|---|---|
| `discord.py` | Discord bot framework |
| `yt-dlp` | Audio extraction from YouTube and other sources |
| `bgutil-ytdlp-pot-provider` | yt-dlp proof-of-origin token provider (YouTube anti-bot) |
| `python-dotenv` | `.env` file loading |
| `PyNaCl` | Discord voice encryption |
| `google-genai` | Google Gemini AI client |
| `openai` | OpenAI-compatible client used for Groq API fallback |
| `davey` | DAVE protocol library for Discord E2EE audio/video |

### 10. Run the bot

```bash
python JoeBardenBot3.py
```

On startup, after the Gemini / AI integration status, the bot prints the list of servers it is installed on.

#### Debug mode

Run with the `-debug` flag to print every non-bot message the bot detects in each server:

```bash
python JoeBardenBot3.py -debug
```

Each line is formatted as:

```
serverID | channelID | username: message here
```

This is useful for verifying the bot can see messages and for troubleshooting command detection.

---

## How it works

### Bot pipeline

The full request lifecycle from Discord message to audio output:

```
Discord user → $play <input>
  │
  ├─ Input classification
  │    ├─ Spotify URL → oEmbed API → artist/title string → YouTube search
  │    ├─ Apple Music URL → iTunes Lookup API → artist/title string → YouTube search
  │    ├─ YouTube playlist URL → yt-dlp flat extraction → list of video URLs
  │    ├─ YouTube URL → passed directly to yt-dlp
  │    └─ Plain text → treated as YouTube search query (ytsearch:)
  │
  ├─ yt-dlp metadata extraction (async, run in thread executor)
  │    ├─ Proof-of-origin token injected by bgutil-ytdlp-pot-provider plugin
  │    ├─ Browser-spoofed User-Agent headers to reduce bot fingerprinting
  │    ├─ Randomized request delay (1–3s) between calls
  │    └─ cookiefile injected if YTDL_COOKIES_PATH is set
  │
  ├─ Song object queued into asyncio.Queue (SongQueue)
  │
  └─ audio_player_task (background asyncio coroutine, one per guild)
       ├─ Dequeues next Song, re-resolves a fresh stream URL at play time
       │    (stream URLs from YouTube expire; re-resolving prevents stale URL errors)
       ├─ Builds FFmpeg filter chain from all active effect flags
       │    └─ e.g. reverse → nightcore → bass → echo → joined as -af filter string
       ├─ discord.FFmpegPCMAudio streams audio over UDP via Discord voice gateway
       │    ├─ FFmpeg reconnects on drop (-reconnect 1 -reconnect_streamed 1)
       │    └─ PCMVolumeTransformer applies per-guild volume in real time
       └─ After track ends → next.set() → loop iterates to next queued Song
```

Each guild gets its own `VoiceState` instance with an independent queue, player task, effect flags, and volume. State is isolated, multiple guilds can run concurrently.

### AI

The bot uses **Google Gemini** as its primary AI, because it has one of the higher daily quotas on the free tier. If Gemini is down or hits quota, it automatically switches to **Groq** (Llama/Mixtral models), not to be mistaken with Grok, which I will never use. You only need `GEMINI_API_KEY` for AI to work — `GROQ_API_KEY` is optional but improves reliability.

AI model priority:
1. `gemini-2.5-flash` (primary)
2. `gemini-2.5-flash-lite` (Gemini fallback)
3. Groq `llama-3.3-70b` → `llama-3.1-8b` → `mixtral-8x7b` (if `GROQ_API_KEY` is set)

### Audio effects

Effects are applied as an FFmpeg filter chain at playback time. Multiple effects can be stacked simultaneously — each one is independently toggled with `$<effect> on|off`. Effects apply to the next track played, not the current one mid-stream.

### Music link resolution

- **YouTube**: Played directly via yt-dlp
- **Spotify**: Link resolved to a search query via Spotify oEmbed, then searched on YouTube
- **Apple Music**: Track/album ID extracted and looked up via the iTunes catalog API, then searched on YouTube

---

## Commands

### Music
| Command | What it does |
|---|---|
| `$play <song/url>` | Play a song or URL (YouTube, Spotify, Apple Music) |
| `$skip` | Skip current song (vote-based when vote mode is on) |
| `$queue` | Show what's queued up |
| `$now` | Show what's playing now |
| `$nowbar` | Show live progress bar for current track |
| `$history` | Show recently played songs |
| `$pause` | Pause playback |
| `$resume` | Resume paused playback |
| `$volume <0-100>` | Set volume |
| `$loop on/off` | Loop the current track |
| `$stop` | Stop and clear the queue |
| `$clear` | Clear queue without stopping |
| `$shuffle` | Shuffle the queue |
| `$remove <index>` | Remove a specific track from the queue by number |
| `$replay` | Restart current track |
| `$leave` | Leave voice channel and clear queue |
| `$join` | Join your voice channel |
| `$summon` | Move to a specific voice channel |

### Playlists
| Command | What it does |
|---|---|
| `$playlist save <name>` | Save current queue as a named playlist |
| `$playlist load <name>` | Load a saved playlist into the queue |
| `$playlist list` | Show your own saved playlists |
| `$playlist view` | Show all playlists saved by anyone |
| `$playlist delete <name>` | Delete one of your playlists |

### Audio effects
| Command | What it does |
|---|---|
| `$effects` | Show all effects and which are currently active |
| `$nightcore on/off` | Speed +15%, higher pitch |
| `$slowmo on/off` | Speed -15%, lower pitch |
| `$vaporwave on/off` | Slowed + echo aesthetic |
| `$reverse on/off` | Play audio backwards |
| `$bass on/off` | Heavy +15dB bass boost |
| `$lofi on/off` | Crunchy vintage bit-crushed sound |
| `$echo on/off` | Triple echo with decay |
| `$tremolo on/off` | Pulsing volume modulation |
| `$fadein on/off` | 3-second fade-in on track start |

Multiple effects can be active at the same time. Stack them freely.

### AI commands
| Command | What it does |
|---|---|
| `$bard <request>` | Ask the AI DJ for song recommendations — queues them directly |
| `$ask <question>` | Ask the AI anything — knows what's currently playing |
| `$roastdj [@user]` | Get an AI roast of whoever's controlling the queue |
| `$aistats` | Check AI usage and model status |

### Utility
| Command | What it does |
|---|---|
| `$help` | Show the command menu |
| `$usage` | Simple how-to guide for new users |
| `$lyrics <artist - song>` | Get song lyrics |
| `$stats` | Show bot uptime and playback stats |
| `$mood <mood>` | Queue a mood preset (`happy`, `chill`, `rage`, `focus`) |
| `$votemode on/off` | Require a vote before skipping |
| `$patchnotes` | Show the latest patch notes in Discord |

### Party mode ideas

**Study session:**
```
$mood focus
$lofi on
$bard Recommend some focus music
```

**Party time:**
```
$mood happy
$nightcore on
$bass on
$bard Suggest party bangers
$shuffle
```

**Chill vibes:**
```
$mood chill
$vaporwave on
$play lofi beats
$bard What's good for a late night wind-down?
```

**Rave mode:**
```
$bass on
$echo on
$tremolo on
$mood rage
```

---

## Troubleshooting

### Common problems

**Bot won't join voice channel:**
- Check bot has Connect and Speak permissions
- Make sure bot isn't already in another channel on the server

**Music not playing:**
- Verify FFmpeg is installed: `ffmpeg -version`
- Check the URL is valid and public
- Age restricted YouTube content needs a `cookies.txt` file (see `YTDL_COOKIES_PATH`)

**AI not responding:**
- Verify `GEMINI_API_KEY` is set correctly in `.env`
- Check usage with `$aistats`
- If Gemini is at quota, set `GROQ_API_KEY` for automatic fallback

**Audio effects not working:**
- Effects apply to the next track played, not the current one
- Use `$effects` to confirm which effects are active
- Multiple effects can be stacked — use `$stop` then `$play` to reload with active effects

**Commands not working:**
- Make sure the command prefix is `$`
- Verify bot has Message Content Intent enabled in the Developer Portal
- Check if `MUSIC_CHANNEL_ID` is set — if so, music commands only work in that channel

### Error messages
| Message | What it means |
|---|---|
| `❌ ffmpeg is not installed` | FFmpeg not found in PATH |
| `⏰ You've reached your daily AI limit` | AI quota exhausted — wait for daily reset or add Groq fallback |
| `❌ Use music commands in #channel only` | `MUSIC_CHANNEL_ID` is set — use the designated channel |
| `⚠️ No cookie file found` | Age-restricted content will fail — add `cookies.txt` or set `YTDL_COOKIES_PATH` |

### AI Disclosure
I have used AI to suppliment code, bugfix, and fix bugs. 
