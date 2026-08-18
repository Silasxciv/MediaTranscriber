"""小宇宙（xiaoyuzhoufm.com）解析：从页面 __NEXT_DATA__ 提取节目/单集信息与音频直链。

小宇宙网页为 Next.js 渲染，结构化数据放在 <script id="__NEXT_DATA__"> 里：
  - 节目页 /podcast/<pid>  → props.pageProps.podcast.episodes[]（页面展示的近期单集）
  - 单集页 /episode/<eid>  → props.pageProps.episode
每个单集对象含 enclosure.url（.m4a 直链）、title、image.picUrl、duration、shownotes 等。
"""
from __future__ import annotations

import json
import re

import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://www.xiaoyuzhoufm.com/",
}

_EPISODE_PATH = re.compile(r"/episode/([a-f0-9]+)")
_PODCAST_PATH = re.compile(r"/podcast/([a-f0-9]+)")
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _fetch_json(url: str, timeout: int = 25) -> dict:
    r = requests.get(url, headers=_HEADERS, timeout=timeout)
    r.raise_for_status()
    m = _NEXT_DATA.search(r.text)
    if not m:
        raise RuntimeError("无法解析小宇宙页面（未找到结构化数据）")
    return json.loads(m.group(1))


def _episode_dict(ep: dict) -> dict:
    enc = ep.get("enclosure") or {}
    img = (ep.get("image") or {}).get("picUrl") or ep.get("coverImage") or ""
    return {
        "eid": ep.get("eid") or ep.get("id") or "",
        "title": (ep.get("title") or "未命名").strip(),
        "audio_url": (enc.get("url") or "").strip(),
        "cover": (img or "").strip(),
        "duration": int(ep.get("duration") or 0),
        "description": ep.get("shownotes") or ep.get("description") or "",
        "pub_date": ep.get("pubDate") or ep.get("publishedAt") or "",
    }


def parse(url: str) -> dict:
    """返回 {'podcast_title','podcast_cover','episodes':[...]}。

    episodes 每个元素：eid/title/audio_url/cover/duration/description/pub_date
    """
    data = _fetch_json(url)
    pp = (data.get("props") or {}).get("pageProps") or {}

    pod = pp.get("podcast")
    if pod:
        episodes = [_episode_dict(e) for e in (pod.get("episodes") or [])]
        cover = (pod.get("image") or {}).get("picUrl") or pod.get("coverImage") or ""
        return {
            "podcast_title": pod.get("title") or "",
            "podcast_cover": (cover or "").strip(),
            "episodes": episodes,
        }

    ep = pp.get("episode")
    if ep:
        return {
            "podcast_title": (ep.get("podcast") or {}).get("title", ""),
            "podcast_cover": "",
            "episodes": [_episode_dict(ep)],
        }

    raise RuntimeError("未在小宇宙页面中找到节目或单集信息")


def episode_page_url(eid: str) -> str:
    return f"https://www.xiaoyuzhoufm.com/episode/{eid}"
