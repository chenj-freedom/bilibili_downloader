import unittest
from contextlib import redirect_stderr
from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path

from scripts.bilibili_downloader import (
    build_episode_url,
    build_download_items,
    build_download_urls,
    default_download_dir,
    determine_download_plan,
    download_items,
    format_download_report,
    normalize_bilibili_url,
    parse_episode_selection,
    safe_print,
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


class DownloadExecutionTests(unittest.TestCase):
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
    def test_safe_print_does_not_fail_on_non_utf8_stream(self):
        raw = BytesIO()
        stream = TextIOWrapper(raw, encoding="cp1252", errors="strict")

        safe_print("标题：唐诗三百首", file=stream)
        stream.flush()

        self.assertIn(b"?????", raw.getvalue())


if __name__ == "__main__":
    unittest.main()
