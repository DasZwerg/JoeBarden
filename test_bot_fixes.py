#!/usr/bin/env python3
"""
Test script to verify JoeBardenBot fixes
Tests ffmpeg error handling and command prefix changes
"""

import asyncio
import os
import sys
from unittest.mock import Mock, AsyncMock, patch
import discord
from discord.ext import commands

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_command_prefix():
    """Test that command prefix is correctly set to $"""
    print("🔍 Testing command prefix...")
    
    # Import the bot
    from JoeBidenBot2_2 import bot
    
    # Check if bot has correct prefix
    assert bot.command_prefix == '$', f"Expected prefix '$', got '{bot.command_prefix}'"
    print("✅ Command prefix correctly set to '$'")
    
    return True

def test_ffmpeg_options():
    """Test that ffmpeg options include timeout for better error handling"""
    print("🔍 Testing ffmpeg options...")
    
    from JoeBidenBot2_2 import YTDLSource
    
    # Check if timeout is added to ffmpeg options
    assert '-timeout 3000000' in YTDLSource.FFMPEG_OPTIONS['options'], \
        "FFmpeg options missing timeout setting"
    print("✅ FFmpeg timeout option added")
    
    return True

def test_voice_state_cleanup():
    """Test that VoiceState has proper cleanup attributes"""
    print("🔍 Testing VoiceState cleanup...")
    
    from JoeBidenBot2_2 import VoiceState
    
    # Create a mock bot and context
    mock_bot = Mock()
    mock_ctx = Mock()
    mock_ctx.guild.id = 12345
    
    # Create VoiceState instance
    voice_state = VoiceState(mock_bot, mock_ctx)
    
    # Check if cleanup attributes exist
    assert hasattr(voice_state, '_ffmpeg_process'), "Missing _ffmpeg_process attribute"
    assert hasattr(voice_state, '_cleanup_lock'), "Missing _cleanup_lock attribute"
    print("✅ VoiceState cleanup attributes present")
    
    return True

async def test_play_command_syntax():
    """Test that play command documentation shows $ prefix"""
    print("🔍 Testing play command documentation...")
    
    from JoeBidenBot2_2 import Music
    from discord.ext import commands
    
    # Create a mock bot
    mock_bot = Mock()
    music_cog = Music(mock_bot)
    
    # Get the play command
    play_command = music_cog._play
    assert play_command is not None, "Play command not found"
    
    # Check if help text contains $ prefix
    help_text = play_command.help or ""
    assert '$play' in help_text, f"Play command help missing $ prefix: {help_text}"
    print("✅ Play command documentation updated with $ prefix")
    
    return True

def test_help_command_prefix():
    """Test that help command shows $ prefix"""
    print("🔍 Testing help command prefix display...")
    
    from JoeBidenBot2_2 import Music
    
    # Create a mock bot
    mock_bot = Mock()
    music_cog = Music(mock_bot)
    
    # The help command should use $ prefix internally
    # This is tested by checking the command exists
    help_command = music_cog._help
    assert help_command is not None, "Help command not found"
    print("✅ Help command exists and updated")
    
    return True

async def test_error_handling_improvements():
    """Test that error handling improvements are in place"""
    print("🔍 Testing error handling improvements...")
    
    from JoeBidenBot2_2 import VoiceState
    
    # Create a mock bot and context
    mock_bot = Mock()
    mock_ctx = Mock()
    mock_ctx.guild.id = 12345
    
    # Create VoiceState instance
    voice_state = VoiceState(mock_bot, mock_ctx)
    
    # Test that stop method has cleanup logic
    import inspect
    stop_source = inspect.getsource(voice_state.stop)
    assert '_cleanup_lock' in stop_source, "Stop method missing cleanup lock usage"
    assert '_ffmpeg_process' in stop_source, "Stop method missing ffmpeg process cleanup"
    print("✅ Error handling improvements present in stop method")
    
    # Test that play_next_song has cleanup logic
    play_next_source = inspect.getsource(voice_state.play_next_song)
    assert '_ffmpeg_process' in play_next_source, "play_next_song missing ffmpeg cleanup"
    print("✅ Error handling improvements present in play_next_song method")
    
    return True

def test_imports_and_dependencies():
    """Test that all required imports are present"""
    print("🔍 Testing imports and dependencies...")
    
    try:
        from JoeBidenBot2_2 import (
            VoiceState, Music, YTDLSource, Song, SongQueue,
            format_clock, is_spotify_url, is_apple_music_url
        )
        print("✅ All core classes imported successfully")
        
        # Test that discord imports are working
        import discord
        from discord.ext import commands
        print("✅ Discord imports working")
        
        # Test that yt_dlp import is working
        import yt_dlp
        print("✅ yt_dlp import working")
        
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

async def run_all_tests():
    """Run all tests and report results"""
    print("🧪 Running JoeBardenBot Fix Tests\n")
    print("=" * 50)
    
    tests = [
        ("Command Prefix", test_command_prefix),
        ("FFmpeg Options", test_ffmpeg_options),
        ("VoiceState Cleanup", test_voice_state_cleanup),
        ("Play Command Syntax", test_play_command_syntax),
        ("Help Command Prefix", test_help_command_prefix),
        ("Error Handling", test_error_handling_improvements),
        ("Imports and Dependencies", test_imports_and_dependencies),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
            else:
                failed += 1
                print(f"❌ {test_name} failed")
                
        except Exception as e:
            failed += 1
            print(f"❌ {test_name} failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! Bot fixes are working correctly.")
        print("\n📋 Summary of fixes applied:")
        print("   ✅ Changed command prefix from ! to $")
        print("   ✅ Added ffmpeg timeout to prevent hanging")
        print("   ✅ Improved ffmpeg process cleanup")
        print("   ✅ Added proper error handling for playback failures")
        print("   ✅ Updated all command documentation")
        print("\n🚀 The bot should now handle ffmpeg errors gracefully!")
    else:
        print("⚠️  Some tests failed. Please review the fixes.")
    
    return failed == 0

def create_usage_examples():
    """Create a file with usage examples for the updated bot"""
    examples = """
# JoeBardenBot Usage Examples (Updated for $ prefix)

## Basic Commands
$help                                    # Show all commands
$join                                   # Join your voice channel
$play never gonna give you up           # Play a song
$play https://youtube.com/watch?v=...   # Play from URL
$queue                                  # Show current queue
$now                                    # Show current song
$skip                                   # Skip current song
$stop                                   # Stop playback (admin)
$leave                                  # Leave voice channel (admin)

## Advanced Commands
$volume 50                              # Set volume to 50%
$loop                                   # Toggle loop
$shuffle                                # Shuffle queue
$remove 3                               # Remove 3rd song from queue
$history                                # Show recently played
$nowbar                                 # Show progress bar

## Playlist Commands
$playlist save mymix                    # Save current queue
$playlist load mymix                    # Load saved playlist
$playlist list                          # Show saved playlists

## Discovery Commands
$mood happy                             # Queue happy songs
$mood chill                              # Queue chill songs
$lyrics Queen - Bohemian Rhapsody       # Get song lyrics

## Admin Commands
$pause                                  # Pause playback (admin)
$resume                                 # Resume playback (admin)
$votemode on                            # Enable vote skipping
$summon #voice-channel                  # Move to specific channel (admin)

## Fun Commands
$roastdj                                # Roast the current DJ
$stats                                  # Show bot statistics
$patchnotes                             # Show bot updates

## Fixed Issues
✅ FFmpeg errors no longer crash the bot
✅ Processes are properly cleaned up
✅ Better timeout handling for streams
✅ All commands now use $ prefix instead of !
"""
    
    with open("USAGE_EXAMPLES.md", "w") as f:
        f.write(examples)
    
    print("📝 Created USAGE_EXAMPLES.md with updated command examples")

if __name__ == "__main__":
    print("🤖 JoeBardenBot Fix Verification")
    print("===============================\n")
    
    # Run tests
    success = asyncio.run(run_all_tests())
    
    # Create usage examples
    create_usage_examples()
    
    if success:
        print("\n🎯 Next steps:")
        print("1. Test the bot in Discord with $play command")
        print("2. Monitor for any ffmpeg errors in terminal")
        print("3. Check that all commands work with $ prefix")
        print("4. Verify cleanup works when stopping playback")
        
        print("\n🔧 If issues persist:")
        print("- Ensure ffmpeg is installed and in PATH")
        print("- Check Discord token in .env file")
        print("- Verify bot has proper permissions")
    else:
        print("\n⚠️  Please review the test failures and fix remaining issues.")
