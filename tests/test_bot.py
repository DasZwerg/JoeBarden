import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import JoeBardenBot3 as bot_module


class SourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_source_extracts_metadata_without_starting_ffmpeg(self):
        ctx = SimpleNamespace(author=Mock(), channel=Mock())
        data = {
            "title": "Test track",
            "url": "https://media.example/audio",
            "webpage_url": "https://example.test/watch/1",
            "duration": 120,
        }

        with patch.object(bot_module.YTDLSource.ytdl, "extract_info", return_value=data), patch.object(
            bot_module.discord, "FFmpegPCMAudio"
        ) as ffmpeg:
            source = await bot_module.YTDLSource.create_source(ctx, "test")

        self.assertEqual(source.title, "Test track")
        self.assertEqual(source.duration_seconds, 120)
        ffmpeg.assert_not_called()

    def test_flat_playlist_entry_is_metadata_only(self):
        ctx = SimpleNamespace(author=Mock(), channel=Mock())
        source = bot_module.YTDLSource.from_flat_entry(
            ctx, "https://example.test/watch/1", "Flat title"
        )

        self.assertEqual(source.title, "Flat title")
        self.assertEqual(source.url, "https://example.test/watch/1")
        self.assertEqual(source.duration_seconds, 0)


class FfmpegOptionTests(unittest.TestCase):
    def test_effects_are_composed(self):
        options, reverse_skipped = bot_module.build_ffmpeg_options(
            {"reverse": True, "nightcore": True, "bass": True}, 180
        )

        self.assertFalse(reverse_skipped)
        self.assertIn("areverse,asetrate=48000*1.15,aresample=48000,bass=g=15", options["options"])

    def test_reverse_is_skipped_for_unknown_or_long_media(self):
        for duration in (0, bot_module.REVERSE_MAX_DURATION_SECONDS + 1):
            with self.subTest(duration=duration):
                options, reverse_skipped = bot_module.build_ffmpeg_options(
                    {"reverse": True}, duration
                )
                self.assertTrue(reverse_skipped)
                self.assertNotIn("-af", options["options"])


class PlaylistStorageTests(unittest.TestCase):
    def setUp(self):
        self.cog = bot_module.Music(Mock())
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.cog.playlists_path = str(Path(self.temp_dir.name) / "playlists.json")

    def test_legacy_data_is_scoped_to_current_guild(self):
        legacy = {"42": {"favorites": ["song"]}}
        Path(self.cog.playlists_path).write_text(json.dumps(legacy), encoding="utf-8")

        data = self.cog._read_playlists(123)

        self.assertEqual(data["version"], 2)
        self.assertEqual(data["guilds"]["123"], legacy)

    def test_atomic_write_round_trip(self):
        data = {"version": 2, "guilds": {"123": {"42": {"mix": ["song"]}}}}

        self.cog._write_playlists(data)

        self.assertEqual(self.cog._read_playlists(123), data)
        self.assertFalse(Path(f"{self.cog.playlists_path}.tmp").exists())


class AiFallbackTests(unittest.TestCase):
    def test_groq_handles_gemini_quota(self):
        with patch.object(bot_module, "client", object()), patch.object(
            bot_module, "gemini_model", "gemini-test"
        ), patch.object(
            bot_module, "_groq_client", object()
        ), patch.object(
            bot_module,
            "generate_content_with_fallback",
            side_effect=bot_module.GeminiQuotaError("quota"),
        ), patch.object(
            bot_module, "generate_content_with_groq", return_value="fallback"
        ) as groq, patch.object(bot_module, "log_error"):
            result = bot_module.generate_content("hello")

        self.assertEqual(result, "fallback")
        groq.assert_called_once_with("hello", None)


if __name__ == "__main__":
    unittest.main()
