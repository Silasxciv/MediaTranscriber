# MediaTranscriber

一站式「下载 + 转文字」工具：支持小宇宙、B 站音频下载与本地音频，
用 faster-whisper 高精度转写成中文文稿。微信风格界面，批量队列、实时进度、运行日志一应俱全。

## ✨ 功能
- 🎙️ 小宇宙节目 / 单集直链下载（自动展开每集为独立任务）
- 📺 B 站音视频下载
- 💻 本地音频文件直接转写
- 📋 批量任务队列，实时进度 + 运行日志
- 🏷️ 按节目 / 单集标题自动命名输出文件
- 🖥️ 微信风简洁 UI，开箱即用（单文件 exe，无需安装 Python）

## ⬇️ 下载
到 Releases 页面下载 MediaTranscriber.exe，双击即可运行（仅 Windows）：
https://github.com/silasxciv/MediaTranscriber/releases

## 🚀 快速开始
1. 下载并双击 MediaTranscriber.exe
2. 粘贴小宇宙 / B 站链接，或选择本地音频
3. 点「开始」，等待转写完成，文稿按标题命名保存

## 🛠 从源码构建（开发者）
python -m venv .buildenv
.buildenv\Scripts\activate
pip install -r requirements.txt
python get_ffmpeg.py
python build.spec
（产物在 dist/MediaTranscriber.exe）

## 📦 技术栈
Python · customtkinter（微信风界面）· yt-dlp · faster-whisper · PyInstaller
（以上仅是说明文字，你无需安装或操作任何东西）

## 📄 License
MIT —— 见仓库根目录的 LICENSE 文件
