import json
import subprocess
import sys
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from scripts import bilibili_web
from scripts.bilibili_downloader import DOWNLOAD_EVENT_PREFIX
from scripts.bilibili_web import (
    apply_downloader_event,
    apply_log_line,
    build_download_command,
    build_retry_payload,
    detect_tools,
    parse_downloader_event,
    parse_download_progress,
    parse_log_episode_list,
    resolve_static_path,
    retry_job_item,
    seed_items_from_payload,
    split_output_lines,
    stop_job,
)


class WebCommandTests(unittest.TestCase):
    def test_web_script_help_runs_when_called_by_path(self):
        result = subprocess.run(
            [sys.executable, "scripts/bilibili_web.py", "--help"],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Start the local Bilibili Downloader web UI.", result.stdout)

    def test_build_download_command_omits_auto_media_and_empty_options(self):
        command = build_download_command(
            {
                "url": "https://www.bilibili.com/video/BVtest",
                "media": "auto",
                "episodes": "",
                "output": "",
            }
        )

        self.assertEqual(
            command,
            [
                sys.executable,
                str(Path("scripts/bilibili_downloader.py")),
                "-i",
                "https://www.bilibili.com/video/BVtest",
            ],
        )

    def test_build_download_command_includes_explicit_options(self):
        command = build_download_command(
            {
                "url": "https://www.bilibili.com/video/BVtest",
                "media": "audio",
                "episodes": "1,2,5",
                "output": "C:/Downloads/bilibili",
            }
        )

        self.assertEqual(
            command,
            [
                sys.executable,
                str(Path("scripts/bilibili_downloader.py")),
                "-i",
                "https://www.bilibili.com/video/BVtest",
                "-e",
                "1,2,5",
                "-o",
                "C:/Downloads/bilibili",
                "-m",
                "audio",
            ],
        )

    def test_build_download_command_rejects_missing_url(self):
        with self.assertRaises(ValueError):
            build_download_command({"url": "   ", "media": "auto"})

    def test_build_download_command_rejects_invalid_media(self):
        with self.assertRaises(ValueError):
            build_download_command(
                {
                    "url": "https://www.bilibili.com/video/BVtest",
                    "media": "danger",
                }
            )


class StaticPathTests(unittest.TestCase):
    def test_resolve_static_path_serves_index_for_root(self):
        web_root = Path("web")

        self.assertEqual(resolve_static_path("/", web_root), web_root / "index.html")

    def test_resolve_static_path_rejects_path_traversal(self):
        web_root = Path("web")

        self.assertIsNone(resolve_static_path("/../README.md", web_root))

    def test_static_files_are_not_cached(self):
        server = bilibili_web.create_server(0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            response = urllib.request.urlopen(f"http://{bilibili_web.HOST}:{port}/app.js", timeout=3)
            self.assertEqual(response.headers["Cache-Control"], "no-store, max-age=0")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_tools_api_returns_detected_tool_status(self):
        server = bilibili_web.create_server(0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch("scripts.bilibili_web.shutil.which", return_value="C:/Tools/ffmpeg.exe"):
                response = urllib.request.urlopen(f"http://{bilibili_web.HOST}:{port}/api/tools", timeout=3)
                data = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        self.assertTrue(data["ok"])
        self.assertTrue(data["tools"]["python"]["ok"])
        self.assertEqual(data["tools"]["ffmpeg"]["path"], "C:/Tools/ffmpeg.exe")


class ToolDetectionTests(unittest.TestCase):
    def test_detect_tools_reports_missing_ffmpeg(self):
        with patch("scripts.bilibili_web.shutil.which", return_value=None):
            result = detect_tools()

        self.assertFalse(result["ok"])
        self.assertTrue(result["tools"]["python"]["ok"])
        self.assertFalse(result["tools"]["ffmpeg"]["ok"])
        self.assertIn("ffmpeg", result["missing"])


class WebAssetLayoutTests(unittest.TestCase):
    def test_index_places_download_list_next_to_form_and_log_below(self):
        html = Path("web/index.html").read_text(encoding="utf-8")

        self.assertIn('class="top-grid"', html)
        self.assertIn('id="download-pagination"', html)
        self.assertLess(html.index('class="top-grid"'), html.index('class="panel log-panel"'))
        self.assertIn('id="page-first"', html)
        self.assertIn('id="page-prev"', html)
        self.assertIn('id="page-next"', html)
        self.assertIn('id="page-last"', html)

    def test_frontend_has_download_list_pagination_controls(self):
        script = Path("web/app.js").read_text(encoding="utf-8")

        self.assertIn("const DOWNLOAD_PAGE_SIZE = 4;", script)
        self.assertIn("function getPageCount", script)
        self.assertIn("pageFirstButton.addEventListener", script)
        self.assertIn("pagePrevButton.addEventListener", script)
        self.assertIn("pageNextButton.addEventListener", script)
        self.assertIn("pageLastButton.addEventListener", script)

    def test_download_list_uses_fixed_page_height(self):
        style = Path("web/style.css").read_text(encoding="utf-8")

        self.assertIn("--download-item-height: 86px;", style)
        self.assertIn("height: calc(var(--download-item-height) * 4 + var(--download-list-gap) * 3);", style)

    def test_index_has_tool_check_tip(self):
        html = Path("web/index.html").read_text(encoding="utf-8")

        self.assertIn('id="tool-tip"', html)
        self.assertIn('id="tool-tip-message"', html)
        self.assertIn('id="tool-recheck"', html)

    def test_frontend_checks_tools_and_hides_success_tip(self):
        script = Path("web/app.js").read_text(encoding="utf-8")

        self.assertIn("async function checkTools", script)
        self.assertIn('fetch("/api/tools")', script)
        self.assertIn("toolRecheckButton.addEventListener", script)
        self.assertIn("setTimeout(hideToolTip, 3000)", script)


class SubprocessEnvironmentTests(unittest.TestCase):
    def test_build_subprocess_env_forces_python_utf8_output(self):
        self.assertTrue(hasattr(bilibili_web, "build_subprocess_env"))

        env = bilibili_web.build_subprocess_env({"PATH": "C:/Tools"})

        self.assertEqual(env["PATH"], "C:/Tools")
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(env["PYTHONUTF8"], "1")
        self.assertEqual(env["BILI_DOWNLOADER_EVENTS"], "1")

    def test_run_job_preserves_chinese_output(self):
        job_id = "encoding-test"
        command = [sys.executable, "-c", "print('中文标题《悬溺》')"]
        with bilibili_web.JOBS_LOCK:
            bilibili_web.JOBS[job_id] = {
                "status": "running",
                "return_code": None,
                "logs": [],
                "command": command,
                "error": None,
            }

        try:
            bilibili_web.run_job(job_id, command)
            job = bilibili_web.snapshot_job(job_id)
        finally:
            with bilibili_web.JOBS_LOCK:
                bilibili_web.JOBS.pop(job_id, None)

        self.assertIsNotNone(job)
        self.assertIn("中文标题《悬溺》", job["logs"])

    def test_run_job_consumes_events_from_child_process(self):
        job_id = "event-child-test"
        command = [
            sys.executable,
            "-c",
            (
                "from scripts.bilibili_downloader import emit_download_event; "
                "emit_download_event('plan', title='T', episodes=[1], total=1, media='audio'); "
                "emit_download_event('item_completed', episode=1, percent=100)"
            ),
        ]
        with bilibili_web.JOBS_LOCK:
            bilibili_web.JOBS[job_id] = {
                "status": "running",
                "return_code": None,
                "logs": [],
                "items": [],
                "command": command,
                "payload": {},
                "error": None,
            }

        try:
            bilibili_web.run_job(job_id, command)
            job = bilibili_web.snapshot_job(job_id)
        finally:
            with bilibili_web.JOBS_LOCK:
                bilibili_web.JOBS.pop(job_id, None)

        self.assertEqual(job["items"][0]["status"], "completed")
        self.assertEqual(job["items"][0]["progress"], 100)

    def test_run_job_shows_progress_events_in_logs_before_child_process_exits(self):
        job_id = "event-progress-log-child-test"
        command = [
            sys.executable,
            "-c",
            (
                "import time; "
                "from scripts.bilibili_downloader import emit_download_event; "
                "emit_download_event('item_started', episode=1, total=1); "
                "emit_download_event('item_progress', episode=1, percent=68.5, size_bytes=5484052); "
                "time.sleep(1.0)"
            ),
        ]
        with bilibili_web.JOBS_LOCK:
            bilibili_web.JOBS[job_id] = {
                "status": "running",
                "return_code": None,
                "logs": [],
                "items": [],
                "command": command,
                "payload": {},
                "error": None,
                "process": None,
                "stop_requested": False,
            }

        thread = threading.Thread(target=bilibili_web.run_job, args=(job_id, command), daemon=True)
        thread.start()
        try:
            observed = False
            for _ in range(20):
                job = bilibili_web.snapshot_job(job_id)
                if job and "[download] 68.5% of 5.23MiB" in job["logs"]:
                    observed = True
                    break
                threading.Event().wait(0.05)
            self.assertTrue(observed, "Structured progress events should also be visible in logs.")
        finally:
            try:
                stop_job(job_id)
            except ValueError:
                pass
            thread.join(timeout=3)
            with bilibili_web.JOBS_LOCK:
                bilibili_web.JOBS.pop(job_id, None)

    def test_run_job_consumes_album_plan_from_child_process(self):
        job_id = "album-plan-child-test"
        command = [
            sys.executable,
            "-c",
            (
                "from scripts.bilibili_downloader import emit_download_event; "
                "emit_download_event('plan', title='Album', episodes=list(range(1, 14)), total=13, media='audio')"
            ),
        ]
        with bilibili_web.JOBS_LOCK:
            bilibili_web.JOBS[job_id] = {
                "status": "running",
                "return_code": None,
                "logs": [],
                "items": [],
                "command": command,
                "payload": {},
                "error": None,
            }

        try:
            bilibili_web.run_job(job_id, command)
            job = bilibili_web.snapshot_job(job_id)
        finally:
            with bilibili_web.JOBS_LOCK:
                bilibili_web.JOBS.pop(job_id, None)

        self.assertEqual(len(job["items"]), 13)
        self.assertEqual(job["items"][0]["name"], "Album - 1")
        self.assertEqual(job["items"][-1]["name"], "Album - 13")

    def test_run_job_updates_items_from_plain_logs_during_child_process(self):
        job_id = "plain-log-progress-child-test"
        command = [
            sys.executable,
            "-c",
            (
                "import time; "
                "print('Downloading episodes: 1,2,3', flush=True); "
                "print('Downloading playlist item 2 of 3', flush=True); "
                "print('[download] 23.2% of 8.63MiB at 1MiB/s', flush=True); "
                "time.sleep(0.2); "
                "print('[download] 46.3% of 8.63MiB at 1MiB/s', flush=True); "
                "time.sleep(0.2)"
            ),
        ]
        with bilibili_web.JOBS_LOCK:
            bilibili_web.JOBS[job_id] = {
                "status": "running",
                "return_code": None,
                "logs": [],
                "items": [],
                "command": command,
                "payload": {},
                "error": None,
                "process": None,
                "stop_requested": False,
            }

        thread = threading.Thread(target=bilibili_web.run_job, args=(job_id, command), daemon=True)
        thread.start()
        try:
            observed = None
            for _ in range(20):
                job = bilibili_web.snapshot_job(job_id)
                if job and len(job["items"]) == 3 and job["items"][1]["progress"] >= 23.2:
                    observed = job
                    break
                threading.Event().wait(0.05)
            self.assertIsNotNone(observed)
            self.assertEqual(observed["items"][1]["status"], "downloading")
        finally:
            thread.join(timeout=3)
            with bilibili_web.JOBS_LOCK:
                bilibili_web.JOBS.pop(job_id, None)

    def test_run_job_keeps_carriage_return_progress_in_logs(self):
        job_id = "carriage-return-log-test"
        command = [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.stdout.write('[download] 0.0% of 5MiB\\r[download] 23.2% of 5MiB\\r[download] 46.3% of 5MiB\\n'); "
                "sys.stdout.flush()"
            ),
        ]
        with bilibili_web.JOBS_LOCK:
            bilibili_web.JOBS[job_id] = {
                "status": "running",
                "return_code": None,
                "logs": [],
                "items": [],
                "command": command,
                "payload": {},
                "error": None,
                "process": None,
                "stop_requested": False,
            }

        try:
            bilibili_web.run_job(job_id, command)
            job = bilibili_web.snapshot_job(job_id)
        finally:
            with bilibili_web.JOBS_LOCK:
                bilibili_web.JOBS.pop(job_id, None)

        self.assertIn("[download] 0.0% of 5MiB", job["logs"])
        self.assertIn("[download] 23.2% of 5MiB", job["logs"])
        self.assertIn("[download] 46.3% of 5MiB", job["logs"])

    def test_run_job_streams_flushed_carriage_return_progress_before_exit(self):
        job_id = "carriage-return-stream-test"
        command = [
            sys.executable,
            "-c",
            (
                "import sys, time; "
                "sys.stdout.write('[download] 0.0% of 5MiB\\r'); "
                "sys.stdout.flush(); "
                "time.sleep(0.1); "
                "sys.stdout.write('[download] 23.2% of 5MiB\\r'); "
                "sys.stdout.flush(); "
                "time.sleep(1.0)"
            ),
        ]
        with bilibili_web.JOBS_LOCK:
            bilibili_web.JOBS[job_id] = {
                "status": "running",
                "return_code": None,
                "logs": [],
                "items": [],
                "command": command,
                "payload": {},
                "error": None,
                "process": None,
                "stop_requested": False,
            }

        thread = threading.Thread(target=bilibili_web.run_job, args=(job_id, command), daemon=True)
        thread.start()
        try:
            observed = False
            for _ in range(20):
                job = bilibili_web.snapshot_job(job_id)
                if job and "[download] 23.2% of 5MiB" in job["logs"]:
                    observed = True
                    break
                threading.Event().wait(0.05)
            self.assertTrue(observed, "Progress should appear before the child process exits.")
        finally:
            try:
                stop_job(job_id)
            except ValueError:
                pass
            thread.join(timeout=3)
            with bilibili_web.JOBS_LOCK:
                bilibili_web.JOBS.pop(job_id, None)


class DownloadEventTests(unittest.TestCase):
    def test_parse_downloader_event_returns_payload_for_event_line(self):
        event = parse_downloader_event(
            DOWNLOAD_EVENT_PREFIX + '{"type":"item_progress","episode":2,"percent":68.5}'
        )

        self.assertEqual(event["type"], "item_progress")
        self.assertEqual(event["episode"], 2)
        self.assertEqual(event["percent"], 68.5)

    def test_parse_downloader_event_finds_event_after_carriage_return_progress(self):
        event = parse_downloader_event(
            "\r[download] 23.2% of 8.63MiB"
            + DOWNLOAD_EVENT_PREFIX
            + '{"type":"item_progress","episode":2,"percent":23.2}'
        )

        self.assertEqual(event["type"], "item_progress")
        self.assertEqual(event["episode"], 2)
        self.assertEqual(event["percent"], 23.2)

    def test_parse_downloader_event_ignores_normal_log_line(self):
        self.assertIsNone(parse_downloader_event("[download] 68% of 4.86MiB"))

    def test_split_output_lines_splits_carriage_return_progress_updates(self):
        self.assertEqual(
            split_output_lines(
                "[download] 0.0% of 5MiB\r[download] 23.2% of 5MiB\r[download] 46.3% of 5MiB\n"
            ),
            [
                "[download] 0.0% of 5MiB",
                "[download] 23.2% of 5MiB",
                "[download] 46.3% of 5MiB",
            ],
        )

    def test_parse_log_episode_list_reads_downloading_episodes(self):
        self.assertEqual(parse_log_episode_list("Downloading episodes: 1,2,3,13"), [1, 2, 3, 13])

    def test_parse_download_progress_reads_yt_dlp_percent(self):
        self.assertEqual(parse_download_progress("[download] 23.2% of 8.63MiB at 6.24MiB/s"), 23.2)

    def test_apply_log_line_creates_album_items_and_updates_progress(self):
        job = {"items": [], "active_episode": None}

        apply_log_line(job, "Downloading episodes: 1,2,3")
        apply_log_line(job, "Downloading playlist item 2 of 3")
        apply_log_line(job, "[download] 46.3% of 8.63MiB at 6.11MiB/s ETA 00:00")

        self.assertEqual(len(job["items"]), 3)
        self.assertEqual(job["active_episode"], 2)
        self.assertEqual(job["items"][1]["status"], "downloading")
        self.assertEqual(job["items"][1]["progress"], 46.3)

    def test_apply_plan_event_creates_pending_items(self):
        job = {"items": []}

        apply_downloader_event(
            job,
            {"type": "plan", "episodes": [1, 3], "total": 5, "title": "合集标题"},
        )

        self.assertEqual(
            job["items"],
            [
                {
                    "id": "1",
                    "episode": 1,
                    "name": "合集标题 - 1",
                    "status": "pending",
                    "progress": 0,
                    "error": None,
                },
                {
                    "id": "3",
                    "episode": 3,
                    "name": "合集标题 - 3",
                    "status": "pending",
                    "progress": 0,
                    "error": None,
                },
            ],
        )

    def test_apply_item_events_update_existing_item(self):
        job = {"items": []}
        apply_downloader_event(job, {"type": "item_started", "episode": 2, "total": 5})
        apply_downloader_event(
            job,
            {
                "type": "item_progress",
                "episode": 2,
                "percent": 68.5,
                "name": "中文标题",
            },
        )
        apply_downloader_event(job, {"type": "item_failed", "episode": 2, "error": "network"})

        self.assertEqual(job["items"][0]["id"], "2")
        self.assertEqual(job["items"][0]["name"], "中文标题")
        self.assertEqual(job["items"][0]["status"], "failed")
        self.assertEqual(job["items"][0]["progress"], 68.5)
        self.assertEqual(job["items"][0]["error"], "network")

    def test_build_retry_payload_retries_one_episode(self):
        payload = {
            "url": "https://www.bilibili.com/video/BVtest",
            "episodes": "all",
            "media": "video",
            "output": "C:/Downloads",
        }

        retry_payload = build_retry_payload(payload, "3")

        self.assertEqual(
            retry_payload,
            {
                "url": "https://www.bilibili.com/video/BVtest",
                "episodes": "3",
                "media": "video",
                "output": "C:/Downloads",
            },
        )

    def test_seed_items_from_payload_uses_explicit_episode_list(self):
        self.assertEqual(
            seed_items_from_payload({"episodes": "1,3-4"}),
            [
                {
                    "id": "1",
                    "episode": 1,
                    "name": "下载项 1",
                    "status": "pending",
                    "progress": 0,
                    "error": None,
                },
                {
                    "id": "3",
                    "episode": 3,
                    "name": "下载项 3",
                    "status": "pending",
                    "progress": 0,
                    "error": None,
                },
                {
                    "id": "4",
                    "episode": 4,
                    "name": "下载项 4",
                    "status": "pending",
                    "progress": 0,
                    "error": None,
                },
            ],
        )

    def test_seed_items_from_payload_defaults_to_one_item(self):
        self.assertEqual(seed_items_from_payload({"episodes": ""})[0]["id"], "1")

    def test_retry_job_item_resets_failed_item_and_builds_one_item_command(self):
        job_id = "retry-test"
        payload = {
            "url": "https://www.bilibili.com/video/BVtest",
            "episodes": "all",
            "media": "video",
            "output": "C:/Downloads",
        }
        with bilibili_web.JOBS_LOCK:
            bilibili_web.JOBS[job_id] = {
                "status": "failed",
                "return_code": 1,
                "logs": [],
                "items": [
                    {
                        "id": "3",
                        "episode": 3,
                        "name": "P3",
                        "status": "failed",
                        "progress": 42,
                        "error": "network",
                    }
                ],
                "command": [],
                "payload": payload,
                "error": None,
            }

        try:
            retry_job_item(job_id, "3", start_thread=False)
            job = bilibili_web.snapshot_job(job_id)
        finally:
            with bilibili_web.JOBS_LOCK:
                bilibili_web.JOBS.pop(job_id, None)

        self.assertEqual(job["status"], "running")
        self.assertEqual(job["return_code"], None)
        self.assertEqual(job["items"][0]["status"], "pending")
        self.assertEqual(job["items"][0]["progress"], 0)
        self.assertEqual(job["items"][0]["error"], None)
        self.assertIn("-e", job["command"])
        self.assertIn("3", job["command"])

    def test_finish_job_marks_seeded_items_when_no_events_arrive(self):
        job = {
            "status": "running",
            "return_code": None,
            "logs": [],
            "items": seed_items_from_payload({"episodes": ""}),
            "command": [],
            "payload": {},
            "error": None,
        }

        bilibili_web.finish_job_state(job, "completed", return_code=0)

        self.assertEqual(job["items"][0]["status"], "completed")
        self.assertEqual(job["items"][0]["progress"], 100)

    def test_stop_job_marks_running_job_stopped(self):
        job_id = "stop-test"
        with bilibili_web.JOBS_LOCK:
            bilibili_web.JOBS[job_id] = {
                "status": "running",
                "return_code": None,
                "logs": [],
                "items": seed_items_from_payload({"episodes": ""}),
                "command": [],
                "payload": {},
                "error": None,
                "process": None,
                "stop_requested": False,
            }

        try:
            stop_job(job_id)
            job = bilibili_web.snapshot_job(job_id)
        finally:
            with bilibili_web.JOBS_LOCK:
                bilibili_web.JOBS.pop(job_id, None)

        self.assertEqual(job["status"], "stopped")
        self.assertEqual(job["items"][0]["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
