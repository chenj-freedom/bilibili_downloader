# Bilibili Downloader

简体中文 | [English](README.en.md)

一个简单的 B 站音频下载脚本。当前支持下载音频并转换为 mp3；视频下载参数已预留，但尚未实现。

## 功能

- 支持通过 `-i/--input` 输入 B 站视频链接。
- 不传 `-e/--episodes` 时，只下载输入链接本身指向的视频。
- 如果输入链接带 `?p=2`，默认只下载第 2P。
- 传 `-e/--episodes` 时，会先规范化 B 站链接，再按指定分 P 下载。
- `-e/--episodes` 支持 `1-5`、`1,2,6`、`all`。
- 支持通过 `-o/--output` 指定下载目录，默认保存到系统 Downloads 目录。
- 下载多个分 P 时，单个分 P 失败后会继续下载后续分 P。
- 执行结束后会输出成功数量、失败数量和失败分 P 列表。

## 依赖

安装 Python 依赖：

```powershell
python -m pip install -U yt-dlp
```

脚本会通过 `yt-dlp` 下载音频，并使用 FFmpeg 后处理转换为 mp3。请确保本机已经安装 FFmpeg，并且 `ffmpeg` 可以在命令行里直接运行。

## 基本用法

```powershell
python .\scripts\bilibili_downloader.py -i "B站视频链接"
```

指定输出目录：

```powershell
python .\scripts\bilibili_downloader.py -i "B站视频链接" -o "C:\Users\YourName\Downloads\bilibili"
```

查看帮助：

```powershell
python .\scripts\bilibili_downloader.py -h
```

## 参数说明

- `-i`, `--input`：B 站视频链接，必填。
- `-e`, `--episodes`：指定分 P，例如 `"1-5"`、`"1,2,6"` 或 `all`。
- `-o`, `--output`：下载目录，不传时默认保存到系统 Downloads 目录。
- `-m`, `--media`：媒体类型，目前 `audio` 可用，`video` 是 TODO 占位。
- `-h`, `--help`：显示帮助。

## 分 P 下载规则

如果不传 `-e`，脚本只下载 `-i` 链接本身对应的视频。

例如这个链接打开的是第 2P：

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=2&vd_source=xxx"
```

这时脚本只下载这个链接指向的第 2P。

如果传了 `-e`，脚本会先把 B 站链接规范化为基础 BV 链接，再按 `-e` 指定的分 P 下载：

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=2&vd_source=xxx" -e "1,2"
```

这时会下载第 1P 和第 2P。

下载连续分 P：

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/" -e "1-5"
```

下载全部分 P：

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/" -e all
```

## 下载失败统计

脚本会逐个分 P 下载。某一集下载失败时，脚本会记录失败并继续下载后面的分 P。

全部执行完成后，会输出统计信息：

```text
Download summary: succeeded 2, failed 1
Failed episodes: 41
```

如果所有分 P 都下载成功，只会显示成功和失败数量：

```text
Download summary: succeeded 3, failed 0
```

如果存在失败分 P，脚本退出码为 `1`；如果全部成功，退出码为 `0`。

## PowerShell 引号建议

在 PowerShell 里，建议给 URL 加双引号，尤其是 URL 里包含 `?`、`&` 这类字符时：

```powershell
-i "https://www.bilibili.com/video/BV1Ag4y1Z7Ga/?p=2&vd_source=xxx"
```

`-e` 后面的内容如果包含逗号或横杠，也建议加双引号：

```powershell
-e "1,2,6"
-e "1-5"
```

`all` 不加引号也可以：

```powershell
-e all
```

## 后续计划

- 实现 `-m video` 视频下载。
- 根据需要补充更多输出格式选项。
