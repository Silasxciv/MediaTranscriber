"""任务队列：线程池并发、批量下载+转写、实时进度与取消。"""
from __future__ import annotations

import os
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from app import utils
from app.asr import Transcriber, CancelRequested
from app.downloader import Downloader

KIND_FOLDERS = {
    "xiaoyuzhou": "小宇宙",
    "bilibili": "B站视频",
    "local": "本地音频",
}


class Task:
    def __init__(self, kind: str, source: str, transcribe: bool, label: str = ""):
        self.id = uuid.uuid4().hex[:8]
        self.kind = kind
        self.source = source
        self.transcribe = transcribe
        self.label = label or source
        self.title = ""
        self.status = "queued"      # queued|running|done|error|cancelled
        self.phase = "queued"       # queued|downloading|transcribing|done
        self.progress = None        # 0-100 或 None(不确定)
        self.message = "等待中"
        self.error = ""
        self.outputs = {}           # {media, markdown, cover}
        self.cancel_event = threading.Event()
        self.cancel_requested = False


class TaskManager:
    def __init__(self, settings, ffmpeg_path, on_update=None, on_done=None, on_log=None):
        self.settings = settings
        self.ffmpeg = ffmpeg_path
        self.on_update = on_update or (lambda t: None)
        self.on_done = on_done or (lambda t: None)
        self.on_log = on_log or (lambda level, msg: None)
        self._downloader = None
        self._transcriber = None
        self._lock = threading.Lock()
        self.tasks = {}
        self._executor = ThreadPoolExecutor(max_workers=max(1, settings.concurrent_tasks))

    # ----------------------------------------------------------- 懒加载
    def _dl(self) -> Downloader:
        if self._downloader is None:
            self._downloader = Downloader(self.ffmpeg, on_log=self.on_log)
        return self._downloader

    def _asr(self) -> Transcriber:
        if self._transcriber is None:
            self._transcriber = Transcriber(self.ffmpeg, self.settings, on_log=self.on_log)
        return self._transcriber

    # ----------------------------------------------------------- 任务管理
    def add(self, kind: str, source: str, transcribe: bool, label: str = "") -> Task:
        t = Task(kind, source, transcribe, label)
        with self._lock:
            self.tasks[t.id] = t
        self.on_log("task", f"新建任务：{label}")
        self._executor.submit(self._run, t)
        return t

    def cancel(self, task_id: str):
        t = self.tasks.get(task_id)
        if not t:
            return
        t.cancel_requested = True
        t.cancel_event.set()

    def get(self, task_id):
        return self.tasks.get(task_id)

    def all(self):
        return list(self.tasks.values())

    def clear(self):
        """取消所有进行中/排队中的任务，并清空整个队列。

        已结束（完成/失败/已取消）的任务线程不会再触发回调，直接丢弃。
        """
        with self._lock:
            for t in self.tasks.values():
                if t.status in ("queued", "running"):
                    t.cancel_requested = True
                    t.cancel_event.set()
            self.tasks.clear()

    # ----------------------------------------------------------- 执行
    def _run(self, task: Task):
        if task.cancel_requested:
            task.status = "cancelled"
            task.message = "已取消"
            self.on_done(task)
            return
        task.status = "running"
        self.on_log("task", f"开始处理：{task.label}")
        self.on_update(task)

        def prog(p, phase, msg):
            task.progress = p
            task.phase = phase
            task.message = msg
            self.on_update(task)

        try:
            if task.kind in ("xiaoyuzhou", "bilibili"):
                self._run_remote(task, prog)
            else:
                self._run_local(task, prog)
            if task.cancel_event.is_set():
                raise CancelRequested()
            task.status = "done"
            task.phase = "done"
            task.progress = 100
            task.message = "完成"
        except CancelRequested:
            task.status = "cancelled"
            task.message = "已取消"
        except Exception as e:
            task.status = "error"
            task.error = str(e)[:500]
            task.message = f"失败：{task.error}"
        self.on_done(task)

    def _run_remote(self, task, prog):
        dl = self._dl()
        out_dir = os.path.join(self.settings.output_dir, KIND_FOLDERS[task.kind])
        res = dl.download(task.source, task.kind, out_dir, task.cancel_event, prog)
        if res.get("cancelled"):
            raise CancelRequested()
        if not res.get("ok"):
            raise RuntimeError(res.get("error") or "下载失败")
        meta = res["metadata"]
        meta["cover"] = res.get("cover", "")
        meta["source"] = task.kind
        meta["title"] = meta.get("title") or utils.sanitize_filename("未命名")
        task.title = meta["title"]
        self.on_log("ok", f"下载完成：{task.title}")
        media = res["file"]
        if task.transcribe:
            self.on_log("task", f"开始转写：{task.title}")
            trans = self._asr().transcribe(media, task.cancel_event, prog)
            md = self._asr().write_markdown(out_dir, meta, trans)
            task.outputs = {"media": media, "markdown": md, "cover": res.get("cover")}
        else:
            task.outputs = {"media": media, "cover": res.get("cover")}

    def _run_local(self, task, prog):
        path = task.source
        out_dir = os.path.join(self.settings.output_dir, KIND_FOLDERS["local"])
        os.makedirs(out_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(path))[0]
        meta = {
            "title": utils.sanitize_filename(base),
            "source": "local",
            "upload_date": "",
            "thumbnail": "",
            "duration": 0,
            "description": "",
            "webpage_url": "",
            "channel": "",
        }
        task.title = meta["title"]
        if task.transcribe:
            self.on_log("task", f"开始转写：{os.path.basename(path)}")
            trans = self._asr().transcribe(path, task.cancel_event, prog)
            md = self._asr().write_markdown(out_dir, meta, trans)
            task.outputs = {"media": path, "markdown": md}
        else:
            dest = os.path.join(out_dir, os.path.basename(path))
            if os.path.abspath(path) != os.path.abspath(dest):
                shutil.copy(path, dest)
            task.outputs = {"media": dest}

    def shutdown(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
