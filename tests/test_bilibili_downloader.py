import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scripts.bilibili_downloader import (
    build_audio_options,
    build_episode_url,
    build_bilibili_collection_plan,
    build_download_items,
    build_download_urls,
    build_video_options,
    BilibiliCollectionItem,
    BilibiliCollectionPlan,
    DOWNLOAD_EVENT_PREFIX,
    create_parser,
    default_download_dir,
    determine_download_plan,
    download_audio,
    download_items,
    download_video,
    emit_download_event,
    format_download_report,
    infer_media_type,
    is_bilibili_audio_playlist_url,
    is_bilibili_audio_track_url,
    is_bilibili_audio_url,
    main,
    normalize_bilibili_url,
    parse_episode_selection,
    create_progress_hook,
    resolve_media_type,
    safe_print,
    configure_stream_utf8,
    summarize_metadata,
    VideoSummary,
)


class EpisodeSelectionTests(unittest.TestCase):
    def test_uses_all_episodes_when_selection_is_empty(self):
        self.assertEqual(parse_episode_selection(None, 5), [1, 2, 3, 4, 5])

    def test_parses_range_selection(self):
        self.assertEqual(parse_episode_selection("1-5", 8), [1, 2, 3, 4, 5])

    def test_parses_comma_selection(self):
        self.assertEqual(parse_episode_selection("1,2,6", 8), [1, 2, 6])

    def test_deduplicates_and_sorts_mixed_selection(self):
        self.assertEqual(parse_episode_selection("3,1-2,2", 8), [1, 2, 3])

    def test_rejects_out_of_range_episode(self):
        with self.assertRaises(ValueError):
            parse_episode_selection("1,9", 8)

    def test_rejects_reverse_range(self):
        with self.assertRaises(ValueError):
            parse_episode_selection("5-1", 8)

    def test_all_selects_every_episode(self):
        self.assertEqual(parse_episode_selection("all", 3), [1, 2, 3])


class UrlTests(unittest.TestCase):
    def test_build_episode_url_keeps_clean_bv_url_and_sets_p(self):
        self.assertEqual(
            build_episode_url("https://www.bilibili.com/video/BV1Ag4y1Z7Ga", 5),
            "https://www.bilibili.com/video/BV1Ag4y1Z7Ga?p=5",
        )

    def test_build_episode_url_replaces_tracking_query_with_p(self):
        self.assertEqual(
            build_episode_url(
                "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?spm_id_from=x&vd_source=y",
                5,
            ),
            "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=5",
        )

    def test_normalize_bilibili_url_removes_page_and_tracking_query(self):
        self.assertEqual(
            normalize_bilibili_url(
                "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=2&vd_source=abc"
            ),
            "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/",
        )

    def test_infers_video_media_from_bilibili_video_url(self):
        self.assertEqual(
            infer_media_type("https://www.bilibili.com/video/BV1Ag4y1Z7Ga/"),
            "video",
        )

    def test_infers_audio_media_from_bilibili_audio_url(self):
        self.assertEqual(
            infer_media_type("https://www.bilibili.com/audio/au123456"),
            "audio",
        )

    def test_infers_audio_media_from_bilibili_audio_domain(self):
        self.assertEqual(
            infer_media_type("https://audio.bilibili.com/audio/au123456"),
            "audio",
        )

    def test_infers_audio_media_from_bilibili_audio_album_url(self):
        self.assertEqual(
            infer_media_type("https://www.bilibili.com/audio/am10627"),
            "audio",
        )

    def test_identifies_audio_album_url(self):
        self.assertTrue(is_bilibili_audio_playlist_url("https://www.bilibili.com/audio/am10627"))
        self.assertFalse(is_bilibili_audio_playlist_url("https://www.bilibili.com/audio/au4059094"))

    def test_identifies_audio_track_url(self):
        self.assertTrue(is_bilibili_audio_track_url("https://www.bilibili.com/audio/au4059094"))
        self.assertFalse(is_bilibili_audio_track_url("https://www.bilibili.com/audio/am10627"))

    def test_identifies_bilibili_audio_url(self):
        self.assertTrue(is_bilibili_audio_url("https://www.bilibili.com/audio/am10627"))
        self.assertTrue(is_bilibili_audio_url("https://www.bilibili.com/audio/au4059094"))
        self.assertFalse(is_bilibili_audio_url("https://www.bilibili.com/video/BV1Ag4y1Z7Ga/"))


class DownloadPlanTests(unittest.TestCase):
    def test_keeps_original_link_when_episodes_are_not_specified(self):
        url = "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=2&vd_source=abc"
        summary = VideoSummary("title", True, 3)

        plan_url, episodes = determine_download_plan(url, None, summary)

        self.assertEqual(plan_url, url)
        self.assertEqual(episodes, [2])

    def test_normalizes_link_when_episodes_are_specified(self):
        url = "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=2&vd_source=abc"
        summary = VideoSummary("title", True, 3)

        plan_url, episodes = determine_download_plan(url, "1,2", summary)

        self.assertEqual(plan_url, "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/")
        self.assertEqual(episodes, [1, 2])

    def test_download_urls_keep_original_link_without_episode_selection(self):
        url = "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=2&vd_source=abc"
        summary = VideoSummary("title", True, 3)

        plan_url, episodes = determine_download_plan(url, None, summary)

        self.assertEqual(build_download_urls(plan_url, summary, episodes), [url])

    def test_build_download_items_keeps_episode_numbers_with_urls(self):
        url = "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/"
        summary = VideoSummary("title", True, 3)

        self.assertEqual(
            build_download_items(url, summary, [1, 3]),
            [
                (1, "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=1"),
                (3, "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=3"),
            ],
        )

    def test_audio_album_without_episode_selection_downloads_all_tracks(self):
        url = "https://www.bilibili.com/audio/am10627"
        summary = VideoSummary("title", True, 13)

        plan_url, episodes = determine_download_plan(url, None, summary)

        self.assertEqual(plan_url, url)
        self.assertEqual(episodes, list(range(1, 14)))

    def test_audio_album_with_episode_selection_keeps_album_url(self):
        url = "https://www.bilibili.com/audio/am10627"
        summary = VideoSummary("title", True, 13)

        plan_url, episodes = determine_download_plan(url, "1,3-4", summary)

        self.assertEqual(plan_url, url)
        self.assertEqual(episodes, [1, 3, 4])

    def test_audio_album_download_items_do_not_build_video_page_urls(self):
        url = "https://www.bilibili.com/audio/am10627"
        summary = VideoSummary("title", True, 13)

        self.assertEqual(
            build_download_items(url, summary, [1, 3]),
            [
                (1, "https://www.bilibili.com/audio/am10627"),
                (3, "https://www.bilibili.com/audio/am10627"),
            ],
        )

    def test_audio_track_with_episode_selection_ignores_selection(self):
        url = "https://www.bilibili.com/audio/au4059094"
        summary = VideoSummary("title", False, 1)

        plan_url, episodes = determine_download_plan(url, "2", summary)

        self.assertEqual(plan_url, url)
        self.assertEqual(episodes, [1])


class BilibiliCollectionPlanTests(unittest.TestCase):
    def test_build_bilibili_collection_plan_expands_nested_bv_pages(self):
        state = {
            "sectionsInfo": {
                "title": "宋词三百首",
                "sections": [
                    {
                        "title": "正片",
                        "episodes": [
                            {"bvid": "BVfirst", "title": "宋词三百首1-3"},
                            {"bvid": "BVsecond", "title": "宋词三百首4"},
                        ],
                    }
                ],
            }
        }

        def fake_page_fetcher(bvid):
            return {
                "BVfirst": [
                    {"page": 1, "part": "001"},
                    {"page": 2, "part": "002"},
                    {"page": 3, "part": "003"},
                ],
                "BVsecond": [{"page": 1, "part": "004"}],
            }[bvid]

        plan = build_bilibili_collection_plan(state, page_fetcher=fake_page_fetcher)

        self.assertEqual(plan.title, "宋词三百首")
        self.assertEqual(len(plan.items), 4)
        self.assertEqual(
            [(item.episode, item.url) for item in plan.items],
            [
                (1, "https://www.bilibili.com/video/BVfirst?p=1"),
                (2, "https://www.bilibili.com/video/BVfirst?p=2"),
                (3, "https://www.bilibili.com/video/BVfirst?p=3"),
                (4, "https://www.bilibili.com/video/BVsecond"),
            ],
        )

    def test_build_bilibili_collection_plan_uses_embedded_pages_first(self):
        state = {
            "sectionsInfo": {
                "title": "宋词三百首",
                "sections": [
                    {
                        "episodes": [
                            {
                                "bvid": "BVfirst",
                                "title": "宋词三百首1-2",
                                "pages": [
                                    {"page": 1, "part": "001"},
                                    {"page": 2, "part": "002"},
                                ],
                            }
                        ],
                    }
                ],
            }
        }

        def failing_page_fetcher(_bvid):
            raise AssertionError("page_fetcher should not be called")

        plan = build_bilibili_collection_plan(state, page_fetcher=failing_page_fetcher)

        self.assertEqual(
            [(item.episode, item.url) for item in plan.items],
            [
                (1, "https://www.bilibili.com/video/BVfirst?p=1"),
                (2, "https://www.bilibili.com/video/BVfirst?p=2"),
            ],
        )

    def test_build_bilibili_collection_plan_returns_none_without_sections(self):
        self.assertIsNone(build_bilibili_collection_plan({"videoData": {"pages": []}}))


class DownloadExecutionTests(unittest.TestCase):
    def test_parser_media_default_allows_url_based_detection(self):
        args = create_parser().parse_args(["-i", "https://www.bilibili.com/video/BVtest"])

        self.assertIsNone(args.media)

    def test_parser_description_mentions_audio_and_video(self):
        self.assertIn("audio or video", create_parser().description)

    def test_parser_input_help_accepts_any_bilibili_url(self):
        input_action = next(action for action in create_parser()._actions if action.dest == "input")

        self.assertEqual(input_action.help, "Bilibili URL.")

    def test_video_options_download_best_video_and_audio_to_output_directory(self):
        options = build_video_options(Path("C:/Downloads"))

        self.assertEqual(options["format"], "bv*+ba/best")
        self.assertEqual(options["merge_output_format"], "mp4")
        self.assertEqual(options["outtmpl"], "C:\\Downloads\\%(title).200B-%(id)s.%(ext)s")
        self.assertTrue(options["noplaylist"])

    def test_audio_options_extract_mp3_to_output_directory(self):
        options = build_audio_options(Path("C:/Downloads"))

        self.assertEqual(options["format"], "bestaudio/best")
        self.assertEqual(options["outtmpl"], "C:\\Downloads\\%(title).200B-%(id)s.%(ext)s")
        self.assertEqual(
            options["postprocessors"],
            [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                }
            ],
        )

    def test_audio_options_can_select_playlist_item(self):
        options = build_audio_options(Path("C:/Downloads"), playlist_items="3")

        self.assertFalse(options["noplaylist"])
        self.assertEqual(options["playlist_items"], "3")

    def test_audio_options_accept_progress_hooks(self):
        hook = object()
        options = build_audio_options(Path("C:/Downloads"), progress_hooks=[hook])

        self.assertEqual(options["progress_hooks"], [hook])

    def test_video_options_accept_progress_hooks(self):
        hook = object()
        options = build_video_options(Path("C:/Downloads"), progress_hooks=[hook])

        self.assertEqual(options["progress_hooks"], [hook])

    def test_progress_hook_emits_percent_and_title(self):
        stdout = StringIO()
        hook = create_progress_hook({"episode": 2, "total": 5})

        with (
            redirect_stdout(stdout),
            patch.dict("os.environ", {"BILI_DOWNLOADER_EVENTS": "1"}),
        ):
            hook(
                {
                    "status": "downloading",
                    "downloaded_bytes": 50,
                    "total_bytes": 100,
                    "info_dict": {"title": "中文标题"},
                }
            )

        event_line = next(
            line for line in stdout.getvalue().splitlines() if line.startswith(DOWNLOAD_EVENT_PREFIX)
        )
        event = json.loads(event_line.removeprefix(DOWNLOAD_EVENT_PREFIX))
        self.assertEqual(event["type"], "item_progress")
        self.assertEqual(event["episode"], 2)
        self.assertEqual(event["total"], 5)
        self.assertEqual(event["percent"], 50.0)
        self.assertEqual(event["name"], "中文标题")

    def test_download_audio_album_downloads_selected_items_one_by_one(self):
        captured_options = []
        downloaded_urls = []

        class FakeYoutubeDL:
            def __init__(self, options):
                captured_options.append(options)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def download(self, urls):
                downloaded_urls.append(urls)
                return 0

        stdout = StringIO()
        with TemporaryDirectory() as temp_dir:
            with (
                redirect_stdout(stdout),
                patch.dict(
                    "sys.modules",
                    {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYoutubeDL)},
                ),
            ):
                result = download_audio(
                    "https://www.bilibili.com/audio/am10627",
                    VideoSummary("title", True, 13),
                    [1, 3, 5],
                    Path(temp_dir),
                )

        self.assertEqual(len(captured_options), 3)
        self.assertEqual([options["playlist_items"] for options in captured_options], ["1", "3", "5"])
        self.assertEqual(
            downloaded_urls,
            [
                ["https://www.bilibili.com/audio/am10627"],
                ["https://www.bilibili.com/audio/am10627"],
                ["https://www.bilibili.com/audio/am10627"],
            ],
        )
        self.assertIn("Downloading playlist item 1 of 13", stdout.getvalue())
        self.assertIn("Downloading playlist item 3 of 13", stdout.getvalue())
        self.assertIn("Downloading playlist item 5 of 13", stdout.getvalue())
        self.assertEqual(result.succeeded_episodes, [1, 3, 5])
        self.assertEqual(result.failed_episodes, [])

    def test_download_audio_album_continues_after_failed_item(self):
        class FakeYoutubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def download(self, urls):
                if self.options["playlist_items"] == "3":
                    return 1
                return 0

        with TemporaryDirectory() as temp_dir:
            with (
                redirect_stdout(StringIO()),
                redirect_stderr(StringIO()),
                patch.dict(
                    "sys.modules",
                    {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYoutubeDL)},
                ),
            ):
                result = download_audio(
                    "https://www.bilibili.com/audio/am10627",
                    VideoSummary("title", True, 13),
                    [1, 3, 5],
                    Path(temp_dir),
                )

        self.assertEqual(result.succeeded_episodes, [1, 5])
        self.assertEqual(result.failed_episodes, [3])

    def test_download_items_prints_playlist_progress_when_total_is_provided(self):
        class FakeYDL:
            def download(self, urls):
                return 0

        stdout = StringIO()

        with redirect_stdout(stdout):
            result = download_items(
                FakeYDL(),
                [
                    (1, "https://example.test/video?p=1"),
                    (5, "https://example.test/video?p=5"),
                ],
                total_episodes=13,
            )

        self.assertIn("Downloading playlist item 1 of 13", stdout.getvalue())
        self.assertIn("Downloading playlist item 5 of 13", stdout.getvalue())
        self.assertEqual(result.succeeded_episodes, [1, 5])

    def test_download_items_emits_json_events_when_enabled(self):
        class FakeYDL:
            def download(self, urls):
                return 0

        stdout = StringIO()

        with (
            redirect_stdout(stdout),
            patch.dict("os.environ", {"BILI_DOWNLOADER_EVENTS": "1"}),
        ):
            result = download_items(
                FakeYDL(),
                [
                    (1, "https://example.test/video?p=1"),
                    (5, "https://example.test/video?p=5"),
                ],
                total_episodes=13,
            )

        events = [
            json.loads(line.removeprefix(DOWNLOAD_EVENT_PREFIX))
            for line in stdout.getvalue().splitlines()
            if line.startswith(DOWNLOAD_EVENT_PREFIX)
        ]

        self.assertEqual(
            [(event["type"], event["episode"]) for event in events],
            [
                ("item_started", 1),
                ("item_completed", 1),
                ("item_started", 5),
                ("item_completed", 5),
            ],
        )
        self.assertEqual(events[0]["total"], 13)
        self.assertEqual(result.succeeded_episodes, [1, 5])

    def test_download_video_prints_playlist_progress_for_selected_parts(self):
        class FakeYoutubeDL:
            def __init__(self, options):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def download(self, urls):
                return 0

        stdout = StringIO()
        with TemporaryDirectory() as temp_dir:
            with (
                redirect_stdout(stdout),
                patch.dict(
                    "sys.modules",
                    {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYoutubeDL)},
                ),
            ):
                result = download_video(
                    "https://www.bilibili.com/video/BVtest/",
                    VideoSummary("title", True, 13),
                    [1, 5],
                    Path(temp_dir),
                )

        self.assertIn("Downloading playlist item 1 of 13", stdout.getvalue())
        self.assertIn("Downloading playlist item 5 of 13", stdout.getvalue())
        self.assertEqual(result.succeeded_episodes, [1, 5])

    def test_audio_url_forces_audio_even_when_video_is_requested(self):
        self.assertEqual(
            resolve_media_type("video", "https://www.bilibili.com/audio/au4059094"),
            "audio",
        )

    def test_video_url_respects_explicit_audio_request(self):
        self.assertEqual(
            resolve_media_type("audio", "https://www.bilibili.com/video/BVtest"),
            "audio",
        )

    def test_main_routes_video_media_to_video_downloader(self):
        summary = VideoSummary("title", False, 1)
        result = type("Result", (), {"succeeded_episodes": [1], "failed_episodes": []})()

        with (
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
            patch("scripts.bilibili_downloader.fetch_metadata", return_value={"title": "title"}),
            patch("scripts.bilibili_downloader.summarize_metadata", return_value=summary),
            patch("scripts.bilibili_downloader.download_video", return_value=result) as download_video,
        ):
            exit_code = main(["-i", "https://www.bilibili.com/video/BVtest", "-m", "video"])

        self.assertEqual(exit_code, 0)
        download_video.assert_called_once_with(
            "https://www.bilibili.com/video/BVtest",
            summary,
            [1],
            default_download_dir(),
        )

    def test_main_emits_plan_event_when_events_are_enabled(self):
        summary = VideoSummary("合集标题", True, 5)
        result = type("Result", (), {"succeeded_episodes": [1, 3], "failed_episodes": []})()
        stdout = StringIO()

        with (
            redirect_stdout(stdout),
            redirect_stderr(StringIO()),
            patch.dict("os.environ", {"BILI_DOWNLOADER_EVENTS": "1"}),
            patch("scripts.bilibili_downloader.fetch_metadata", return_value={"title": "合集标题"}),
            patch("scripts.bilibili_downloader.summarize_metadata", return_value=summary),
            patch("scripts.bilibili_downloader.download_video", return_value=result),
        ):
            exit_code = main(["-i", "https://www.bilibili.com/video/BVtest", "-e", "1,3"])

        events = [
            json.loads(line.removeprefix(DOWNLOAD_EVENT_PREFIX))
            for line in stdout.getvalue().splitlines()
            if line.startswith(DOWNLOAD_EVENT_PREFIX)
        ]
        plan = next(event for event in events if event["type"] == "plan")
        self.assertEqual(exit_code, 0)
        self.assertEqual(plan["title"], "合集标题")
        self.assertEqual(plan["episodes"], [1, 3])
        self.assertEqual(plan["total"], 5)
        self.assertEqual(plan["media"], "video")

    def test_main_routes_omitted_media_to_video_for_video_url(self):
        summary = VideoSummary("title", False, 1)
        result = type("Result", (), {"succeeded_episodes": [1], "failed_episodes": []})()

        with (
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
            patch("scripts.bilibili_downloader.fetch_metadata", return_value={"title": "title"}),
            patch("scripts.bilibili_downloader.summarize_metadata", return_value=summary),
            patch("scripts.bilibili_downloader.download_audio") as download_audio,
            patch("scripts.bilibili_downloader.download_video", return_value=result) as download_video,
        ):
            exit_code = main(["-i", "https://www.bilibili.com/video/BVtest"])

        self.assertEqual(exit_code, 0)
        download_audio.assert_not_called()
        download_video.assert_called_once()

    def test_main_uses_collection_episode_selection_when_sections_are_detected(self):
        collection = BilibiliCollectionPlan(
            title="宋词三百首",
            items=[
                BilibiliCollectionItem(1, "https://www.bilibili.com/video/BVfirst?p=1", "001"),
                BilibiliCollectionItem(2, "https://www.bilibili.com/video/BVfirst?p=2", "002"),
                BilibiliCollectionItem(3, "https://www.bilibili.com/video/BVfirst?p=3", "003"),
                BilibiliCollectionItem(4, "https://www.bilibili.com/video/BVsecond", "004"),
            ],
        )
        result = type("Result", (), {"succeeded_episodes": [4], "failed_episodes": []})()

        with (
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
            patch("scripts.bilibili_downloader.fetch_bilibili_collection_plan", return_value=collection),
            patch("scripts.bilibili_downloader.fetch_metadata") as fetch_metadata,
            patch("scripts.bilibili_downloader.download_video", return_value=result) as download_video,
        ):
            exit_code = main(["-i", "https://www.bilibili.com/video/BVsecond", "-e", "4"])

        self.assertEqual(exit_code, 0)
        fetch_metadata.assert_not_called()
        download_video.assert_called_once()
        args, kwargs = download_video.call_args
        self.assertEqual(
            args[:4],
            (
                "https://www.bilibili.com/video/BVsecond",
                VideoSummary("宋词三百首", True, 4),
                [4],
                default_download_dir(),
            ),
        )
        self.assertEqual(
            kwargs["download_items_override"],
            [(4, "https://www.bilibili.com/video/BVsecond")],
        )

    def test_main_routes_omitted_media_to_audio_for_audio_url(self):
        summary = VideoSummary("title", False, 1)
        result = type("Result", (), {"succeeded_episodes": [1], "failed_episodes": []})()

        with (
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
            patch("scripts.bilibili_downloader.fetch_metadata", return_value={"title": "title"}),
            patch("scripts.bilibili_downloader.summarize_metadata", return_value=summary),
            patch("scripts.bilibili_downloader.download_audio", return_value=result) as download_audio,
            patch("scripts.bilibili_downloader.download_video") as download_video,
        ):
            exit_code = main(["-i", "https://www.bilibili.com/audio/au123456"])

        self.assertEqual(exit_code, 0)
        download_audio.assert_called_once()
        download_video.assert_not_called()

    def test_main_forces_audio_for_audio_url_even_when_video_is_requested(self):
        summary = VideoSummary("title", False, 1)
        result = type("Result", (), {"succeeded_episodes": [1], "failed_episodes": []})()
        stderr = StringIO()

        with (
            redirect_stdout(StringIO()),
            redirect_stderr(stderr),
            patch("scripts.bilibili_downloader.fetch_metadata", return_value={"title": "title"}),
            patch("scripts.bilibili_downloader.summarize_metadata", return_value=summary),
            patch("scripts.bilibili_downloader.download_audio", return_value=result) as download_audio,
            patch("scripts.bilibili_downloader.download_video") as download_video,
        ):
            exit_code = main(
                ["-i", "https://www.bilibili.com/audio/au4059094", "-m", "video"]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn(
            "Warning: audio URL detected; ignoring --media video and using audio mode.",
            stderr.getvalue(),
        )
        download_audio.assert_called_once()
        download_video.assert_not_called()

    def test_main_ignores_episode_selection_for_single_audio_url(self):
        summary = VideoSummary("title", False, 1)
        result = type("Result", (), {"succeeded_episodes": [1], "failed_episodes": []})()
        stderr = StringIO()

        with (
            redirect_stdout(StringIO()),
            redirect_stderr(stderr),
            patch("scripts.bilibili_downloader.fetch_metadata", return_value={"title": "title"}),
            patch("scripts.bilibili_downloader.summarize_metadata", return_value=summary),
            patch("scripts.bilibili_downloader.download_audio", return_value=result) as download_audio,
        ):
            exit_code = main(["-i", "https://www.bilibili.com/audio/au4059094", "-e", "2"])

        self.assertEqual(exit_code, 0)
        self.assertIn(
            "Warning: single audio URL detected; ignoring --episodes.",
            stderr.getvalue(),
        )
        download_audio.assert_called_once_with(
            "https://www.bilibili.com/audio/au4059094",
            summary,
            [1],
            default_download_dir(),
        )

    def test_download_items_continues_after_failed_episode(self):
        class FakeYDL:
            def __init__(self):
                self.downloaded = []

            def download(self, urls):
                self.downloaded.append(urls[0])
                if urls[0].endswith("p=2"):
                    raise RuntimeError("connection dropped")
                return 0

        ydl = FakeYDL()

        with redirect_stderr(StringIO()):
            result = download_items(
                ydl,
                [
                    (1, "https://example.test/video?p=1"),
                    (2, "https://example.test/video?p=2"),
                    (3, "https://example.test/video?p=3"),
                ],
            )

        self.assertEqual(result.succeeded_episodes, [1, 3])
        self.assertEqual(result.failed_episodes, [2])
        self.assertEqual(
            ydl.downloaded,
            [
                "https://example.test/video?p=1",
                "https://example.test/video?p=2",
                "https://example.test/video?p=3",
            ],
        )

    def test_format_download_report_includes_counts_and_failed_episodes(self):
        class Result:
            succeeded_episodes = [1, 3]
            failed_episodes = [2]

        self.assertEqual(
            format_download_report(Result()),
            [
                "Download summary: succeeded 2, failed 1",
                "Failed episodes: 2",
            ],
        )


class MetadataTests(unittest.TestCase):
    def test_summarizes_playlist_metadata(self):
        summary = summarize_metadata(
            {
                "_type": "playlist",
                "title": "唐诗三百首",
                "entries": [{"url": "p=1"}, {"url": "p=2"}],
            }
        )

        self.assertTrue(summary.is_playlist)
        self.assertEqual(summary.total_episodes, 2)
        self.assertEqual(summary.title, "唐诗三百首")

    def test_summarizes_single_video_metadata(self):
        summary = summarize_metadata({"title": "单个视频"})

        self.assertFalse(summary.is_playlist)
        self.assertEqual(summary.total_episodes, 1)
        self.assertEqual(summary.title, "单个视频")


class PathTests(unittest.TestCase):
    def test_default_download_dir_uses_home_downloads(self):
        self.assertEqual(default_download_dir(Path("C:/Users/Ada")), Path("C:/Users/Ada/Downloads"))


class OutputTests(unittest.TestCase):
    def test_safe_print_flushes_stream(self):
        class FlushTrackingStream(StringIO):
            def __init__(self):
                super().__init__()
                self.flushed = False

            def flush(self):
                self.flushed = True
                super().flush()

        stream = FlushTrackingStream()

        safe_print("line", file=stream)

        self.assertTrue(stream.flushed)

    def test_safe_print_does_not_fail_on_non_utf8_stream(self):
        raw = BytesIO()
        stream = TextIOWrapper(raw, encoding="cp1252", errors="strict")

        safe_print("标题：唐诗三百首", file=stream)
        stream.flush()

        self.assertIn(b"?????", raw.getvalue())

    def test_configure_stream_utf8_preserves_chinese_output(self):
        raw = BytesIO()
        stream = TextIOWrapper(raw, encoding="cp1252", errors="strict")

        configure_stream_utf8(stream)
        safe_print("标题：唐诗三百首", file=stream)
        stream.flush()

        self.assertIn("标题：唐诗三百首".encode("utf-8"), raw.getvalue())

    def test_emit_download_event_outputs_utf8_json_when_enabled(self):
        stdout = StringIO()

        with (
            redirect_stdout(stdout),
            patch.dict("os.environ", {"BILI_DOWNLOADER_EVENTS": "1"}),
        ):
            emit_download_event("item_progress", episode=1, percent=68.5, name="中文标题")

        line = stdout.getvalue().strip()
        self.assertTrue(line.startswith(DOWNLOAD_EVENT_PREFIX))
        payload = json.loads(line.removeprefix(DOWNLOAD_EVENT_PREFIX))
        self.assertEqual(payload["type"], "item_progress")
        self.assertEqual(payload["episode"], 1)
        self.assertEqual(payload["percent"], 68.5)
        self.assertEqual(payload["name"], "中文标题")

    def test_emit_download_event_is_silent_by_default(self):
        stdout = StringIO()

        with (
            redirect_stdout(stdout),
            patch.dict("os.environ", {}, clear=True),
        ):
            emit_download_event("item_progress", episode=1, percent=68.5)

        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
