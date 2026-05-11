# JoeBardenBot3

A Discord music bot with audio effects, AI integration, and way too many features. Uses discord.py, yt-dlp for audio, Google Gemini AI, and falls back to Groq when Gemini hits its limits.

## What it does

### Music stuff
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

> Only one effect can be active at a time. Switching effects auto-disables the previous one.

### AI stuff
- **General Q&A**: Ask anything with `$ask` — knows what song is playing
- **Music DJ**: Get song recommendations with `$bard`
- **Roast DJ**: AI roasts whoever's controlling the queue with `$roastdj`
- **Usage tracking**: Check AI usage with `$aistats`
- **Dual AI**: Uses Gemini first, falls back to Groq when needed

### Other stuff
- **Joe Biden theme**: Presidential quotes and responses
- **Lyrics**: Get song lyrics
- **Stats**: Track uptime and playback metrics
- **Vote skipping**: Skip songs democratically
- **Progress bar**: Live progress with `$nowbar`

---

## Setup

### What you need
- Python 3.10 or higher
- FFmpeg installed and in PATH
- A Discord bot token
- A Google Gemini API key (free tier works)

### Getting it running

1. **Clone the repo**
```bash
git clone <repository-url>
cd JoeBarden
```

2. **Setup Venv**
```bash
python -m venv .venv
source .venv/bin/activate
```

2. **Install deps**
```bash
pip install -r requirements.txt
```

3. **Set up your .env file**

Create a `.env` file in the project root. See [Environment Variables](#-environment-variables) for the full list.

```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
```

4. **Run the bot**
```bash
python JoeBardenBot3.py
```

---

## Environment Variables

Create a `.env` file in the project root with these:

| Variable | Required | What it does |
|---|---|---|
| `DISCORD_TOKEN` | ✅ Yes | Your Discord bot token. Get one from the [Discord Developer Portal](https://discord.com/developers/applications). |
| `GEMINI_API_KEY` | ✅ Yes (for AI) | Google Gemini API key. Free tier at [Google AI Studio](https://aistudio.google.com/). Powers `$ask`, `$bard`, `$roastdj`. |
| `GROQ_API_KEY` | ⚪ Optional | Groq API key for AI fallback when Gemini is down. Free key at [console.groq.com](https://console.groq.com). |
| `MUSIC_CHANNEL_ID` | ⚪ Optional | Channel ID to restrict music commands to one channel. If unset, commands work anywhere. |
| `YTDL_COOKIES_PATH` | ⚪ Optional | Path to a `cookies.txt` file for yt-dlp. Needed for age-restricted YouTube content. If unset, bot looks for `cookies.txt` in the project root. |

### Getting the keys

**Discord Bot Token:**
1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create new application → Bot → Reset Token
3. Enable **Message Content Intent** under Privileged Gateway Intents
4. Invite bot to your server with OAuth2 URL Generator (scopes: `bot`, permissions below)

**Gemini API Key:**
1. Go to [aistudio.google.com](https://aistudio.google.com/)
2. Sign in with Google → Get API key
3. Free tier has plenty of daily requests, no billing needed

**Groq API Key (optional - AI fallback):**
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up with email (~60 seconds, no billing needed)
3. Create API key under API Keys

---

## Commands

### Music
| Command | What it does |
|---|---|
| `$play <song/url>` | Play a song or URL (YouTube, Spotify, Apple Music) |
| `$skip` | Skip current song (vote-based when vote mode is on) |
| `$queue` | Show what's queued up |
| `$now` | Show what's playing now |
| `$pause` | Pause playback |
| `$resume` | Resume paused playback |
| `$volume <0-100>` | Set volume |
| `$loop on/off` | Loop the current track |
| `$stop` | Stop and clear the queue |
| `$clear` | Clear queue without stopping |
| `$shuffle` | Shuffle the queue |
| `$remove <index>` | Remove a track from queue |
| `$replay` | Restart current track |
| `$history` | Show recently played songs |
| `$leave` | Leave voice channel |
| `$join` | Join your voice channel |
| `$summon` | Move to a specific voice channel |

### Playlists
| Command | What it does |
|---|---|
| `$playlist save <name>` | Save current queue as a playlist |
| `$playlist load <name>` | Load a saved playlist |
| `$playlist list` | Show all saved playlists |
| `$playlist delete <name>` | Delete a playlist |

### Audio effects
| Command | What it does |
|---|---|
| `$effects` | Show all effects and what's active |
| `$nightcore on/off` | Speed up music (+15%, higher pitch) |
| `$slowmo on/off` | Slow down music (-15%, lower pitch) |
| `$vaporwave on/off` | Slowed + echo aesthetic effect |
| `$reverse on/off` | Play music backwards |
| `$bass on/off` | Heavy +15dB bass boost |
| `$lofi on/off` | Crunchy vintage sound |
| `$echo on/off` | Triple echo with decay |
| `$tremolo on/off` | Pulsing volume modulation |
| `$fadein on/off` | 3-second fade-in on track start |

### AI commands
| Command | What it does |
|---|---|
| `$ask <question>` | Ask the AI anything — knows what's playing |
| `$bard <request>` | Ask the AI DJ for song recommendations |
| `$roastdj [@user]` | Get an AI roast of whoever's controlling the queue |
| `$aistats` | Check AI usage and model status |

### Other commands
| Command | What it does |
|---|---|
| `$help` | Show the command menu |
| `$usage` | Simple how-to guide |
| `$lyrics <artist - song>` | Get song lyrics |
| `$stats` | Show bot uptime and stats |
| `$nowbar` | Show live progress bar for current track |
| `$mood <mood>` | Queue a mood playlist (`happy`, `chill`, `rage`, `focus`) |
| `$votemode on/off` | Turn vote-based skipping on/off |
| `$patchnotes` | Show latest patch notes in Discord |

---

## AI stuff

### How it works

The bot uses **Google Gemini** as its main AI. If Gemini is down (quota hit, outage), it automatically switches to **Groq** (Llama/Mixtral models). You only need `GEMINI_API_KEY` for AI to work — `GROQ_API_KEY` is optional but helps with reliability.

AI model priority:
1. `gemini-2.5-flash` (primary)
2. `gemini-2.5-flash-lite` (Gemini fallback)
3. Groq `llama-3.3-70b` → `llama-3.1-8b` → `mixtral-8x7b` (if `GROQ_API_KEY` is set)

### General Assistant (`$ask`)
Ask anything. The bot knows what song is playing and what's queued:
```
$ask What's the meaning of life?
$ask Explain quantum physics simply
$ask What does this song's lyrics mean?
```

### Music DJ (`$bard`)
Ask the AI DJ for song recommendations. It queues songs directly:
```
$bard What should I play for studying?
$bard Suggest some upbeat party bangers
$bard Give me 5 tracks similar to what's playing now
```

### Roast DJ (`$roastdj`)
Get an AI roast of the current DJ, or tag someone:
```
$roastdj
$roastdj @username
```

### Usage Monitoring (`$aistats`)
Check AI model status and your daily usage.

---

## Audio effects

| Effect | Command | What it does |
|---|---|---|
| Nightcore | `$nightcore on` | Speed +15%, higher pitch. Good for parties and workouts. |
| Slow-mo | `$slowmo on` | Speed -15%, lower pitch. Good for chilling. |
| Vaporwave | `$vaporwave on` | Slowed + echo + reverb. Late-night aesthetic vibes. |
| Reverse | `$reverse on` | Plays music backwards. Party games and easter eggs. |
| Bass Boost | `$bass on` | Heavy +15dB bass. EDM, hip-hop, heavy drops. |
| Lo-Fi | `$lofi on` | Crunchy vintage bit-crushed sound. Study sessions. |
| Echo | `$echo on` | Triple echo with decay. Dreamy atmosphere. |
| Tremolo | `$tremolo on` | Pulsing volume modulation. Rave vibes. |
| Fade-In | `$fadein on` | 3-second smooth fade-in. Clean track starts, DJ sets. |

Use `$effects` to see all effects and which one is active.

---

## Bot permissions

These Discord permissions are needed when inviting the bot:

| Permission | Why |
|---|---|
| Connect | Join voice channels |
| Speak | Play audio |
| Read Messages / View Channels | Read commands |
| Send Messages | Respond to commands |
| Embed Links | Show now-playing embeds |
| Add Reactions | React to commands (skip votes, etc.) |

---

## FFmpeg setup

FFmpeg needs to be installed and in your system PATH.

**Windows:**
```bash
# Download from https://ffmpeg.org/download.html and add to PATH
ffmpeg -version  # Verify
```

**Linux:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

---

## Party mode ideas

### Study session
```
$mood focus
$slowmo on
$bard Recommend some focus music
$ask Help me understand this topic
```

### Party time
```
$mood happy
$nightcore on
$bard Suggest party bangers
$shuffle
```

### Chill vibes
```
$mood chill
$vaporwave on
$play lofi beats
$bard What's good for a late night wind-down?
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
- Age-restricted YouTube content needs a `cookies.txt` file (see `YTDL_COOKIES_PATH`)

**AI not responding:**
- Verify `GEMINI_API_KEY` is set correctly in `.env`
- Check usage with `$aistats`
- If Gemini is at quota, set `GROQ_API_KEY` for automatic fallback

**Commands not working:**
- Make sure the command prefix is `$`
- Verify bot has Message Content Intent enabled in Developer Portal
- Check if `MUSIC_CHANNEL_ID` is set — if so, music commands only work in that channel

### Error messages
| Message | What it means |
|---|---|
| `❌ ffmpeg is not installed` | FFmpeg not found in PATH |
| `⏰ You've reached your daily AI limit` | AI quota exhausted — wait for daily reset or add Groq fallback |
| `❌ Use music commands in #channel only` | `MUSIC_CHANNEL_ID` is set — use the designated channel |
| `⚠️ No cookie file found` | Age-restricted content will fail — add `cookies.txt` or set `YTDL_COOKIES_PATH` |

---

## Project structure

```
JoeBarden/
├── JoeBardenBot3.py     # Main bot source
├── .env                 # Environment variables (not committed)
├── requirements.txt     # Python dependencies
├── playlists.json       # Saved playlists per server
├── patchnotes.txt       # Bot changelog
├── cookies.txt          # yt-dlp cookies (optional, not committed)
├── errors.txt           # Runtime error log (auto-created, rotates at 100MB)
└── README.md            # This file
```

---

## Dependencies

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

---

## License

Copyright LPSC LLC. All rights reserved.
