"""下载并解压 Windows 静态 ffmpeg（含 ffprobe）到项目 bin/ 目录。

用于：1) 开发运行时提供 ffmpeg；2) 打包前让 PyInstaller 把 bin/ 内置进 exe。
来源：gyan.dev 官方发布（Essentials 版，约 50MB）。
"""
from __future__ import annotations

import io
import os
import zipfile

import requests

URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "bin")


def main():
    os.makedirs(BIN, exist_ok=True)
    print(f"下载 ffmpeg: {URL}")
    r = requests.get(URL, timeout=120)
    r.raise_for_status()
    print("下载完成，解压中…")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for name in z.namelist():
            base = os.path.basename(name)
            if base in ("ffmpeg.exe", "ffprobe.exe"):
                target = os.path.join(BIN, base)
                with open(target, "wb") as f:
                    f.write(z.read(name))
                print(f"  -> {target}")
    print("完成。bin/ 下已包含 ffmpeg.exe 与 ffprobe.exe。")


if __name__ == "__main__":
    main()
