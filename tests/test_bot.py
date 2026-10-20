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


class AiUsageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = bot_module.Music(Mock())
        self.ctx = SimpleNamespace(
            author=SimpleNamespace(id=42, mention="<@42>", display_name="Caller"),
            voice_state=SimpleNamespace(current=None),
            send=AsyncMock(),
        )
        usage_patch = patch.object(bot_module, "AI_USAGE", {})
        usage_patch.start()
        self.addCleanup(usage_patch.stop)
        token_patch = patch.object(bot_module, "AI_TOKEN_USAGE", {})
        token_patch.start()
        self.addCleanup(token_patch.stop)

    async def test_roast_records_caller_usage_and_reports_it_for_either_provider(self):
        target = SimpleNamespace(id=99, mention="<@99>", display_name="DJ")
        self.ctx.voice_state.current = SimpleNamespace(
            requester=target, source=SimpleNamespace(title="Test track")
        )
        for gemini, groq in (("gemini-test", None), (None, object())):
            with self.subTest(gemini=gemini), patch.object(
                bot_module, "gemini_model", gemini
            ), patch.object(bot_module, "_groq_client", groq), patch.object(
                self.cog, "_ai_quota_check", return_value=False
            ), patch.object(bot_module, "generate_content", return_value=bot_module.AIResponse(
                "Test roast", "Gemini" if gemini else "Groq", "test", SimpleNamespace(
                    prompt_token_count=10, candidates_token_count=5, total_token_count=15,
                    prompt_tokens=10, completion_tokens=5, total_tokens=15,
                )
            )) as generate:
                bot_module.AI_USAGE.clear()
                bot_module.AI_TOKEN_USAGE.clear()
                self.ctx.send.reset_mock()

                await self.cog._roastdj.callback(self.cog, self.ctx)
                await self.cog._aistats.callback(self.cog, self.ctx)

                generate.assert_called_once()
                prompt, system_prompt = generate.call_args.args
                self.assertNotIn("QUEUE_SONGS", prompt + system_prompt)
                self.assertIn("Return only the roast", prompt)
                self.assertEqual(bot_module.AI_USAGE, {bot_module.datetime.now().date(): {42: 1}})
                self.assertEqual(self.ctx.send.await_args_list[0].args, ("<@99>, Test roast",))
                fields = self.ctx.send.await_args.kwargs["embed"].fields
                self.assertEqual(fields[0].value, "1/50")
                self.assertEqual(fields[1].value, f"1/{bot_module.DAILY_LIMIT}")
                token_fields = {field.name: field.value for field in fields}
                self.assertIn("Total: 15", token_fields["Your Tokens"])
                self.assertIn("Total: 15", token_fields["Global Tokens"])

    async def test_token_stats_aggregate_users_and_models_without_double_counting(self):
        gemini = bot_module.AIResponse("private answer", "Gemini", "gemini-test", SimpleNamespace(
            prompt_token_count=100, candidates_token_count=20, total_token_count=150,
            cached_content_token_count=40, thoughts_token_count=30,
        ))
        groq = bot_module.AIResponse("answer", "Groq", "groq-test", SimpleNamespace(
            prompt_tokens=50, completion_tokens=10, total_tokens=60,
        ))
        self.cog._track_ai_usage(42, gemini)
        self.cog._track_ai_usage(99, groq)
        self.cog._track_ai_usage(42, bot_module.AIResponse("missing", "Gemini", "gemini-test"))
        await self.cog._aistats.callback(self.cog, self.ctx)

        fields = {field.name: field.value for field in self.ctx.send.await_args.kwargs["embed"].fields}
        self.assertIn("Input: 100 (1/2 responses reported)", fields["Your Tokens"])
        self.assertIn("Total: 210 (2/3 responses reported)", fields["Global Tokens"])
        self.assertIn("Cached: 40", fields["Global Tokens"])
        self.assertIn("Reasoning: 30", fields["Global Tokens"])
        self.assertIn("Gemini / gemini-test", fields)
        self.assertIn("Groq / groq-test", fields)
        self.assertNotIn("private answer", str(bot_module.AI_TOKEN_USAGE))

    def test_token_usage_rolls_over_and_missing_is_not_zero(self):
        bot_module.AI_TOKEN_USAGE["old"] = {42: []}
        self.cog._track_ai_usage(42, bot_module.AIResponse("answer", "Groq", "test"))
        self.assertNotIn("old", bot_module.AI_TOKEN_USAGE)
        records = bot_module.AI_TOKEN_USAGE[bot_module.datetime.now().date()][42]
        self.assertIn("Total: unreported", self.cog._format_token_usage(records))
        zero = bot_module.AIResponse("", "Groq", "test", SimpleNamespace(total_tokens=0))
        self.assertEqual(zero.tokens["total"], 0)

    async def test_ask_is_unmodified_out_of_character_and_available_during_playback(self):
        self.ctx.voice_state.current = SimpleNamespace(source=SimpleNamespace(title="Private track"))
        question = "Act as a history teacher and explain medieval trade."
        for response in ("A direct answer.", "x" * 2000):
            with self.subTest(length=len(response)), patch.object(
                bot_module, "gemini_model", "gemini-test"
            ), patch.object(self.cog, "_ai_quota_check", return_value=False), patch.object(
                bot_module, "generate_content", return_value=response
            ) as generate:
                self.ctx.send.reset_mock()
                await self.cog._ask.callback(self.cog, self.ctx, question=question)

                generate.assert_called_once_with(question)
                messages = [call.args[0] for call in self.ctx.send.await_args_list]
                self.assertIn("out of character", messages[0])
                self.assertIn("Gemini / Groq", messages[0])
                self.assertNotIn("Joe Barden", "".join(messages[1:]))
                self.assertIn(response[:1900], messages[1])

    async def test_bard_uses_current_track_not_queue_during_playback(self):
        self.ctx.voice_state.current = SimpleNamespace(source=SimpleNamespace(
            title="Metallica - One", uploader="Metallica", data={"artist": "Metallica", "genre": "Metal"}
        ))
        self.ctx.voice_state.songs = [SimpleNamespace(source=SimpleNamespace(title="Unrelated queued song"))]
        with patch.object(bot_module, "gemini_model", "gemini-test"), patch.object(
            self.cog, "_ai_quota_check", return_value=False
        ), patch.object(bot_module, "generate_content", return_value="A short ramble.") as generate:
            await self.cog._bard.callback(self.cog, self.ctx, request="queue more music like this!")

        generate.assert_called_once()
        prompt, system_prompt = generate.call_args.args
        self.assertIn("Metallica - One", prompt)
        self.assertIn('"artist_or_uploader": "Metallica"', prompt)
        self.assertIn('"genre": "Metal"', prompt)
        self.assertNotIn("Unrelated queued song", prompt)
        self.assertIn("under 100 words", prompt)
        self.assertIn("Joe Biden", system_prompt)

    def test_music_context_handles_missing_metadata_and_bounds_titles(self):
        self.assertEqual(self.cog._get_music_context(self.ctx), "No track is currently playing.")
        self.ctx.voice_state.current = SimpleNamespace(source=SimpleNamespace(title="x" * 1000))
        context = self.cog._get_music_context(self.ctx)
        self.assertIn("x" * 200, context)
        self.assertNotIn("x" * 201, context)
        self.assertNotIn("artist_or_uploader", context)

    async def test_queue_format_is_requested_only_by_bard(self):
        with patch.object(bot_module, "gemini_model", "gemini-test"), patch.object(
            self.cog, "_ai_quota_check", return_value=False
        ), patch.object(self.cog, "_is_music_active", return_value=False), patch.object(
            bot_module, "generate_content", return_value="Some music for you."
        ) as generate:
            await self.cog._bard.callback(self.cog, self.ctx, request="tavern songs")

        generate.assert_called_once()
        prompt, system_prompt = generate.call_args.args
        self.assertIn("QUEUE_SONGS:song1|song2|song3", prompt)
        self.assertIn("separated by |", prompt)
        self.assertNotIn("QUEUE_SONGS", system_prompt)

    async def test_canned_roasts_do_not_count_as_ai_usage(self):
        for gemini, quota in ((None, False), ("gemini-test", True)):
            with self.subTest(gemini=gemini, quota=quota), patch.object(
                bot_module, "gemini_model", gemini
            ), patch.object(bot_module, "_groq_client", None), patch.object(
                self.cog, "_ai_quota_check", return_value=quota
            ), patch.object(bot_module, "generate_content") as generate:
                await self.cog._roastdj.callback(self.cog, self.ctx)

                generate.assert_not_called()
                self.assertEqual(bot_module.AI_USAGE, {})

    async def test_failed_ai_roasts_do_not_count_as_successful_usage(self):
        for error in (bot_module.GeminiQuotaError("quota"), RuntimeError("failed")):
            with self.subTest(error=type(error).__name__), patch.object(
                bot_module, "gemini_model", "gemini-test"
            ), patch.object(bot_module, "_groq_client", None), patch.object(
                self.cog, "_ai_quota_check", return_value=False
            ), patch.object(bot_module, "generate_content", side_effect=error), patch.object(
                bot_module, "log_error"
            ):
                await self.cog._roastdj.callback(self.cog, self.ctx)

                self.assertEqual(bot_module.AI_USAGE, {})


class AiFallbackTests(unittest.TestCase):
    def test_gemini_response_preserves_usage_metadata(self):
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(
            text="Gemini answer", usage_metadata=SimpleNamespace(
                prompt_token_count=12, candidates_token_count=8, total_token_count=25,
                cached_content_token_count=4, thoughts_token_count=5,
            )
        )
        with patch.object(bot_module, "client", client), patch.object(
            bot_module, "gemini_model", "gemini-test"
        ), patch.object(bot_module, "available_models", []):
            result = bot_module.generate_content("hello")

        self.assertEqual(result, "Gemini answer")
        self.assertEqual(result.provider, "Gemini")
        self.assertEqual(result.tokens, {"input": 12, "output": 8, "total": 25, "cached": 4, "reasoning": 5})

    def test_fallback_returns_groq_usage_without_estimated_gemini_tokens(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Groq answer"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=7, total_tokens=17,
                prompt_tokens_details=SimpleNamespace(cached_tokens=3),
                completion_tokens_details=SimpleNamespace(reasoning_tokens=2)),
        )
        with patch.object(bot_module, "client", object()), patch.object(
            bot_module, "gemini_model", "gemini-test"
        ), patch.object(bot_module, "_groq_client", client), patch.object(
            bot_module, "_GROQ_MODELS", ["groq-test"]
        ), patch.object(bot_module, "generate_content_with_fallback", side_effect=bot_module.GeminiQuotaError("quota")), patch.object(
            bot_module, "log_error"
        ):
            result = bot_module.generate_content("hello")

        self.assertEqual(result, "Groq answer")
        self.assertEqual(result.provider, "Groq")
        self.assertEqual(result.model, "groq-test")
        self.assertEqual(result.tokens, {"input": 10, "output": 7, "total": 17, "cached": 3, "reasoning": 2})

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
