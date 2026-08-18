"""配置管理：设置持久化、路径解析、ffmpeg 定位。"""
from __future__ import annotations

import json
import os
import shutil
import sys

from app import APP_NAME


# ----------------------------------------------------------------------------
# 路径工具
# ----------------------------------------------------------------------------
def app_data_dir() -> str:
    """跨平台的应用数据目录（用于存放设置与 ffmpeg 缓存）。"""
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def resource_path(rel: str) -> str:
    """定位打包后的资源文件：优先 _MEIPASS，其次脚本所在目录。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    # 开发态：项目根目录（main.py 的上一级）
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, rel)


FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def _download_ffmpeg(target_dir: str, on_progress=None) -> str:
    """首次使用时自动下载并解压 Windows 静态 ffmpeg 到 target_dir。"""
    import io
    import zipfile

    import requests

    os.makedirs(target_dir, exist_ok=True)
    if on_progress:
        on_progress(0, "正在下载 ffmpeg（首次使用，约 100MB）…")
    r = requests.get(FFMPEG_URL, stream=True, timeout=600)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    buf = bytearray()
    got = 0
    for chunk in r.iter_content(1024 * 1024):
        buf += chunk
        got += len(chunk)
        if on_progress and total:
            on_progress(got * 100 // total, f"下载 ffmpeg {got*100//total}%")
    with zipfile.ZipFile(io.BytesIO(bytes(buf))) as z:
        for name in z.namelist():
            if os.path.basename(name) in ("ffmpeg.exe", "ffprobe.exe"):
                p = os.path.join(target_dir, os.path.basename(name))
                with open(p, "wb") as f:
                    f.write(z.read(name))
    return os.path.join(target_dir, "ffmpeg.exe")


def ensure_ffmpeg(on_progress=None) -> str:
    """返回可用的 ffmpeg 可执行文件路径；缺失时自动下载（首次使用）。

    查找顺序：内置 bin/ffmpeg.exe -> 系统 PATH -> 应用数据目录 bin/ffmpeg.exe
    -> 自动下载到应用数据目录。全部失败才抛出可读错误。
    """
    # 1) 内置（打包后一定存在；开发态若有 bin/ 也存在）
    bundled = resource_path(os.path.join("bin", "ffmpeg.exe"))
    if os.path.exists(bundled):
        return bundled

    # 2) 系统 PATH
    in_path = shutil.which("ffmpeg")
    if in_path:
        return in_path

    # 3) 应用数据目录
    app_bin = os.path.join(app_data_dir(), "bin")
    app_ff = os.path.join(app_bin, "ffmpeg.exe")
    if os.path.exists(app_ff):
        return app_ff

    # 4) 自动下载
    try:
        return _download_ffmpeg(app_bin, on_progress)
    except Exception as e:
        raise FileNotFoundError(
            "未找到 ffmpeg 且自动下载失败：" + str(e) +
            "。请手动运行项目根目录的 get_ffmpeg.py，或将 ffmpeg 加入系统 PATH。"
        )


# ----------------------------------------------------------------------------
# 设置
# ----------------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "output_dir": os.path.join(os.path.expanduser("~"), "Downloads", "媒体转写"),
    "asr_engine": "local",          # local | openai
    "whisper_model": "medium",      # small | medium | large-v3 | large-v3-turbo
    "device": "auto",               # auto | cpu | cuda
    "openai_api_key": "",
    "openai_model": "whisper-1",    # whisper-1 | gpt-4o-transcribe | gpt-4o-mini-transcribe
    "concurrent_tasks": 2,
    "theme": "light",               # light | dark
    "paragraph_mode": "semantic",   # semantic | pause（语义分段 / 按停顿分段）
}


class Settings:
    _PATH = os.path.join(app_data_dir(), "settings.json")

    def __init__(self):
        self._data = dict(DEFAULT_SETTINGS)
        self.load()

    def load(self):
        try:
            with open(self._PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self._data.update({k: v for k, v in saved.items() if k in DEFAULT_SETTINGS})
        except FileNotFoundError:
            pass
        # 输出目录不存在则创建
        try:
            os.makedirs(self._data["output_dir"], exist_ok=True)
        except Exception:
            pass

    def save(self):
        path = self._PATH
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        payload = json.dumps(self._data, ensure_ascii=False, indent=2)
        # 原子写入：先写临时文件再替换，避免写到一半崩溃导致文件损坏/为空
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)
        # 写后回读校验，确保确实落盘成功（而不是写了个空文件/半文件）
        try:
            with open(path, "r", encoding="utf-8") as f:
                reloaded = json.load(f)
            for k, v in self._data.items():
                if reloaded.get(k) != v:
                    raise IOError(
                        f"字段校验不一致：{k!r}（期望 {v!r}，实际 {reloaded.get(k)!r}）"
                    )
        except Exception as e:
            raise IOError(f"设置写入后校验失败：{e}")

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        if key in self._data:
            self._data[key] = value
            self.save()

    def as_dict(self):
        return dict(self._data)

    def update(self, d: dict):
        for k, v in d.items():
            if k in self._data:
                self._data[k] = v
        self.save()

    # 便捷属性
    @property
    def output_dir(self):
        return self._data["output_dir"]

    @property
    def asr_engine(self):
        return self._data["asr_engine"]

    @property
    def whisper_model(self):
        return self._data["whisper_model"]

    @property
    def device(self):
        return self._data["device"]

    @property
    def openai_api_key(self):
        return self._data["openai_api_key"]

    @property
    def openai_model(self):
        return self._data["openai_model"]

    @property
    def concurrent_tasks(self):
        return int(self._data.get("concurrent_tasks", 2))

    @property
    def theme(self):
        return self._data.get("theme", "light")

    @property
    def paragraph_mode(self):
        return self._data.get("paragraph_mode", "semantic")
