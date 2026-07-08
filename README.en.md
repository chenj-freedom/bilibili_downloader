# Bilibili Downloader

[简体中文](README.md) | English

A simple Bilibili audio downloader script. It currently downloads audio and converts it to mp3. The video download option is reserved for future work and is not implemented yet.

## Features

- Accepts a Bilibili video URL through `-i/--input`.
- Without `-e/--episodes`, downloads only the video pointed to by the input URL.
- If the input URL contains `?p=2`, downloads only part 2 by default.
- With `-e/--episodes`, normalizes the Bilibili URL first, then downloads the selected parts.
- Supports episode selections such as `1-5`, `1,2,6`, and `all`.
- Supports a custom output directory through `-o/--output`; defaults to the system Downloads directory.
- Continues with later parts if one part fails.
- Prints a final summary with succeeded count, failed count, and failed episode list.

## Requirements

Install the Python dependency:

```powershell
python -m pip install -U yt-dlp
```

The script uses `yt-dlp` to download audio and uses FFmpeg as a post-processor to convert it to mp3. Make sure FFmpeg is installed and that `ffmpeg` can be run directly from your command line.

## Usage

```powershell
python .\scripts\bilibili_downloader.py -i "Bilibili video URL"
```

Set a custom output directory:

```powershell
python .\scripts\bilibili_downloader.py -i "Bilibili video URL" -o "C:\Users\YourName\Downloads\bilibili"
```

Show help:

```powershell
python .\scripts\bilibili_downloader.py -h
```

## Options

- `-i`, `--input`: Bilibili video URL. Required.
- `-e`, `--episodes`: Parts to download, such as `"1-5"`, `"1,2,6"`, or `all`.
- `-o`, `--output`: Output directory. Defaults to the system Downloads directory.
- `-m`, `--media`: Media type. Currently `audio` works; `video` is a TODO placeholder.
- `-h`, `--help`: Show help.

## Episode Selection

If `-e` is not provided, the script downloads only the video pointed to by `-i`.

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

- Implement video download support for `-m video`.
- Add more output format options if needed.
