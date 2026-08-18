"""转写层：本地 faster-whisper（默认，离线、中文+中英混读效果好）
或可选 OpenAI Whisper API；输出简体中文 Markdown 逐字稿。"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from app import utils

SOURCE_LABELS = {
    "xiaoyuzhou": "小宇宙播客",
    "bilibili": "B站视频",
    "local": "本地音频",
}


class CancelRequested(Exception):
    pass


class Transcriber:
    def __init__(self, ffmpeg_path: str, settings, on_log=None):
        self.ffmpeg = ffmpeg_path
        self.settings = settings
        self.on_log = on_log or (lambda level, msg: None)
        self._model = None
        self._model_name = None

    # ----------------------------------------------------------- 音频预处理
    def to_audio(self, path: str, cancel_event, progress) -> str:
        """统一转换为 16k 单声道 wav，供 Whisper 输入（视频也先抽音轨）。"""
        tmp = tempfile.mkdtemp(prefix="mt_audio_")
        out = os.path.join(tmp, "audio.wav")
        cmd = [
            self.ffmpeg, "-y", "-i", path,
            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", out,
        ]
        progress(None, "transcribing", "正在提取音频…")
        self._run(cmd, cancel_event)
        if not os.path.exists(out):
            raise RuntimeError("音频提取失败")
        return out

    def _run(self, cmd, cancel_event):
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while proc.poll() is None:
            if cancel_event.is_set():
                proc.terminate()
                raise CancelRequested()
            cancel_event.wait(0.2)
        if proc.returncode != 0 and not cancel_event.is_set():
            raise RuntimeError("ffmpeg 处理失败")

    # ----------------------------------------------------------- 本地模型
    def _load_model(self, cancel_event, progress):
        name = self.settings.whisper_model
        if self._model and self._model_name == name:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError("未安装 faster-whisper，请在设置中改用 OpenAI API 模式，或重新安装依赖。")
        progress(None, "transcribing", f"首次使用正在加载模型 {name}（如需下载将耗时较久）…")
        self.on_log("task", f"正在加载语音模型 {name}（首次使用需联网下载，请耐心等待）…")
        device = None if self.settings.device == "auto" else self.settings.device
        compute = "int8" if (device in (None, "cpu")) else "float16"
        self._model = WhisperModel(name, device=device or "auto", compute_type=compute)
        self._model_name = name
        self.on_log("ok", f"模型 {name} 已就绪")
        return self._model

    # ----------------------------------------------------------- 分块转写
    def transcribe(self, path: str, cancel_event, progress) -> dict:
        if self.settings.asr_engine == "openai" and self.settings.openai_api_key:
            return self._transcribe_openai(path, cancel_event, progress)
        return self._transcribe_local(path, cancel_event, progress)

    def _transcribe_local(self, path, cancel_event, progress) -> dict:
        model = self._load_model(cancel_event, progress)
        self.on_log("task", f"开始转写：{os.path.basename(path)}")
        audio = self.to_audio(path, cancel_event, progress)
        # 分块以便显示真实进度
        chunks = self._split(audio, cancel_event, progress)
        segments_all = []
        n = max(1, len(chunks))
        offset = 0.0
        chunk_dur = 120.0
        for i, ch in enumerate(chunks):
            if cancel_event.is_set():
                raise CancelRequested()
            progress((i) / n * 100, "transcribing", f"转写中 {i+1}/{n}")
            seg_iter, _ = model.transcribe(
                ch, language="zh", beam_size=5, vad_filter=True,
                condition_on_previous_text=False,
            )
            for s in seg_iter:
                segments_all.append({
                    "start": offset + s.start,
                    "end": offset + s.end,
                    "text": s.text.strip(),
                })
            offset += chunk_dur
        text = "".join(s["text"] for s in segments_all)
        self.on_log("ok", f"转写完成：{os.path.basename(path)}（{len(segments_all)} 段）")
        return {"text": text, "segments": segments_all, "engine": "local", "error": ""}

    def _split(self, wav_path, cancel_event, progress):
        tmp = tempfile.mkdtemp(prefix="mt_chunk_")
        pattern = os.path.join(tmp, "c%03d.wav")
        cmd = [
            self.ffmpeg, "-y", "-i", wav_path,
            "-f", "segment", "-segment_time", "120",
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", pattern,
        ]
        self._run(cmd, cancel_event)
        files = sorted(
            os.path.join(tmp, f) for f in os.listdir(tmp) if f.endswith(".wav")
        )
        if not files:  # 极短音频兜底
            return [wav_path]
        return files

    # ----------------------------------------------------------- OpenAI API
    def _transcribe_openai(self, path, cancel_event, progress) -> dict:
        import requests
        progress(None, "transcribing", "正在调用 OpenAI 转写…")
        self.on_log("task", f"开始转写（OpenAI）：{os.path.basename(path)}")
        api_key = self.settings.openai_api_key
        url = "https://api.openai.com/v1/audio/transcriptions"
        audio = self.to_audio(path, cancel_event, progress)
        with open(audio, "rb") as f:
            files = {"file": ("audio.wav", f, "audio/wav")}
            data = {
                "model": self.settings.openai_model,
                "language": "zh",
                "response_format": "verbose_json",
            }
            headers = {"Authorization": f"Bearer {api_key}"}
            r = requests.post(url, files=files, data=data, headers=headers, timeout=600)
        if r.status_code != 200:
            raise RuntimeError(f"OpenAI API 错误 {r.status_code}: {r.text[:300]}")
        js = r.json()
        segs = js.get("segments") or []
        segments = [{"start": s.get("start", 0), "end": s.get("end", 0),
                     "text": (s.get("text") or "").strip()} for s in segs]
        text = js.get("text") or "".join(s["text"] for s in segments)
        return {"text": text, "segments": segments, "engine": "openai", "error": ""}

    # ----------------------------------------------------------- Markdown
    def write_markdown(self, out_dir: str, meta: dict, transcript: dict) -> str:
        safe = utils.sanitize_filename(meta.get("title") or "未命名")
        path = os.path.join(out_dir, f"{safe}.md")

        cover_rel = ""
        if meta.get("cover") and os.path.exists(meta["cover"]):
            # 复制封面到输出目录并相对引用，保证 md 可移植
            ext = os.path.splitext(meta["cover"])[1] or ".jpg"
            dest = os.path.join(out_dir, f"{safe}{ext}")
            if os.path.abspath(meta["cover"]) != os.path.abspath(dest):
                shutil.copy(meta["cover"], dest)
            cover_rel = f"{safe}{ext}"

        lines = []
        lines.append(f"# {meta.get('title', '未命名')}")
        lines.append("")
        label = SOURCE_LABELS.get(meta.get("source"), meta.get("source", ""))
        info = f"> 来源：**{label}**"
        if meta.get("channel"):
            info += f" · 主播/UP：{meta['channel']}"
        if meta.get("upload_date"):
            info += f" · 发布：{meta['upload_date']}"
        if meta.get("duration"):
            info += f" · 时长：{utils.fmt_duration(meta['duration'])}"
        lines.append(info)
        if meta.get("webpage_url"):
            lines.append(f"> 链接：{meta['webpage_url']}")
        if cover_rel:
            lines.append("")
            lines.append(f"![封面]({cover_rel})")
        lines.append("")
        lines.append(f"_（本稿由 {transcript.get('engine','whisper')} 引擎自动转写，中文（含中英混读）识别，仅供参考）_")
        lines.append("")

        # 全文
        lines.append("## 全文")
        lines.append("")
        lines.append(transcript.get("text", "").strip() or "（无识别内容）")
        lines.append("")

        # 带时间轴
        lines.append("## 逐字稿（带时间轴）")
        lines.append("")
        for s in transcript.get("segments", []):
            ts = utils.fmt_duration(s.get("start", 0))
            lines.append(f"**[{ts}]** {s.get('text','').strip()}")
            lines.append("")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path
