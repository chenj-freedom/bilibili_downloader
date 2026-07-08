import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class VideoSummary:
    title: str
    is_playlist: bool
    total_episodes: int


@dataclass
class DownloadResult:
    succeeded_episodes: list
    failed_episodes: list


def safe_print(*values, sep=" ", end="\n", file=None):
    stream = sys.stdout if file is None else file
    text = sep.join(str(value) for value in values) + end
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = stream.encoding or "utf-8"
        stream.write(text.encode(encoding, errors="replace").decode(encoding))


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


def current_episode_from_url(url):
    values = parse_qs(urlsplit(url).query).get("p", [])
    if not values or not values[0].isdigit():
        return 1
    return int(values[0])


def determine_download_plan(url, episode_selection, summary):
    if not episode_selection:
        return url, [current_episode_from_url(url)]
    normalized_url = normalize_bilibili_url(url)
    return normalized_url, parse_episode_selection(episode_selection, summary.total_episodes)


def build_download_urls(url, summary, episodes):
    if summary.total_episodes > 1:
        parts = urlsplit(url)
        if parts.query:
            return [url]
        return [build_episode_url(url, episode) for episode in episodes]
    return [url]


def build_download_items(url, summary, episodes):
    urls = build_download_urls(url, summary, episodes)
    return list(zip(episodes, urls))


def download_items(ydl, items):
    result = DownloadResult(succeeded_episodes=[], failed_episodes=[])
    for episode, url in items:
        try:
            download_code = ydl.download([url])
        except Exception as exc:
            result.failed_episodes.append(episode)
            safe_print(f"Episode {episode} failed: {exc}", file=sys.stderr)
            continue

        if download_code == 0:
            result.succeeded_episodes.append(episode)
        else:
            result.failed_episodes.append(episode)
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


def download_audio(url, summary, episodes, output_dir):
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed. Run: python -m pip install -U yt-dlp") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    items = build_download_items(url, summary, episodes)

    options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "outtmpl": str(output_dir / "%(title).200B-%(id)s.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "0",
            }
        ],
    }
    with YoutubeDL(options) as ydl:
        return download_items(ydl, items)


def create_parser():
    parser = argparse.ArgumentParser(
        description="Download audio from a Bilibili video or multi-part playlist."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Bilibili video URL.",
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
        default="audio",
        help="Media type to download. Video is reserved as a TODO.",
    )
    return parser


def main(argv=None):
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.media == "video":
        safe_print("Video download is TODO and not implemented yet.", file=sys.stderr)
        return 2

    try:
        metadata_url = normalize_bilibili_url(args.input) if args.episodes else args.input
        info = fetch_metadata(metadata_url)
        summary = summarize_metadata(info)
        download_url, episodes = determine_download_plan(args.input, args.episodes, summary)
        kind = "playlist" if summary.is_playlist else "single video"
        safe_print(f"Detected {kind}: {summary.title}")
        safe_print(f"Total episodes: {summary.total_episodes}")
        safe_print(f"Downloading episodes: {','.join(str(episode) for episode in episodes)}")
        safe_print(f"Output directory: {args.output}")
        result = download_audio(download_url, summary, episodes, args.output)
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
