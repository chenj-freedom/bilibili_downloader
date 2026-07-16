import argparse
import codecs
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bilibili_downloader import DOWNLOAD_EVENT_PREFIX


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
WEB_ROOT = REPO_ROOT / "web"
DOWNLOADER_SCRIPT = REPO_ROOT / "scripts" / "bilibili_downloader.py"

JOBS = {}
JOBS_LOCK = threading.Lock()
DOWNLOAD_PROGRESS_PATTERN = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
DOWNLOADING_EPISODES_PREFIX = "Downloading episodes:"
PLAYLIST_ITEM_PATTERN = re.compile(r"Downloading playlist item\s+(\d+)\s+of\s+(\d+)")


def build_download_command(payload, downloader_script=None):
    downloader = Path("scripts/bilibili_downloader.py") if downloader_script is None else Path(downloader_script)
    url = str(payload.get("url") or "").strip()
    if not url:
        raise ValueError("Bilibili URL is required.")

    media = str(payload.get("media") or "auto").strip().lower()
    if media not in {"auto", "audio", "video"}:
        raise ValueError("Media must be auto, audio, or video.")

    episodes = str(payload.get("episodes") or "").strip()
    output = str(payload.get("output") or "").strip()

    command = [sys.executable, str(downloader), "-i", url]
    if episodes:
        command.extend(["-e", episodes])
    if output:
        command.extend(["-o", output])
    if media != "auto":
        command.extend(["-m", media])
    return command


def build_subprocess_env(base_env=None):
    env = dict(os.environ if base_env is None else base_env)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["BILI_DOWNLOADER_EVENTS"] = "1"
    return env


def detect_tools(path_env=None, python_executable=None):
    python_path = python_executable or sys.executable
    ffmpeg_path = shutil.which("ffmpeg", path=path_env)
    tools = {
        "python": {
            "ok": bool(python_path and Path(python_path).exists()),
            "path": python_path,
            "version": sys.version.split()[0],
        },
        "ffmpeg": {
            "ok": bool(ffmpeg_path),
            "path": ffmpeg_path,
        },
    }
    missing = [name for name, tool in tools.items() if not tool["ok"]]
    return {"ok": not missing, "tools": tools, "missing": missing}


def parse_downloader_event(line):
    marker_index = line.find(DOWNLOAD_EVENT_PREFIX)
    if marker_index < 0:
        return None
    event_text = line[marker_index + len(DOWNLOAD_EVENT_PREFIX) :]
    try:
        return json.loads(event_text)
    except json.JSONDecodeError:
        return None


def split_output_lines(chunk):
    return [part for part in re.split(r"[\r\n]+", chunk) if part]


def format_size_bytes(size):
    try:
        value = float(size)
    except (TypeError, ValueError):
        return None

    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            if unit == "B":
                return f"{value:.0f}{unit}"
            return f"{value:.2f}{unit}"
        value /= 1024
    return None


def format_eta(seconds):
    try:
        total_seconds = int(seconds)
    except (TypeError, ValueError):
        return None
    if total_seconds < 0:
        return None
    minutes, second = divmod(total_seconds, 60)
    hour, minute = divmod(minutes, 60)
    if hour:
        return f"{hour:02d}:{minute:02d}:{second:02d}"
    return f"{minute:02d}:{second:02d}"


def format_progress_event_log(event):
    if event.get("type") != "item_progress":
        return None
    percent = event.get("percent")
    if percent is None:
        return None

    line = f"[download] {percent}%"
    size = format_size_bytes(event.get("size_bytes"))
    if size:
        line += f" of {size}"
    speed = format_size_bytes(event.get("speed"))
    if speed:
        line += f" at {speed}/s"
    eta = format_eta(event.get("eta"))
    if eta:
        line += f" ETA {eta}"
    return line


def parse_log_episode_list(line):
    if not line.startswith(DOWNLOADING_EPISODES_PREFIX):
        return None
    episodes = []
    for raw_part in line.removeprefix(DOWNLOADING_EPISODES_PREFIX).strip().split(","):
        part = raw_part.strip()
        if part.isdigit():
            episodes.append(int(part))
    return episodes or None


def parse_download_progress(line):
    match = DOWNLOAD_PROGRESS_PATTERN.search(line)
    if match is None:
        return None
    return float(match.group(1))


def build_retry_payload(payload, item_id):
    retry_payload = dict(payload)
    retry_payload["episodes"] = str(item_id)
    return retry_payload


def make_pending_item(episode, name=None):
    item_id = str(episode)
    return {
        "id": item_id,
        "episode": episode,
        "name": name or f"下载项 {item_id}",
        "status": "pending",
        "progress": 0,
        "error": None,
    }


def parse_seed_episodes(selection):
    text = str(selection or "").strip()
    if not text or text.lower() == "all":
        return [1]

    episodes = set()
    for raw_part in text.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            if start_text.isdigit() and end_text.isdigit():
                start = int(start_text)
                end = int(end_text)
                if start <= end:
                    episodes.update(range(start, end + 1))
        elif part.isdigit():
            episodes.add(int(part))

    return sorted(episodes) or [1]


def seed_items_from_payload(payload):
    return [make_pending_item(episode) for episode in parse_seed_episodes(payload.get("episodes"))]


def find_or_create_item(job, episode):
    item_id = str(episode)
    for item in job["items"]:
        if item["id"] == item_id:
            return item

    item = make_pending_item(episode, name=f"Item {item_id}")
    job["items"].append(item)
    return item


def apply_downloader_event(job, event):
    event_type = event.get("type")
    if event_type == "plan":
        title = event.get("title") or "Download"
        job["items"] = []
        for episode in event.get("episodes") or []:
            item = find_or_create_item(job, episode)
            item["name"] = f"{title} - {episode}"
        return

    episode = event.get("episode")
    if episode is None:
        return

    job["active_episode"] = episode
    item = find_or_create_item(job, episode)
    if event_type == "item_started":
        item["status"] = "downloading"
        item["error"] = None
    elif event_type == "item_progress":
        item["status"] = "downloading"
        item["progress"] = event.get("percent") or item["progress"]
        if event.get("name"):
            item["name"] = event["name"]
    elif event_type == "item_completed":
        item["status"] = "completed"
        item["progress"] = 100
        item["error"] = None
    elif event_type == "item_failed":
        item["status"] = "failed"
        item["error"] = event.get("error") or "Download failed."


def apply_log_line(job, line):
    episodes = parse_log_episode_list(line)
    if episodes:
        job["items"] = [make_pending_item(episode) for episode in episodes]
        if len(episodes) == 1:
            job["active_episode"] = episodes[0]
        return

    playlist_match = PLAYLIST_ITEM_PATTERN.search(line)
    if playlist_match:
        episode = int(playlist_match.group(1))
        job["active_episode"] = episode
        item = find_or_create_item(job, episode)
        item["status"] = "downloading"
        item["error"] = None
        return

    progress = parse_download_progress(line)
    if progress is None:
        return

    episode = job.get("active_episode")
    if episode is None:
        for item in job.get("items", []):
            if item["status"] in {"pending", "downloading"}:
                episode = item["episode"]
                job["active_episode"] = episode
                break
    if episode is None:
        episode = 1
        job["active_episode"] = episode

    item = find_or_create_item(job, episode)
    item["status"] = "downloading"
    item["progress"] = progress


def resolve_static_path(request_path, web_root=WEB_ROOT):
    path = unquote(urlsplit(request_path).path)
    if path == "/":
        path = "/index.html"
    relative = path.lstrip("/")
    if not relative:
        relative = "index.html"

    root = Path(web_root)
    candidate = root / relative
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def snapshot_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return None
        return {
            "id": job_id,
            "status": job["status"],
            "return_code": job["return_code"],
            "logs": list(job["logs"]),
            "items": [dict(item) for item in job.get("items", [])],
            "command": list(job["command"]),
            "payload": dict(job.get("payload", {})),
            "error": job.get("error"),
        }


def append_job_log(job_id, line):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is not None:
            job["logs"].append(line)
            apply_log_line(job, line)


def append_job_log_only(job_id, line):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is not None:
            job["logs"].append(line)


def finish_job_state(job, status, return_code=None, error=None):
    job["status"] = status
    job["return_code"] = return_code
    job["error"] = error
    if status == "stopped":
        final_item_status = "stopped"
    else:
        final_item_status = "completed" if status == "completed" else "failed"
    for item in job.get("items", []):
        if item["status"] in {"pending", "downloading"}:
            item["status"] = final_item_status
            if final_item_status == "completed":
                item["progress"] = 100
                item["error"] = None
            elif final_item_status == "stopped":
                item["error"] = None
            elif error:
                item["error"] = error


def apply_job_event(job_id, event):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is not None:
            apply_downloader_event(job, event)


def finish_job(job_id, status, return_code=None, error=None):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is not None:
            finish_job_state(job, status, return_code=return_code, error=error)


def set_job_process(job_id, process):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is not None:
            job["process"] = process


def stop_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise ValueError("Job not found.")
        job["stop_requested"] = True
        process = job.get("process")
        finish_job_state(job, "stopped", return_code=None)

    if process is not None and process.poll() is None:
        process.terminate()
    return job_id


def append_job_output_line(job_id, clean_line):
    event = parse_downloader_event(clean_line)
    if event is not None:
        apply_job_event(job_id, event)
        progress_line = format_progress_event_log(event)
        if progress_line is not None:
            append_job_log_only(job_id, progress_line)
        return
    append_job_log(job_id, clean_line)


def run_job(job_id, command):
    append_job_log(job_id, f"Running: {' '.join(command)}")
    try:
        process = subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            env=build_subprocess_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
    except OSError as exc:
        append_job_log(job_id, f"Failed to start downloader: {exc}")
        finish_job(job_id, "failed", return_code=1, error=str(exc))
        return
    set_job_process(job_id, process)

    assert process.stdout is not None
    pending_output = ""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def consume_output(text):
        nonlocal pending_output
        for character in text:
            if character not in "\r\n":
                pending_output += character
                continue
            if pending_output:
                append_job_output_line(job_id, pending_output)
                pending_output = ""

    try:
        while True:
            data = process.stdout.read(1)
            if data == b"":
                consume_output(decoder.decode(b"", final=True))
                break
            consume_output(decoder.decode(data))
        if pending_output:
            append_job_output_line(job_id, pending_output)
    finally:
        process.stdout.close()

    return_code = process.wait()
    with JOBS_LOCK:
        stop_requested = bool(JOBS.get(job_id, {}).get("stop_requested"))
    status = "stopped" if stop_requested else ("completed" if return_code == 0 else "failed")
    append_job_log(job_id, f"Process exited with code {return_code}.")
    finish_job(job_id, status, return_code=return_code)


def create_job(payload):
    command = build_download_command(payload, downloader_script=DOWNLOADER_SCRIPT)
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "return_code": None,
            "logs": [],
            "items": seed_items_from_payload(payload),
            "command": command,
            "payload": dict(payload),
            "error": None,
            "process": None,
            "stop_requested": False,
        }

    thread = threading.Thread(target=run_job, args=(job_id, command), daemon=True)
    thread.start()
    return job_id


def retry_job_item(job_id, item_id, start_thread=True):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise ValueError("Job not found.")

        retry_payload = build_retry_payload(job["payload"], item_id)
        command = build_download_command(retry_payload, downloader_script=DOWNLOADER_SCRIPT)
        item = find_or_create_item(job, int(item_id))
        item["status"] = "pending"
        item["progress"] = 0
        item["error"] = None
        job["status"] = "running"
        job["return_code"] = None
        job["error"] = None
        job["command"] = command
        job["logs"].append(f"Retrying item {item_id}")
        job["process"] = None
        job["stop_requested"] = False

    if start_thread:
        thread = threading.Thread(target=run_job, args=(job_id, command), daemon=True)
        thread.start()
    return job_id


class BilibiliWebHandler(BaseHTTPRequestHandler):
    server_version = "BilibiliDownloaderWeb/1.0"

    def log_message(self, format, *args):
        return

    def write_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/health":
            self.write_json(200, {"ok": True})
            return

        if self.path == "/api/tools":
            self.write_json(200, detect_tools())
            return

        if self.path.startswith("/api/jobs/"):
            job_id = self.path.rsplit("/", 1)[-1]
            job = snapshot_job(job_id)
            if job is None:
                self.write_json(404, {"error": "Job not found."})
                return
            self.write_json(200, job)
            return

        path = resolve_static_path(self.path)
        if path is None or not path.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.startswith("/api/jobs/") and self.path.endswith("/stop"):
            parts = self.path.strip("/").split("/")
            if len(parts) != 4 or parts[0] != "api" or parts[1] != "jobs":
                self.write_json(404, {"error": "Not found."})
                return
            try:
                stop_job(parts[2])
            except ValueError as exc:
                self.write_json(404, {"error": str(exc)})
                return
            self.write_json(202, {"job_id": parts[2], "status": "stopped"})
            return

        if self.path.startswith("/api/jobs/") and self.path.endswith("/retry"):
            parts = self.path.strip("/").split("/")
            if len(parts) != 6 or parts[0] != "api" or parts[1] != "jobs" or parts[3] != "items":
                self.write_json(404, {"error": "Not found."})
                return
            try:
                retry_job_item(parts[2], parts[4])
            except ValueError as exc:
                self.write_json(404, {"error": str(exc)})
                return
            self.write_json(202, {"job_id": parts[2], "item_id": parts[4]})
            return

        if self.path != "/api/download":
            self.write_json(404, {"error": "Not found."})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.write_json(400, {"error": "Invalid request length."})
            return

        if length <= 0 or length > 65536:
            self.write_json(400, {"error": "Invalid request body."})
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            job_id = create_job(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            self.write_json(400, {"error": str(exc)})
            return

        self.write_json(202, {"job_id": job_id})


def create_server(port):
    return ThreadingHTTPServer((HOST, port), BilibiliWebHandler)


def find_server(start_port=DEFAULT_PORT, attempts=20):
    for port in range(start_port, start_port + attempts):
        try:
            return create_server(port), port
        except OSError:
            continue
    raise RuntimeError(f"No available port found from {start_port} to {start_port + attempts - 1}.")


def create_parser():
    parser = argparse.ArgumentParser(description="Start the local Bilibili Downloader web UI.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Preferred local port.")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    return parser


def main(argv=None):
    args = create_parser().parse_args(argv)
    try:
        server, port = find_server(args.port)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    url = f"http://{HOST}:{port}"
    print(f"Bilibili Downloader Web UI is running at {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
