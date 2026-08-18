"""通用工具：文件名净化、大小/时长格式化、音频格式判断、封面缩略图加载。"""
from __future__ import annotations

import os
import re

# 常见音频后缀（本地导入与视频内音轨提取均使用）
AUDIO_EXTS = {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus", ".wma", ".ape", ".alac"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".flv", ".ts", ".m4v"}


def sanitize_filename(name: str, max_len: int = 90) -> str:
    """去除 Windows 非法字符并压缩空白，避免出现无法保存的文件名。"""
    if not name:
        return "未命名"
    # 去除非法字符
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', " ", name)
    # 压缩空白
    name = re.sub(r"\s+", " ", name).strip()
    # 去除首尾点/空格
    name = name.strip(". ")
    # 截断（预留扩展名空间）
    if len(name) > max_len:
        name = name[:max_len].rstrip(". ")
    if not name:
        name = "未命名"
    return name


def fmt_size(n: int) -> str:
    if n is None or n <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024 or u == "TB":
            return f"{f:.1f} {u}" if u != "B" else f"{int(f)} {u}"
        f /= 1024
    return f"{f:.1f} TB"


def fmt_duration(seconds) -> str:
    try:
        seconds = int(round(float(seconds)))
    except (TypeError, ValueError):
        return "--:--"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def is_audio_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in AUDIO_EXTS


def is_video_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTS


def load_thumbnail(path: str, size: tuple = (64, 64)):
    """为任务卡片加载封面缩略图（失败返回 None）。"""
    try:
        from PIL import Image, ImageTk
        if not path or not os.path.exists(path):
            return None
        img = Image.open(path).convert("RGB")
        img.thumbnail(size, Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None
