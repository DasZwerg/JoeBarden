import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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

        with patch.object(bot_module.YTDLSource, "extract_info", return_value=data), patch.object(
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


class YtdlRuntimeTests(unittest.TestCase):
    def test_options_pick_up_cookie_replacements_and_provider_url(self):
        with tempfile.TemporaryDirectory() as directory:
            cookie_path = Path(directory) / "cookies.txt"
            with patch.object(bot_module, "YTDL_COOKIES_PATH", str(cookie_path)), patch.object(
                bot_module, "YTDL_POT_PROVIDER_URL", "http://127.0.0.1:4416"
            ):
                self.assertNotIn("cookiefile", bot_module.YTDLSource.build_options())
                cookie_path.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
                options = bot_module.YTDLSource.build_options()

        self.assertEqual(options["cookiefile"], str(cookie_path))
        self.assertEqual(
            options["extractor_args"]["youtubepot-bgutilhttp"]["base_url"],
            ["http://127.0.0.1:4416"],
        )
        self.assertEqual(options["extractor_args"]["youtube"]["player_client"][0], "mweb")

    def test_extraction_uses_and_removes_private_cookie_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            cookie_path = Path(directory) / "cookies.txt"
            cookie_path.write_text(
                "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsecret\n",
                encoding="utf-8",
            )
            extractor = Mock()
            extractor.extract_info.return_value = {"title": "track"}
            context = Mock()
            context.__enter__ = Mock(return_value=extractor)
            context.__exit__ = Mock(return_value=False)
            with patch.object(bot_module, "YTDL_COOKIES_PATH", str(cookie_path)), patch.object(
                bot_module.yt_dlp, "YoutubeDL", return_value=context
            ) as youtube_dl:
                result = bot_module.YTDLSource.extract_info("query")

            snapshot = Path(youtube_dl.call_args.args[0]["cookiefile"])
            self.assertEqual(result, {"title": "track"})
            self.assertNotEqual(snapshot, cookie_path)
            self.assertFalse(snapshot.exists())

    def test_cookie_install_validates_and_atomically_replaces(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "export.txt"
            destination = Path(directory) / "cookies.txt"
            source.write_text(
                "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSID\tsecret\n",
                encoding="utf-8",
            )

            entries = bot_module.install_youtube_cookies(str(source), str(destination))

            self.assertEqual(entries, 1)
            self.assertEqual(destination.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            self.assertFalse(Path(f"{destination}.tmp").exists())

    def test_cookie_install_rejects_unrelated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.txt"
            source.write_text("not a cookie export", encoding="utf-8")

            with self.assertRaises(ValueError):
                bot_module.install_youtube_cookies(str(source), str(Path(directory) / "cookies.txt"))


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


class ErrorNotificationTests(unittest.IsolatedAsyncioTestCase):
    def test_error_component_only_exposes_safe_category(self):
        self.assertEqual(
            bot_module.error_component("[Player] failed for /secret/path?token=value"),
            "Player",
        )
        self.assertEqual(bot_module.error_component("unstructured secret"), "Runtime")

    async def test_owner_notification_contains_no_exception_details(self):
        test_bot = bot_module.JoeBardenBot(command_prefix="!", intents=bot_module.discord.Intents.none())
        owner = Mock()
        owner.send = AsyncMock()
        test_bot.wait_until_ready = AsyncMock()
        test_bot.application_info = AsyncMock(return_value=SimpleNamespace(owner=owner))
        worker = asyncio.create_task(test_bot.error_notification_worker())
        await test_bot.error_queue.put("Player")
        for _ in range(20):
            if owner.send.await_count:
                break
            await asyncio.sleep(0)
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)

        message = owner.send.await_args.args[0]
        self.assertIn("Component: **Player**", message)
        self.assertNotIn("secret", message)


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
