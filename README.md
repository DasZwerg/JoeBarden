# JoeBardenBot - Discord Music Bot with AI

A feature-rich Discord music bot with audio effects, AI integration, and party features. Built with discord.py and powered by yt-dlp and Google Gemini AI.

## 🎵 Features

### Core Music Functionality
- **High-Quality Audio**: Supports YouTube, Spotify, and Apple Music links
- **Smart Playback**: Automatic reconnection and stream recovery
- **Queue Management**: Full queue control with history tracking
- **Playlists**: Save and load custom playlists
- **Mood Playlists**: Pre-configured playlists for different vibes

### 🎛️ Audio Effects (Party Tricks!)
- **Nightcore**: Speed up music by 15% for high energy
- **Slow-mo**: Slow down music by 15% for chill vibes
- **Vaporwave**: Aesthetic slowed + echo effect
- **Reverse**: Play music backwards for hidden messages
- **Bass Boost**: Heavy bass for party vibes
- **Lo-Fi**: Crunchy vintage sound for study sessions
- **Echo**: Triple echo chamber for atmospheric effects
- **Tremolo**: Pulsing tremolo effect for rave vibes
- **Fade-In**: Smooth fade-in for professional transitions

### 🤖 AI Assistant Integration
- **General Q&A**: Ask anything with `$ask`
- **Music DJ**: Get music recommendations with `$dj`
- **Private Chat**: One-on-one AI conversations with `$chat`
- **Usage Tracking**: Monitor AI usage with `$aistats`

### 🎮 Bot Features
- **Joe Biden Theme**: Fun presidential quotes and responses
- **Voice Channel Auto-Join**: Automatically joins your voice channel
- **Lyrics Fetching**: Get song lyrics on demand
- **Statistics**: Track bot usage and performance
- **Vote Skipping**: Democratic song skipping

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- FFmpeg (must be installed and in PATH)
- Discord bot token

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
Create a `.env` file with:
```env
DISCORD_TOKEN=your_discord_bot_token
MUSIC_CHANNEL_ID=your_music_channel_id
GEMINI_API_KEY=your_gemini_api_key
```

4. **Run the bot**
```bash
python JoeBardenBot3.py
```

## 📋 Commands

### Music Commands
- `$play <song/url>` - Play music
- `$skip` - Skip current song
- `$queue` - Show current queue
- `$now` - Show current song
- `$volume <0-100>` - Set volume
- `$loop on/off` - Loop current track
- `$stop` - Stop playback (admin)
- `$leave` - Disconnect (admin)

### Audio Effects
- `$effects` - Show all effects
- `$nightcore on/off` - Speed up music
- `$slowmo on/off` - Slow down music
- `$vaporwave on/off` - Aesthetic effect
- `$reverse on/off` - Play backwards
- `$bass on/off` - Heavy bass boost
- `$lofi on/off` - Crunchy vintage sound
- `$echo on/off` - Triple echo chamber
- `$tremolo on/off` - Pulsing tremolo
- `$fadein on/off` - Smooth fade-in

### AI Commands
- `$ask <question>` - Ask AI anything
- `$dj <request>` - Get music recommendations
- `$chat` - Start private AI conversation
- `$aistats` - Check AI usage limits

### Utility Commands
- `$help` - Show all commands
- `$usage` - Simple how-to guide
- `$lyrics <artist - song>` - Get lyrics
- `$history` - Show recently played
- `$stats` - Show bot statistics

## 🎛️ Audio Effects Guide

### Nightcore (`$nightcore on`)
- Perfect for: Parties, high energy moments
- Effect: Speed +15%, higher pitch
- Use case: Dance sessions, workout music

### Slow-mo (`$slowmo on`)
- Perfect for: Chill sessions, study time
- Effect: Speed -15%, lower pitch
- Use case: Relaxing, dramatic effect

### Vaporwave (`$vaporwave on`)
- Perfect for: Aesthetic vibes, late night
- Effect: Slowed + echo + reverb
- Use case: Ambient, dreamy atmosphere

### Reverse (`$reverse on`)
- Perfect for: Party games, easter eggs
- Effect: Plays music backwards
- Use case: Finding "hidden messages"

### Bass Boost (`$bass on`)
- Perfect for: Parties, EDM, hip-hop
- Effect: Heavy +15dB bass boost
- Use case: Dance sessions, heavy drops

### Lo-Fi (`$lofi on`)
- Perfect for: Study sessions, background music
- Effect: Crunchy vintage bit-crushed sound
- Use case: Relaxing, nostalgic vibes

### Echo (`$echo on`)
- Perfect for: Atmospheric, ambient sessions
- Effect: Triple echo chamber with decay
- Use case: Dreamy, spacey atmosphere

### Tremolo (`$tremolo on`)
- Perfect for: Raves, electronic music
- Effect: Pulsing sine-wave volume modulation
- Use case: Rave vibes, wobble effect

### Fade-In (`$fadein on`)
- Perfect for: Professional transitions
- Effect: 3-second smooth volume fade-in
- Use case: Clean track starts, DJ sets

## 🤖 AI Features

### General Assistant (`$ask`)
Ask anything from general knowledge to help with homework:
```
$ask What's the meaning of life?
$ask Explain quantum physics simply
$ask Help me write a poem
```

### Music DJ (`$dj`)
Get personalized music recommendations:
```
$dj What should I play for studying?
$dj Suggest some upbeat party music
$dj What genre is this current song?
```

### Private Chat (`$chat`)
Start a one-on-one conversation in DMs:
```
$chat  # Bot will DM you
# Then chat privately in DMs
!endchat  # End the conversation
```

### Usage Monitoring (`$aistats`)
Track your AI usage to stay within limits:
- **Free tier**: 50 requests per user per day
- **Global limit**: 1,500 requests per day
- **Rate limiting**: Prevents abuse

## 🔧 Configuration

### Environment Variables
- `DISCORD_TOKEN`: Your Discord bot token
- `MUSIC_CHANNEL_ID`: Channel ID for music commands (optional)
- `GEMINI_API_KEY`: Google Gemini API key for AI features

### Bot Permissions
Required Discord permissions:
- **Connect** - Join voice channels
- **Speak** - Play audio
- **Read Messages** - Read commands
- **Send Messages** - Respond to commands
- **Embed Links** - Show rich embeds

### FFmpeg Setup
**Windows:**
```bash
# Download from https://ffmpeg.org/download.html
# Add to PATH environment variable
ffmpeg -version  # Test installation
```

**Linux:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

## 📊 Usage Statistics

The bot tracks:
- Songs played per session
- Queue length and history
- AI usage per user
- Bot uptime and performance
- Voice connection quality

## 🎭 Party Mode Ideas

### Study Session
```
$mood focus
$slowmo on
$dj Recommend some study music
$ask Help me understand this topic
```

### Party Time
```
$mood happy
$nightcore on
$dj Suggest party music
$shuffle
```

### Chill Vibes
```
$mood chill
$vaporwave on
$play lofi beats
$chat  # Chill with AI
```

## 🛠️ Troubleshooting

### Common Issues

**Bot won't join voice channel:**
- Check bot permissions
- Ensure bot isn't already in another channel
- Verify voice channel exists

**Music not playing:**
- Check FFmpeg installation: `ffmpeg -version`
- Verify URL is valid
- Check internet connection

**AI not responding:**
- Verify GEMINI_API_KEY in .env
- Check daily limits with `$aistats`
- Ensure API key is valid

**Commands not working:**
- Check command prefix is `$`
- Verify bot has message permissions
- Check if channel restrictions are set

### Error Messages
- `❌ ffmpeg is not installed` - Install FFmpeg
- `⏰ You've reached your daily AI limit` - Wait for daily reset
- `❌ Use music commands in #channel only` - Use correct channel

## 📝 Development

### Project Structure
```
JoeBarden/
├── JoeBardenBot3.py     # Main bot file
├── .env                  # Environment variables
├── requirements.txt      # Python dependencies
├── playlists.json       # Saved playlists
├── patchnotes.txt        # Bot changelog
└── README.md            # This file
```

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

Copyright LPSC LLC. All rights reserved.

## 🆘 Support

If you encounter issues:
1. Check this README first
2. Review patchnotes for known issues
3. Test with `$help` and `$usage` commands
4. Verify all dependencies are installed

## 🎉 Enjoy the Bot!

JoeBardenBot is designed to be the ultimate party and study companion. With music, effects, and AI all in one, it's perfect for any Discord server!

**Made with ❤️ and lots of 🎵**
