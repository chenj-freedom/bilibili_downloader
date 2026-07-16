# Bilibili Downloader

<p align="center">
  <img src="web/banner.png" width="100%" alt="Bilibili Downloader banner">
</p>

<p align="center">
  <a href="https://github.com/chenj-freedom/bilibili_downloader/stargazers"><img src="https://img.shields.io/github/stars/chenj-freedom/bilibili_downloader?style=for-the-badge&logo=github&color=FB7299" alt="GitHub stars"></a>
  <a href="https://github.com/chenj-freedom/bilibili_downloader/commits/main"><img src="https://img.shields.io/github/last-commit/chenj-freedom/bilibili_downloader?style=for-the-badge&logo=github&color=00C4D9" alt="Last commit"></a>
  <img src="https://img.shields.io/badge/Python-3-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3">
  <img src="https://img.shields.io/badge/FFmpeg-required-007808?style=for-the-badge&logo=ffmpeg&logoColor=white" alt="FFmpeg required">
  <img src="https://img.shields.io/badge/Windows%20%7C%20macOS-supported-20242C?style=for-the-badge" alt="Windows and macOS">
</p>

<p align="center"><a href="README.md">简体中文</a> · English</p>

<p align="center">Download Bilibili audio, video, multi-part videos, and collections from the CLI or local Web UI.</p>

## Features

- Accepts a Bilibili URL through `-i/--input`.
- Without `-e/--episodes`, downloads only the video pointed to by the input URL.
- If the input URL contains `?p=2`, downloads only part 2 by default.
- With `-e/--episodes`, normalizes the Bilibili URL first, then downloads the selected parts.
- Supports episode selections such as `1-5`, `1,2,6`, and `all`.
- Detects video collections and expands their BVs and nested BV parts into one ordered download list.
- Supports a custom output directory through `-o/--output`; defaults to the system Downloads directory.
- Without `-m/--media`, infers `audio` or `video` from the input URL.
- Supports explicitly selecting `audio` or `video` through `-m/--media`.
- Bilibili audio URLs such as `/audio/au...` and audio albums such as `/audio/am...` always use audio mode. If `--media video` is passed, the script prints a warning and ignores it.
- Continues with later parts if one part fails.
- Prints script-level progress for video parts and audio albums, such as `Downloading playlist item 5 of 13`.
- Prints a final summary with succeeded count, failed count, and failed episode list.

## Requirements

Make sure these tools are installed:

- Python 3
- FFmpeg, with `ffmpeg` available from your command line

Install the Python dependency:

```powershell
python -m pip install -U yt-dlp
```

The script uses `yt-dlp` to download media and relies on FFmpeg to handle audio and video files. Make sure FFmpeg is installed and that `ffmpeg` can be run directly from your command line.

## Web UI Usage

The web UI is recommended for users who do not want to type commands.

Windows:

```text
Double-click start_web.bat
```

macOS:

```text
Double-click start_web.command
```

The browser opens automatically, usually at:

```text
http://127.0.0.1:8765
```

If port 8765 is already in use, the script tries later ports automatically. The actual URL is printed in the launcher window.

The web UI lets you fill in:

- Bilibili URL
- Media type: auto, audio, or video
- Parts / tracks: empty, `1,2,5`, `1-5`, or `all`
- Output directory: empty means the system Downloads directory

After a download starts, the web UI shows each item in a download list with its progress percentage and status. If one item fails, click its Retry button to download only that item again. The raw log stays visible on the right side for detailed yt-dlp output.

If macOS says `start_web.command` is not executable, run this once in the project directory:

```bash
chmod +x start_web.command
```

Then double-click `start_web.command` again.

## Command Line Usage

```powershell
python .\scripts\bilibili_downloader.py -i "Bilibili URL"
```

When `-m` is omitted, the script infers the media type from the URL. Regular Bilibili video URLs use video mode; Bilibili audio URLs use audio mode.

Bilibili audio URLs are always downloaded as audio:

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/audio/au4059094"
```

Bilibili audio albums are downloaded in full when `-e` is omitted:

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/audio/am10627"
```

Set a custom output directory:

```powershell
python .\scripts\bilibili_downloader.py -i "Bilibili URL" -o "C:\Users\YourName\Downloads\bilibili"
```

Show help:

```powershell
python .\scripts\bilibili_downloader.py -h
```

Download video:

```powershell
python .\scripts\bilibili_downloader.py -i "Bilibili video URL" -m video
```

## Options

- `-i`, `--input`: Bilibili URL. Required.
- `-e`, `--episodes`: Parts to download, such as `"1-5"`, `"1,2,6"`, or `all`.
- `-o`, `--output`: Output directory. Defaults to the system Downloads directory.
- `-m`, `--media`: Media type. Use `audio` or `video`. When omitted, the type is inferred from the input URL. Bilibili audio URLs always use `audio`.
- `-h`, `--help`: Show help.

## Bilibili Video Structure

The script treats Bilibili video pages as one of these structures:

- **Single video**: one BV contains exactly one part.
- **Multi-part video**: one BV contains multiple parts, such as part 1, part 2, and part 3.
- **Video collection**: one collection directory contains multiple BVs. A BV inside the collection may also contain multiple parts.

Detection rules:

- If the page contains `sectionsInfo`, the script treats it as a video collection.
- If there is no `sectionsInfo` and `videoData.pages` contains more than one item, the script treats it as a multi-part video.
- If there is no `sectionsInfo` and `videoData.pages` contains one item, the script treats it as a single video.

For video collections, when `-e` is provided, the script expands the collection into one ordered list before applying the selection. For example, if items 1-50 are in `BV1324y1o7E7` and items 51-100 are in `BV1hX4y1k7WH`, then `-e 60` means collection item 60, which maps to part 10 of the second BV.

When `-e` is omitted, the script still downloads only the video or part pointed to by the input URL.

## Episode And Collection Selection

If `-e` is not provided, regular video URLs download only the video pointed to by `-i`.

For example, this URL points to part 2:

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=2&vd_source=xxx"
```

In this case, the script downloads only part 2.

If `-e` is provided, the script first normalizes the Bilibili URL to the base BV URL, then downloads the selected parts:

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=2&vd_source=xxx" -e "1,2"
```

This downloads parts 1 and 2.

Download a continuous range:

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/" -e "1-5"
```

Download all parts:

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/" -e all
```

Download selected ordered items from a video collection:

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1AiarzQEJ1" -e "60,101-103"
```

Download the full video collection:

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1AiarzQEJ1" -e all
```

## Audio Album Selection

A Bilibili single-audio URL looks like this:

```text
https://www.bilibili.com/audio/au4059094
```

A Bilibili audio album URL looks like this:

```text
https://www.bilibili.com/audio/am10627
```

When `-e` is omitted for an audio album, the script downloads the full album. When `-e` is provided, it downloads the selected tracks by their album order:

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/audio/am10627" -e "1,3-5"
```

Audio albums are downloaded track by track, so the script can record success or failure for each selected track. If one track fails, later tracks are still downloaded. The script prints progress such as `Downloading playlist item 5 of 13`.

Single-audio URLs do not need `-e`. If `-e` is passed for an `au...` URL, the script prints a warning and ignores `-e`.

Audio URLs always use audio mode. If `--media video` is passed for an audio URL, the script prints a warning and continues in audio mode.

## Failure Summary

The script downloads each selected part one by one. If one part fails, the failure is recorded and the script continues with the remaining parts.

After all downloads finish, it prints a summary:

```text
Download summary: succeeded 2, failed 1
Failed episodes: 41
```

If all selected parts succeed, it only prints the success and failure counts:

```text
Download summary: succeeded 3, failed 0
```

If any selected part fails, the script exits with code `1`. If all selected parts succeed, it exits with code `0`.

## PowerShell Quoting Notes

In PowerShell, it is recommended to wrap URLs in double quotes, especially when the URL contains characters such as `?` or `&`:

```powershell
-i "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=2&vd_source=xxx"
```

If the value after `-e` contains commas or hyphens, wrapping it in double quotes is also recommended:

```powershell
-e "1,2,6"
-e "1-5"
```

`all` also works without quotes:

```powershell
-e all
```

## Roadmap

- Add more output format options if needed.
