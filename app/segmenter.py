"""段落化：把 faster-whisper 的句子级 segment 聚合成自然段落。

做法 B（默认）：
    语义分段 —— 用 fastembed 加载中文小模型 ``BAAI/bge-small-zh-v1.5`` 把每句转成向量，
    按「相邻句余弦相似度 + 句间停顿」双信号切段：话题一变（相似度低）或停顿较长就另起一段。
    模型在你本机首次分段时自动联网下载并缓存（约 90~130MB，不进 exe）。

兜底：
    若语义模型不可用（如离线、下载失败），自动回退到纯规则分段（按停顿/句数），
    保证任何环境下都能产出段落，无需任何额外依赖。
"""
from __future__ import annotations

import math

# ---- 段落切分阈值（可调）---------------------------------------------------
SEM_SIM_THRESHOLD = 0.45   # 相邻句向量余弦相似度低于此值 → 新段落（话题转换）
PAUSE_THRESHOLD = 2.5       # 相邻句停顿（秒）超过此值 → 新段落（强信号）
MAX_SENTENCES = 12          # 单段最多句数，防止段落过长


def _cosine(a, b) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def _clean(segments):
    out = []
    for s in segments:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        out.append({
            "start": float(s.get("start", 0.0) or 0.0),
            "end": float(s.get("end", 0.0) or 0.0),
            "text": text,
        })
    return out


def _rule_paragraphs(segs):
    """纯规则分段：按停顿 + 句数切段，无需任何模型。"""
    paras, cur = [], []
    n = len(segs)
    for i, s in enumerate(segs):
        cur.append(s)
        gap = (segs[i + 1]["start"] - s["end"]) if i + 1 < n else 0.0
        gap = max(0.0, gap)
        if gap >= PAUSE_THRESHOLD or len(cur) >= MAX_SENTENCES:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    return paras


def _semantic_paragraphs(segs, on_log=None):
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5")
    texts = [s["text"] for s in segs]
    embeds = list(model.embed(texts))  # 首次会下载模型并缓存

    paras, cur = [], [segs[0]]
    n = len(segs)
    for i in range(1, n):
        prev, cur_s = segs[i - 1], segs[i]
        gap = max(0.0, cur_s["start"] - prev["end"])
        sim = _cosine(embeds[i - 1], embeds[i])
        if gap >= PAUSE_THRESHOLD or sim < SEM_SIM_THRESHOLD or len(cur) >= MAX_SENTENCES:
            paras.append(cur)
            cur = [cur_s]
        else:
            cur.append(cur_s)
    if cur:
        paras.append(cur)
    return paras


def paragraphize(segments, mode="semantic", on_log=None) -> list:
    """把句子级 segment 列表聚合成段落。

    返回段落列表，每段的字段：
        text      段落文本（句子拼接）
        start     段落首句起始时间（秒）
        end       段落末句结束时间（秒）
        segments  组成该段的原始句子列表
    """
    segs = _clean(segments)
    if not segs:
        return []

    if mode == "pause":
        grouped = _rule_paragraphs(segs)
    else:
        try:
            grouped = _semantic_paragraphs(segs, on_log)
        except Exception as e:  # 离线 / 下载失败 / 模型缺失 → 优雅回退
            if on_log:
                on_log("warn", f"语义分段暂不可用，已回退为规则分段：{e}")
            grouped = _rule_paragraphs(segs)

    out = []
    for g in grouped:
        out.append({
            "text": "".join(s["text"] for s in g),
            "start": g[0]["start"],
            "end": g[-1]["end"],
            "segments": g,
        })
    return out
