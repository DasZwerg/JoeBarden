# JoeBardenBot3 - Discord Music Bot with AI

A feature-rich Discord music bot with audio effects, AI integration, and party features. Built with discord.py, powered by yt-dlp, Google Gemini AI, and a Groq fallback for uninterrupted responses.

## 🎵 Features

### Core Music Functionality
- **High-Quality Audio**: Supports YouTube, Spotify, and Apple Music links
- **Smart Playback**: Automatic stream re-resolution and reconnection
- **Queue Management**: Full queue control with history tracking
- **Playlists**: Save, load, list, and delete custom per-server playlists
- **Mood Playlists**: Pre-configured playlists for different vibes

### 🎛️ Audio Effects
- **Nightcore**: Speed up music by 15% for high energy
- **Slow-mo**: Slow down music by 15% for chill vibes
- **Vaporwave**: Aesthetic slowed + echo effect
- **Reverse**: Play music backwards
- **Bass Boost**: Heavy bass for party vibes
- **Lo-Fi**: Crunchy vintage sound for study sessions
- **Echo**: Triple echo chamber for atmospheric effects
- **Tremolo**: Pulsing tremolo effect for rave vibes
- **Fade-In**: Smooth fade-in for professional transitions

> Only one effect can be active at a time. Switching effects auto-disables the previous one.

### 🤖 AI Assistant Integration
- **General Q&A**: Ask anything with `$ask` — context-aware of the current song and queue
- **Music DJ**: Get AI-curated song recommendations with `$bard`
- **Roast DJ**: AI-powered roast of whoever's controlling the queue with `$roastdj`
- **Usage Tracking**: Monitor AI usage with `$aistats`
- **Dual AI Engine**: Gemini (primary) with automatic Groq fallback when Gemini hits quota

### 🎮 Other Features
- **Joe Biden Theme**: Presidential quotes and responses
- **Lyrics Fetching**: Get song lyrics on demand
- **Statistics**: Track bot uptime and playback metrics
- **Vote Skipping**: Democratic song skipping
- **Now Playing Bar**: Live progress bar with `$nowbar`

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10 or higher
- FFmpeg installed and in PATH
- A Discord bot token
- A Google Gemini API key (free tier available)

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd JoeBarden
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up environment variables**

Create a `.env` file in the project root. See [Environment Variables](#-environment-variables) below for the full list.

```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
```

4. **Run the bot**
```bash
python JoeBardenBot3.py
```

---

## 🔑 Environment Variables

Create a `.env` file in the project root with the following keys:

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ Yes | Your Discord bot token. Get one from the [Discord Developer Portal](https://discord.com/developers/applications). |
| `GEMINI_API_KEY` | ✅ Yes (for AI) | Google Gemini API key. Free tier available at [Google AI Studio](https://aistudio.google.com/). Powers `$ask`, `$bard`, `$roastdj`. |
| `GROQ_API_KEY` | ⚪ Optional | Groq API key for AI fallback when Gemini is unavailable. Free key at [console.groq.com](https://console.groq.com). |
| `MUSIC_CHANNEL_ID` | ⚪ Optional | Channel ID to restrict music commands to a specific channel. If unset, commands work in any channel. |
| `YTDL_COOKIES_PATH` | ⚪ Optional | Path to a `cookies.txt` file for yt-dlp. Required for age-restricted or login-gated YouTube content. If unset, the bot looks for `cookies.txt` in the project root automatically. |

### Getting Your Keys

**Discord Bot Token:**
1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create a new application → Bot → Reset Token
3. Enable **Message Content Intent** under Privileged Gateway Intents
4. Invite the bot to your server with the OAuth2 URL Generator (scopes: `bot`, permissions below)

**Gemini API Key:**
1. Go to [aistudio.google.com](https://aistudio.google.com/)
2. Sign in with a Google account → Get API key
3. Free tier: generous daily quota, no billing required

**Groq API Key (optional — AI fallback):**
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up with email (~60 seconds, no billing required)
3. Create an API key under API Keys

---

## 📋 Commands

### Music Commands
| Command | Description |
|---|---|
| `$play <song/url>` | Play a track from a search query or URL (YouTube, Spotify, Apple Music) |
| `$skip` | Skip the current song (vote-based when vote mode is on) |
| `$queue` | Show the current queue |
| `$now` | Show the currently playing track |
| `$pause` | Pause playback |
| `$resume` | Resume paused playback |
| `$volume <0-100>` | Set playback volume |
| `$loop on/off` | Loop the current track |
| `$stop` | Stop playback and clear the queue |
| `$clear` | Clear the queue without stopping current playback |
| `$shuffle` | Shuffle the queue |
| `$remove <index>` | Remove a track from the queue by position |
| `$replay` | Restart the current track from the beginning |
| `$history` | Show recently played tracks |
| `$leave` | Disconnect the bot from the voice channel |
| `$join` | Join your current voice channel |
| `$summon` | Move the bot to a specific voice channel |

### Playlist Commands
| Command | Description |
|---|---|
| `$playlist save <name>` | Save the current queue as a named playlist |
| `$playlist load <name>` | Load a saved playlist into the queue |
| `$playlist list` | List all saved playlists for this server |
| `$playlist delete <name>` | Delete a saved playlist |

### Audio Effects
| Command | Description |
|---|---|
| `$effects` | Show all effects and their current on/off state |
| `$nightcore on/off` | Speed up music (+15%, higher pitch) |
| `$slowmo on/off` | Slow down music (-15%, lower pitch) |
| `$vaporwave on/off` | Slowed + echo aesthetic effect |
| `$reverse on/off` | Play music backwards |
| `$bass on/off` | Heavy +15dB bass boost |
| `$lofi on/off` | Crunchy vintage bit-crushed sound |
| `$echo on/off` | Triple echo chamber with decay |
| `$tremolo on/off` | Pulsing sine-wave volume modulation |
| `$fadein on/off` | 3-second smooth fade-in on track start |

### AI Commands
| Command | Description |
|---|---|
| `$ask <question>` | Ask the AI anything — it knows what's currently playing |
| `$bard <request>` | Ask the AI DJ for music recommendations |
| `$roastdj [@user]` | Get an AI roast of whoever is controlling the queue |
| `$aistats` | Check AI usage and model status |

### Utility Commands
| Command | Description |
|---|---|
| `$help` | Show the full command menu |
| `$usage` | Simple how-to guide |
| `$lyrics <artist - song>` | Fetch song lyrics |
| `$stats` | Show bot uptime and playback statistics |
| `$nowbar` | Show a live progress bar for the current track |
| `$mood <mood>` | Queue a preset mood playlist (`happy`, `chill`, `rage`, `focus`) |
| `$votemode on/off` | Enable or disable vote-based skipping |
| `$patchnotes` | Show the latest patch notes in Discord |

---

## 🤖 AI Features

### How It Works

The bot uses **Google Gemini** as its primary AI engine. If Gemini is unavailable (quota exhausted, outage), it automatically falls back to **Groq** (Llama/Mixtral models). You only need `GEMINI_API_KEY` to use AI — `GROQ_API_KEY` is optional but recommended for reliability.

AI model priority:
1. `gemini-2.5-flash` (primary)
2. `gemini-2.5-flash-lite` (Gemini fallback)
3. Groq `llama-3.3-70b` → `llama-3.1-8b` → `mixtral-8x7b` (if `GROQ_API_KEY` is set)

### General Assistant (`$ask`)
Ask anything. The bot is aware of the current song and queue when answering:
```
$ask What's the meaning of life?
$ask Explain quantum physics simply
$ask What does this song's lyrics mean?
```

### Music DJ (`$bard`)
Ask the AI DJ for song recommendations. It will queue suggestions directly:
```
$bard What should I play for studying?
$bard Suggest some upbeat party bangers
$bard Give me 5 tracks similar to what's playing now
```

### Roast DJ (`$roastdj`)
Get an AI-generated roast of the current DJ, or tag someone specific:
```
$roastdj
$roastdj @username
```

### Usage Monitoring (`$aistats`)
Check AI model status, availability, and your usage for the day.

---

## 🎛️ Audio Effects Guide

| Effect | Command | Description |
|---|---|---|
| Nightcore | `$nightcore on` | Speed +15%, higher pitch. Great for parties and workouts. |
| Slow-mo | `$slowmo on` | Speed -15%, lower pitch. Great for chill sessions. |
| Vaporwave | `$vaporwave on` | Slowed + echo + reverb. Aesthetic late-night vibes. |
| Reverse | `$reverse on` | Plays music backwards. Party games and easter eggs. |
| Bass Boost | `$bass on` | Heavy +15dB bass. EDM, hip-hop, heavy drops. |
| Lo-Fi | `$lofi on` | Crunchy vintage bit-crushed sound. Study sessions. |
| Echo | `$echo on` | Triple echo chamber with decay. Dreamy atmosphere. |
| Tremolo | `$tremolo on` | Pulsing sine-wave volume modulation. Rave vibes. |
| Fade-In | `$fadein on` | 3-second smooth fade-in. Clean track starts, DJ sets. |

Use `$effects` to see all effects and which one is currently active.

---

## 🔧 Bot Permissions

Required Discord permissions when inviting the bot:

| Permission | Why |
|---|---|
| Connect | Join voice channels |
| Speak | Play audio |
| Read Messages / View Channels | Read commands |
| Send Messages | Respond to commands |
| Embed Links | Show rich now-playing embeds |
| Add Reactions | React to commands (skip votes, etc.) |

---

## 🖥️ FFmpeg Setup

FFmpeg must be installed and available in your system PATH.

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

## 🎭 Party Mode Ideas

### Study Session
```
$mood focus
$slowmo on
$bard Recommend some focus music
$ask Help me understand this topic
```

### Party Time
```
$mood happy
$nightcore on
$bard Suggest party bangers
$shuffle
```

### Chill Vibes
```
$mood chill
$vaporwave on
$play lofi beats
$bard What's good for a late night wind-down?
```

---

## 🛠️ Troubleshooting

### Common Issues

**Bot won't join voice channel:**
- Check bot has Connect and Speak permissions in the channel
- Ensure the bot isn't already in a different channel on the server

**Music not playing:**
- Verify FFmpeg is installed: `ffmpeg -version`
- Check the URL is valid and publicly accessible
- Age-restricted YouTube content requires a `cookies.txt` file (see `YTDL_COOKIES_PATH`)

**AI not responding:**
- Verify `GEMINI_API_KEY` is set correctly in `.env`
- Check usage with `$aistats`
- If Gemini is at quota, set `GROQ_API_KEY` for automatic fallback

**Commands not working:**
- Confirm the command prefix is `$`
- Verify the bot has Message Content Intent enabled in the Developer Portal
- Check if `MUSIC_CHANNEL_ID` is set — if so, music commands only work in that channel

### Error Messages
| Message | Cause |
|---|---|
| `❌ ffmpeg is not installed` | FFmpeg not found in PATH |
| `⏰ You've reached your daily AI limit` | AI quota exhausted — wait for daily reset or add Groq fallback |
| `❌ Use music commands in #channel only` | `MUSIC_CHANNEL_ID` is set — use the designated channel |
| `⚠️ No cookie file found` | Age-restricted content will fail — add `cookies.txt` or set `YTDL_COOKIES_PATH` |

---

## 📝 Project Structure

```
JoeBarden/
├── JoeBardenBot3.py     # Main bot source
├── .env                 # Environment variables (not committed)
├── requirements.txt     # Python dependencies
├── playlists.json       # Saved per-server playlists
├── patchnotes.txt       # Bot changelog
├── cookies.txt          # yt-dlp cookies (optional, not committed)
├── errors.txt           # Runtime error log (auto-created, rotates at 100MB)
└── README.md            # This file
```

---

## � Dependencies

| Package | Purpose |
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

## 📄 License

Copyright LPSC LLC. All rights reserved.
