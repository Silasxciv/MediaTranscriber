"""下载层：基于 yt-dlp 封装小宇宙音频与 B站视频下载，保留元数据与封面。"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import requests

from app import utils
from app import xiaoyuzhou

XY_HOSTS = ("xiaoyuzhoufm.com", "xyzcdn.net")
BILI_HOSTS = ("bilibili.com", "b23.tv", "bilibili.tv", "player.bilibili.com")


def _fmt_pub_date(raw) -> str:
    """把小宇宙 pubDate 规范化成 YYYY-MM-DD（尽力而为）。"""
    if not raw:
        return ""
    s = str(raw)
    # ISO 字符串：2024-08-01T12:00:00 → 取前 10 位
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    # 纯数字：可能是毫秒/秒级时间戳
    if s.isdigit():
        try:
            v = int(s)
            if v > 1e12:
                v /= 1000
            import datetime
            return datetime.datetime.utcfromtimestamp(v).strftime("%Y-%m-%d")
        except Exception:
            return ""
    return ""


class CancelRequested(Exception):
    """在进度钩子中抛出以中止下载。"""


def detect_source(url: str) -> str | None:
    try:
        host = urlparse(url.strip()).netloc.lower()
    except Exception:
        return None
    if any(h in host for h in XY_HOSTS):
        return "xiaoyuzhou"
    if any(h in host for h in BILI_HOSTS):
        return "bilibili"
    return None


def parse_links(text: str) -> list[str]:
    """从多行/空格分隔文本中提取有效链接。"""
    if not text:
        return []
    found = re.findall(r"https?://[^\s,，。；;]+", text)
    seen, out = set(), []
    for u in found:
        u = u.rstrip(").,;。，；\"'")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


class Downloader:
    def __init__(self, ffmpeg_path: str, on_log=None):
        self.ffmpeg = ffmpeg_path
        self.on_log = on_log or (lambda level, msg: None)

    # ------------------------------------------------------------------ info
    def fetch_info(self, url: str) -> dict:
        """轻量获取元数据（不下载媒体）。"""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ffmpeg_location": self.ffmpeg,
        }
        import yt_dlp
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
        return self._normalize_info(info)

    def _normalize_info(self, info: dict) -> dict:
        title = info.get("title") or info.get("fulltitle") or "未命名"
        upload = info.get("upload_date") or info.get("release_date") or ""
        if upload and len(upload) == 8:
            date = f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}"
        else:
            date = info.get("upload_date_str") or ""
        return {
            "title": title,
            "upload_date": date,
            "thumbnail": info.get("thumbnail") or info.get("cover") or "",
            "duration": info.get("duration") or 0,
            "description": (info.get("description") or "")[:2000],
            "webpage_url": info.get("webpage_url") or info.get("url") or "",
            "channel": info.get("uploader") or info.get("artist") or "",
        }

    # ---------------------------------------------------------------- download
    def download(
        self,
        url: str,
        kind: str,
        out_dir: str,
        cancel_event,
        progress,
    ) -> dict:
        """下载单个链接。

        progress(percent:float|None, phase:str, message:str)
        返回 {ok, cancelled, file, cover, metadata, error}
        """
        os.makedirs(out_dir, exist_ok=True)

        # 小宇宙：yt-dlp 不支持，走页面解析 + 音频直链下载
        if kind == "xiaoyuzhou":
            return self.download_xiaoyuzhou(url, out_dir, cancel_event, progress)

        # 先取元数据以决定文件名
        try:
            meta = self.fetch_info(url)
        except Exception as e:  # 某些站点需下载才能拿信息
            meta = {"title": "未命名", "upload_date": "", "thumbnail": "",
                    "duration": 0, "description": "", "webpage_url": url, "channel": ""}
            meta["_info_error"] = str(e)

        safe = utils.sanitize_filename(meta["title"])

        # 下载封面
        cover = ""
        if meta.get("thumbnail"):
            cover = self._download_cover(meta["thumbnail"], out_dir, safe)

        fmt, postp, ext = self._build_format(kind)

        outtmpl = os.path.join(out_dir, f"{safe}.%(ext)s")
        state = {"cancelled": False, "last_file": None, "bucket": -1}

        def hook(d):
            if cancel_event.is_set():
                state["cancelled"] = True
                raise CancelRequested()
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes") or 0
                pct = (done / total * 100) if total else None
                progress(pct, "downloading",
                         f"下载中 {utils.fmt_size(done)}" + (f" / {utils.fmt_size(total)}" if total else ""))
                if pct is not None:
                    bucket = int(pct) // 20
                    if bucket != state["bucket"] and bucket > 0:
                        state["bucket"] = bucket
                        self.on_log("task", f"下载进度 {int(pct)}%  {utils.fmt_size(done)}"
                                    + (f" / {utils.fmt_size(total)}" if total else ""))
            elif d.get("status") == "finished":
                state["last_file"] = d.get("info_dict", {}).get("filepath") or d.get("filename")
                if cancel_event.is_set():
                    state["cancelled"] = True
                    raise CancelRequested()

        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "ffmpeg_location": self.ffmpeg,
            "outtmpl": outtmpl,
            "format": fmt,
            "merge_output_format": "mp4" if kind == "bilibili" else None,
            "postprocessors": postp,
            "progress_hooks": [hook],
            "retries": 3,
            "fragment_retries": 3,
            "http_chunk_size": 10 * 1024 * 1024,
        }
        if kind == "bilibili":
            opts["writesubtitles"] = False

        import yt_dlp
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except CancelRequested:
            return {"ok": False, "cancelled": True, "file": None, "cover": cover, "metadata": meta, "error": "已取消"}
        except Exception as e:
            return {"ok": False, "cancelled": False, "file": None, "cover": cover, "metadata": meta, "error": str(e)}

        final = state["last_file"] or os.path.join(out_dir, f"{safe}.{ext}")
        if not os.path.exists(final):
            # 兜底：取目录中最新文件
            final = self._newest_in_dir(out_dir, ext)
        return {"ok": True, "cancelled": False, "file": final, "cover": cover, "metadata": meta, "error": ""}

    # --------------------------------------------------- 小宇宙：直链下载
    def download_xiaoyuzhou(self, url: str, out_dir: str, cancel_event, progress) -> dict:
        """解析小宇宙页面，直接下载 .m4a 音频（不走 yt-dlp）。

        支持单集页（/episode/<eid>）与节目页（/podcast/<pid>）。
        节目页在入队时已被展开为每集一个任务，此处通常只处理单集；
        若直接传入节目页，则只下载其首集并给出提示。
        """
        info = xiaoyuzhou.parse(url)
        episodes = info.get("episodes") or []
        if not episodes:
            raise RuntimeError("该小宇宙页面未包含可下载的音频")
        ep = episodes[0]
        if len(episodes) > 1:
            self.on_log("warn", f"小宇宙节目页含 {len(episodes)} 集，此处仅下载第一集「{ep['title']}」"
                                  f"（建议在输入框粘贴单集链接以逐集下载）")

        meta = {
            "title": ep["title"] or "未命名",
            "upload_date": _fmt_pub_date(ep.get("pub_date")),
            "thumbnail": ep.get("cover") or "",
            "duration": ep.get("duration") or 0,
            "description": (ep.get("description") or "")[:2000],
            "webpage_url": url,
            "channel": info.get("podcast_title") or "",
        }
        safe = utils.sanitize_filename(meta["title"])
        cover = ""
        if meta.get("thumbnail"):
            cover = self._download_cover(meta["thumbnail"], out_dir, safe)

        audio_url = ep.get("audio_url")
        if not audio_url:
            raise RuntimeError("该集无音频直链（可能为付费或私有内容）")

        final = os.path.join(out_dir, f"{safe}.m4a")
        self._download_file(audio_url, final, cancel_event, progress)
        return {"ok": True, "cancelled": False, "file": final, "cover": cover, "metadata": meta, "error": ""}

    def _download_file(self, url: str, dest: str, cancel_event, progress):
        """用 requests 流式下载（支持进度与取消），写入 dest。"""
        # 已存在则跳过，避免重复下载
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            progress(100, "downloading", "已存在，跳过")
            return
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.xiaoyuzhoufm.com/",
        }, stream=True, timeout=30)
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        last_bucket = -1
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 256):
                if cancel_event.is_set():
                    raise CancelRequested()
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done / total * 100
                    progress(pct, "downloading",
                             f"下载中 {utils.fmt_size(done)} / {utils.fmt_size(total)}")
                    bucket = int(pct) // 20
                    if bucket != last_bucket and bucket > 0:
                        last_bucket = bucket
                        self.on_log("task", f"下载进度 {int(pct)}%  {utils.fmt_size(done)} / {utils.fmt_size(total)}")
                else:
                    progress(None, "downloading", f"下载中 {utils.fmt_size(done)}")
        if cancel_event.is_set():
            raise CancelRequested()

    # ----------------------------------------------------------------- helpers
    def _build_format(self, kind: str):
        if kind == "xiaoyuzhou":
            return (
                "bestaudio/best",
                [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a", "preferredquality": "0"},
                 {"key": "FFmpegMetadata"}],
                "m4a",
            )
        # bilibili 最高清晰度：视频+音频合并为 mp4
        return (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
            [{"key": "FFmpegMetadata"}],
            "mp4",
        )

    def _download_cover(self, thumb_url: str, out_dir: str, safe: str) -> str:
        try:
            ext = os.path.splitext(urlparse(thumb_url).path)[1] or ".jpg"
            if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                ext = ".jpg"
            path = os.path.join(out_dir, f"{safe}{ext}")
            r = requests.get(thumb_url, timeout=30)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
            return path
        except Exception:
            return ""

    def _newest_in_dir(self, out_dir: str, ext: str) -> str:
        files = [os.path.join(out_dir, f) for f in os.listdir(out_dir)
                 if f.lower().endswith(f".{ext}")]
        if not files:
            return ""
        return max(files, key=os.path.getmtime)
