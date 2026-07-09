import argparse
import gzip
import json
import os
import re
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from urllib import request
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


DOWNLOAD_EVENT_PREFIX = "__BILI_EVENT__"


@dataclass(frozen=True)
class VideoSummary:
    title: str
    is_playlist: bool
    total_episodes: int


@dataclass
class DownloadResult:
    succeeded_episodes: list
    failed_episodes: list


@dataclass(frozen=True)
class BilibiliCollectionItem:
    episode: int
    url: str
    title: str = ""


@dataclass(frozen=True)
class BilibiliCollectionPlan:
    title: str
    items: list


def safe_print(*values, sep=" ", end="\n", file=None):
    stream = sys.stdout if file is None else file
    text = sep.join(str(value) for value in values) + end
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = stream.encoding or "utf-8"
        stream.write(text.encode(encoding, errors="replace").decode(encoding))
    flush = getattr(stream, "flush", None)
    if flush is not None:
        flush()


def download_events_enabled():
    return os.environ.get("BILI_DOWNLOADER_EVENTS") == "1"


def emit_download_event(event_type, **payload):
    if not download_events_enabled():
        return
    event = {"type": event_type}
    event.update(payload)
    safe_print(DOWNLOAD_EVENT_PREFIX + json.dumps(event, ensure_ascii=False))


def create_progress_hook(context):
    def hook(status):
        if status.get("status") != "downloading":
            return
        downloaded = status.get("downloaded_bytes") or 0
        total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
        if not total:
            return
        info = status.get("info_dict") or {}
        name = info.get("title") or Path(status.get("filename") or "").stem or None
        emit_download_event(
            "item_progress",
            episode=context.get("episode"),
            total=context.get("total"),
            percent=round(downloaded * 100 / total, 1),
            name=name,
            size_bytes=total,
            speed=status.get("speed"),
            eta=status.get("eta"),
        )

    return hook


def configure_stream_utf8(stream):
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (TypeError, ValueError, OSError):
        return


def configure_stdio_utf8():
    configure_stream_utf8(sys.stdout)
    configure_stream_utf8(sys.stderr)


def default_download_dir(home=None):
    base = Path.home() if home is None else Path(home)
    return base / "Downloads"


def parse_episode_selection(selection, total_episodes):
    if total_episodes < 1:
        raise ValueError("total episodes must be at least 1")

    if not selection:
        return list(range(1, total_episodes + 1))

    if selection.strip().lower() == "all":
        return list(range(1, total_episodes + 1))

    episodes = set()
    for raw_part in selection.split(","):
        part = raw_part.strip()
        if not part:
            raise ValueError("episode selection contains an empty item")

        if "-" in part:
            start_text, end_text = part.split("-", 1)
            if not start_text.isdigit() or not end_text.isdigit():
                raise ValueError(f"invalid episode range: {part}")
            start = int(start_text)
            end = int(end_text)
            if start > end:
                raise ValueError(f"episode range start is greater than end: {part}")
            episodes.update(range(start, end + 1))
        else:
            if not part.isdigit():
                raise ValueError(f"invalid episode number: {part}")
            episodes.add(int(part))

    ordered = sorted(episodes)
    for episode in ordered:
        if episode < 1 or episode > total_episodes:
            raise ValueError(
                f"episode {episode} is out of range; valid range is 1-{total_episodes}"
            )

    return ordered


def build_episode_url(url, episode):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode({"p": episode}), ""))


def normalize_bilibili_url(url):
    parts = urlsplit(url)
    if "bilibili.com" not in parts.netloc.lower():
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def is_bilibili_video_url(url):
    parts = urlsplit(url)
    return "bilibili.com" in parts.netloc.lower() and parts.path.lower().startswith("/video/")


def extract_bvid(url):
    match = re.search(r"/video/(BV[0-9A-Za-z]+)", urlsplit(url).path)
    if match is None:
        return None
    return match.group(1)


def build_bilibili_video_url(bvid):
    return f"https://www.bilibili.com/video/{bvid}"


def is_bilibili_audio_url(url):
    parts = urlsplit(url)
    return "bilibili.com" in parts.netloc.lower() and parts.path.lower().startswith("/audio/")


def is_bilibili_audio_playlist_url(url):
    parts = urlsplit(url)
    return is_bilibili_audio_url(url) and parts.path.lower().startswith("/audio/am")


def is_bilibili_audio_track_url(url):
    parts = urlsplit(url)
    return is_bilibili_audio_url(url) and parts.path.lower().startswith("/audio/au")


def infer_media_type(url):
    if is_bilibili_audio_url(url):
        return "audio"
    return "video"


def resolve_media_type(requested_media, url):
    if is_bilibili_audio_url(url):
        return "audio"
    return requested_media or infer_media_type(url)


def current_episode_from_url(url):
    values = parse_qs(urlsplit(url).query).get("p", [])
    if not values or not values[0].isdigit():
        return 1
    return int(values[0])


def fetch_text(url):
    req = request.Request(
        url,
        headers={
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "Mozilla/5.0",
        },
    )
    with request.urlopen(req, timeout=20) as response:
        body = response.read()
        encoding = (response.headers.get("Content-Encoding") or "").lower()
    if "gzip" in encoding:
        body = gzip.decompress(body)
    elif "deflate" in encoding:
        body = zlib.decompress(body)
    return body.decode("utf-8", errors="replace")


def extract_initial_state(html):
    match = re.search(r"window\.__INITIAL_STATE__=(.*?);\(function\(\)", html)
    if match is None:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def fetch_bilibili_initial_state(url):
    html = fetch_text(normalize_bilibili_url(url))
    return extract_initial_state(html)


def fetch_bilibili_video_pages(bvid):
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    try:
        data = json.loads(fetch_text(url))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to read Bilibili video metadata for {bvid}") from exc
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to read Bilibili video metadata for {bvid}: {data.get('message')}")
    return (data.get("data") or {}).get("pages") or []


def extract_collection_episodes(state):
    sections_info = (state or {}).get("sectionsInfo") or {}
    sections = sections_info.get("sections") or []
    episodes = []
    for section in sections:
        episodes.extend(
            section.get("episodes")
            or section.get("archives")
            or section.get("ep_list")
            or []
        )
    return sections_info, episodes


def build_bilibili_collection_plan(state, page_fetcher=fetch_bilibili_video_pages):
    sections_info, episodes = extract_collection_episodes(state)
    if not sections_info or not episodes:
        return None

    items = []
    page_cache = {}
    for collection_episode in episodes:
        bvid = collection_episode.get("bvid")
        if not bvid:
            continue
        pages = collection_episode.get("pages")
        if pages is None and bvid not in page_cache:
            page_cache[bvid] = page_fetcher(bvid)
        if pages is None:
            pages = page_cache[bvid]
        pages = pages or []
        base_url = build_bilibili_video_url(bvid)
        if not pages:
            items.append(
                BilibiliCollectionItem(
                    len(items) + 1,
                    base_url,
                    collection_episode.get("title") or "",
                )
            )
            continue
        for page in pages:
            page_number = int(page.get("page") or 1)
            url = build_episode_url(base_url, page_number) if len(pages) > 1 else base_url
            items.append(
                BilibiliCollectionItem(
                    len(items) + 1,
                    url,
                    page.get("part") or collection_episode.get("title") or "",
                )
            )

    if not items:
        return None
    return BilibiliCollectionPlan(
        title=sections_info.get("title") or "Bilibili collection",
        items=items,
    )


def fetch_bilibili_collection_plan(url):
    if not is_bilibili_video_url(url):
        return None
    state = fetch_bilibili_initial_state(url)
    return build_bilibili_collection_plan(state)


def determine_download_plan(url, episode_selection, summary):
    if is_bilibili_audio_playlist_url(url):
        return url, parse_episode_selection(episode_selection or "all", summary.total_episodes)
    if is_bilibili_audio_track_url(url):
        return url, [1]
    if not episode_selection:
        return url, [current_episode_from_url(url)]
    normalized_url = normalize_bilibili_url(url)
    return normalized_url, parse_episode_selection(episode_selection, summary.total_episodes)


def build_download_urls(url, summary, episodes):
    if is_bilibili_audio_playlist_url(url):
        return [url for _episode in episodes]
    if summary.total_episodes > 1:
        parts = urlsplit(url)
        if parts.query:
            return [url]
        return [build_episode_url(url, episode) for episode in episodes]
    return [url]


def build_download_items(url, summary, episodes):
    urls = build_download_urls(url, summary, episodes)
    return list(zip(episodes, urls))


def download_items(ydl, items, total_episodes=None, progress_context=None):
    result = DownloadResult(succeeded_episodes=[], failed_episodes=[])
    for episode, url in items:
        if progress_context is not None:
            progress_context["episode"] = episode
            progress_context["total"] = total_episodes or len(items)
        emit_download_event("item_started", episode=episode, total=total_episodes or len(items), url=url)
        if total_episodes and total_episodes > 1:
            safe_print(f"Downloading playlist item {episode} of {total_episodes}")
        try:
            download_code = ydl.download([url])
        except Exception as exc:
            result.failed_episodes.append(episode)
            emit_download_event("item_failed", episode=episode, error=str(exc))
            safe_print(f"Episode {episode} failed: {exc}", file=sys.stderr)
            continue

        if download_code == 0:
            result.succeeded_episodes.append(episode)
            emit_download_event("item_completed", episode=episode, percent=100)
        else:
            result.failed_episodes.append(episode)
            emit_download_event(
                "item_failed",
                episode=episode,
                error=f"exit code {download_code}",
            )
            safe_print(f"Episode {episode} failed with exit code {download_code}", file=sys.stderr)
    return result


def format_download_report(result):
    lines = [
        f"Download summary: succeeded {len(result.succeeded_episodes)}, failed {len(result.failed_episodes)}"
    ]
    if result.failed_episodes:
        failed = ",".join(str(episode) for episode in result.failed_episodes)
        lines.append(f"Failed episodes: {failed}")
    return lines


def summarize_metadata(info):
    entries = info.get("entries") or []
    is_playlist = info.get("_type") == "playlist" and len(entries) > 1
    total = len(entries) if is_playlist else 1
    return VideoSummary(
        title=info.get("title") or "Untitled",
        is_playlist=is_playlist,
        total_episodes=total,
    )


def fetch_metadata(url):
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed. Run: python -m pip install -U yt-dlp") from exc

    options = {
        "extract_flat": True,
        "quiet": True,
        "skip_download": True,
    }
    with YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


def build_audio_options(output_dir, playlist_items=None, progress_hooks=None):
    options = {
        "format": "bestaudio/best",
        "noplaylist": playlist_items is None,
        "outtmpl": str(output_dir / "%(title).200B-%(id)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ],
    }
    if playlist_items is not None:
        options["playlist_items"] = playlist_items
    if progress_hooks:
        options["progress_hooks"] = progress_hooks
    return options


def build_video_options(output_dir, progress_hooks=None):
    options = {
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "outtmpl": str(output_dir / "%(title).200B-%(id)s.%(ext)s"),
    }
    if progress_hooks:
        options["progress_hooks"] = progress_hooks
    return options


def download_audio(url, summary, episodes, output_dir, download_items_override=None):
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed. Run: python -m pip install -U yt-dlp") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    items = download_items_override or build_download_items(url, summary, episodes)
    progress_context = {"episode": None, "total": summary.total_episodes}
    progress_hooks = [create_progress_hook(progress_context)]

    if download_items_override is None and is_bilibili_audio_playlist_url(url):
        result = DownloadResult(succeeded_episodes=[], failed_episodes=[])
        for episode, item_url in items:
            with YoutubeDL(
                build_audio_options(
                    output_dir,
                    playlist_items=str(episode),
                    progress_hooks=progress_hooks,
                )
            ) as ydl:
                episode_result = download_items(
                    ydl,
                    [(episode, item_url)],
                    total_episodes=summary.total_episodes,
                    progress_context=progress_context,
                )
            result.succeeded_episodes.extend(episode_result.succeeded_episodes)
            result.failed_episodes.extend(episode_result.failed_episodes)
        return result

    with YoutubeDL(build_audio_options(output_dir, progress_hooks=progress_hooks)) as ydl:
        return download_items(
            ydl,
            items,
            total_episodes=summary.total_episodes,
            progress_context=progress_context,
        )


def download_video(url, summary, episodes, output_dir, download_items_override=None):
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed. Run: python -m pip install -U yt-dlp") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    items = download_items_override or build_download_items(url, summary, episodes)
    progress_context = {"episode": None, "total": summary.total_episodes}
    progress_hooks = [create_progress_hook(progress_context)]

    with YoutubeDL(build_video_options(output_dir, progress_hooks=progress_hooks)) as ydl:
        return download_items(
            ydl,
            items,
            total_episodes=summary.total_episodes,
            progress_context=progress_context,
        )


def create_parser():
    parser = argparse.ArgumentParser(
        description="Download audio or video from a Bilibili video or multi-part playlist."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Bilibili URL.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=default_download_dir(),
        help="Output directory. Defaults to the system Downloads directory.",
    )
    parser.add_argument(
        "-e",
        "--episodes",
        help="Episodes to download, such as 1-5, 1,2,6, or all. Defaults to the input link only.",
    )
    parser.add_argument(
        "-m",
        "--media",
        choices=("audio", "video"),
        help="Media type to download. Defaults to the type inferred from the input URL.",
    )
    return parser


def main(argv=None):
    configure_stdio_utf8()
    parser = create_parser()
    args = parser.parse_args(argv)

    try:
        download_items_override = None
        collection_plan = None
        if args.episodes and is_bilibili_video_url(args.input):
            try:
                collection_plan = fetch_bilibili_collection_plan(args.input)
            except (RuntimeError, OSError, ValueError):
                collection_plan = None

        if collection_plan is not None:
            summary = VideoSummary(collection_plan.title, True, len(collection_plan.items))
            download_url = normalize_bilibili_url(args.input)
            episodes = parse_episode_selection(args.episodes, summary.total_episodes)
            selected_episodes = set(episodes)
            download_items_override = [
                (item.episode, item.url)
                for item in collection_plan.items
                if item.episode in selected_episodes
            ]
            kind = "collection"
        else:
            metadata_url = normalize_bilibili_url(args.input) if args.episodes else args.input
            info = fetch_metadata(metadata_url)
            summary = summarize_metadata(info)
            download_url, episodes = determine_download_plan(args.input, args.episodes, summary)
            kind = "playlist" if summary.is_playlist else "single video"

        safe_print(f"Detected {kind}: {summary.title}")
        safe_print(f"Total episodes: {summary.total_episodes}")
        safe_print(f"Downloading episodes: {','.join(str(episode) for episode in episodes)}")
        safe_print(f"Output directory: {args.output}")
        media = resolve_media_type(args.media, args.input)
        if args.episodes and is_bilibili_audio_track_url(args.input):
            safe_print(
                "Warning: single audio URL detected; ignoring --episodes.",
                file=sys.stderr,
            )
        if args.media == "video" and is_bilibili_audio_url(args.input):
            safe_print(
                "Warning: audio URL detected; ignoring --media video and using audio mode.",
                file=sys.stderr,
            )
        emit_download_event(
            "plan",
            title=summary.title,
            episodes=episodes,
            total=summary.total_episodes,
            media=media,
        )
        safe_print(f"Media type: {media}")
        download = download_video if media == "video" else download_audio
        if download_items_override is None:
            result = download(download_url, summary, episodes, args.output)
        else:
            result = download(
                download_url,
                summary,
                episodes,
                args.output,
                download_items_override=download_items_override,
            )
        for line in format_download_report(result):
            safe_print(line)
        return 1 if result.failed_episodes else 0
    except ValueError as exc:
        parser.error(str(exc))
    except RuntimeError as exc:
        safe_print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
