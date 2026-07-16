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

<p align="center">简体中文 · <a href="README.en.md">English</a></p>

<p align="center">下载 B 站音频、视频、多 P 与合集，支持命令行和本地 Web UI。</p>

## 功能

- 支持通过 `-i/--input` 输入 B 站链接。
- 不传 `-e/--episodes` 时，只下载输入链接本身指向的视频。
- 如果输入链接带 `?p=2`，默认只下载第 2P。
- 传 `-e/--episodes` 时，会先规范化 B 站链接，再按指定分 P 下载。
- `-e/--episodes` 支持 `1-5`、`1,2,6`、`all`。
- 支持识别视频合集，并把合集里的多个 BV 和 BV 内分 P 展开成统一序号下载。
- 支持通过 `-o/--output` 指定下载目录，默认保存到系统 Downloads 目录。
- 不传 `-m/--media` 时，会根据输入链接自动选择 `audio` 或 `video`。
- 支持通过 `-m/--media` 显式指定 `audio` 或 `video`。
- B 站音频链接 `/audio/au...` 和音频合集 `/audio/am...` 会强制使用 `audio` 模式；如果传了 `--media video`，会打印 warning 并忽略。
- 下载多个分 P 时，单个分 P 失败后会继续下载后续分 P。
- 下载视频分 P 或音频合集时，会打印脚本层进度，例如 `Downloading playlist item 5 of 13`。
- 执行结束后会输出成功数量、失败数量和失败分 P 列表。

## 依赖

请先确保本机已经安装：

- Python 3
- FFmpeg，并且 `ffmpeg` 可以在命令行里直接运行

安装 Python 依赖：

```powershell
python -m pip install -U yt-dlp
```

脚本会通过 `yt-dlp` 下载媒体内容，并依赖 FFmpeg 处理音频和视频文件。请确保本机已经安装 FFmpeg，并且 `ffmpeg` 可以在命令行里直接运行。

## 网页 UI 用法

推荐不熟悉命令行的用户使用网页 UI。

Windows：

```text
双击 start_web.bat
```

macOS：

```text
双击 start_web.command
```

启动后会自动打开浏览器，通常地址是：

```text
http://127.0.0.1:8765
```

如果 8765 端口被占用，脚本会自动尝试后续端口，实际地址会显示在启动窗口里。

网页里可以填写：

- B 站链接
- 媒体类型：自动、音频、视频
- 分 P / 曲目：留空、`1,2,5`、`1-5` 或 `all`
- 输出目录：留空时保存到系统 Downloads

下载开始后，网页会在下载列表里逐条显示内容、进度百分比和状态。某一项下载失败时，可以点击该项右侧的“重新下载”按钮，只重试这一项。原始日志仍会显示在页面右侧，方便查看 yt-dlp 的详细输出。

如果 macOS 提示 `start_web.command` 没有执行权限，请在项目目录运行一次：

```bash
chmod +x start_web.command
```

然后再双击 `start_web.command`。

## 命令行用法

```powershell
python .\scripts\bilibili_downloader.py -i "B站链接"
```

不传 `-m` 时，脚本会根据链接类型自动选择下载音频或视频。普通 B 站视频链接默认按视频下载；B 站音频链接默认按音频下载。

B 站音频链接始终按音频下载：

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/audio/au4059094"
```

B 站音频合集不传 `-e` 时会下载全集：

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/audio/am10627"
```

指定输出目录：

```powershell
python .\scripts\bilibili_downloader.py -i "B站链接" -o "C:\Users\YourName\Downloads\bilibili"
```

查看帮助：

```powershell
python .\scripts\bilibili_downloader.py -h
```

下载视频：

```powershell
python .\scripts\bilibili_downloader.py -i "B站视频链接" -m video
```

## 参数说明

- `-i`, `--input`：B 站链接，必填。
- `-e`, `--episodes`：指定分 P，例如 `"1-5"`、`"1,2,6"` 或 `all`。
- `-o`, `--output`：下载目录，不传时默认保存到系统 Downloads 目录。
- `-m`, `--media`：媒体类型，可选 `audio` 或 `video`。不传时会根据输入链接自动判断；如果输入是 B 站音频链接，会强制使用 `audio`。
- `-h`, `--help`：显示帮助。

## B 站视频结构说明

这个脚本按下面的结构理解 B 站视频：

- **单个视频**：一个 BV 里只有 1 个 P。比如打开后没有分 P 列表，也没有合集目录。
- **多 P 视频**：一个 BV 里有多个 P。比如同一个 BV 下有第 1P、第 2P、第 3P。
- **视频合集**：一个合集目录里包含多个 BV。合集里的某个 BV 也可能自己带多个 P。

脚本判断规则：

- 页面里有 `sectionsInfo` 时，按视频合集处理。
- 没有 `sectionsInfo`，但 `videoData.pages` 超过 1 个时，按多 P 视频处理。
- 没有 `sectionsInfo`，并且 `videoData.pages` 只有 1 个时，按单个视频处理。

对于视频合集，传 `-e` 时脚本会先把合集展开成一个统一列表，再按统一序号下载。比如合集前 50 首在 `BV1324y1o7E7`，第 51 到 100 首在 `BV1hX4y1k7WH`，那么 `-e 60` 表示下载整个合集的第 60 项，也就是第二个 BV 里的第 10P。

如果不传 `-e`，仍然只下载输入链接本身指向的视频或分 P。

## 分 P / 合集下载规则

如果不传 `-e`，普通视频链接只下载 `-i` 链接本身对应的视频。

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

下载视频合集里的指定统一序号：

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1AiarzQEJ1" -e "60,101-103"
```

下载视频合集全集：

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/video/BV1AiarzQEJ1" -e all
```

## 音频合集规则

B 站音频单曲链接形如：

```text
https://www.bilibili.com/audio/au4059094
```

B 站音频合集链接形如：

```text
https://www.bilibili.com/audio/am10627
```

音频合集不传 `-e` 时会下载全集。传 `-e` 时会按合集内曲目序号下载指定曲目：

```powershell
python .\scripts\bilibili_downloader.py -i "https://www.bilibili.com/audio/am10627" -e "1,3-5"
```

音频合集会逐首下载并记录每首的成功或失败；某一首失败时，会继续下载后续曲目。下载时会显示脚本层进度，例如 `Downloading playlist item 5 of 13`。

音频单曲不需要 `-e`。如果对 `au...` 单曲传了 `-e`，脚本会打印 warning 并忽略 `-e`。

音频链接会强制使用 `audio` 模式。如果对音频链接传了 `--media video`，脚本会打印 warning 并继续按音频下载。

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

- 根据需要补充更多输出格式选项。
