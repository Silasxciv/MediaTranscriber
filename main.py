"""GUI 主程序：微信桌面端风格（简洁、圆角卡片、非全屏）。

三栏式布局：左侧导航 + 顶部信息条 + 主内容区（功能页 / 任务队列）。
"""
from __future__ import annotations

import os
import threading
import time
import webbrowser

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageDraw

from app import __version__, APP_NAME
from app import utils
from app.config import Settings, ensure_ffmpeg
from app.downloader import parse_links, detect_source
from app.tasks import TaskManager
from app import xiaoyuzhou

# 微信风格配色
WX_GREEN = "#07C160"
WX_GREEN_HOVER = "#06AD56"
WX_BG = "#F5F5F5"
WX_SIDEBAR = "#ECECEC"
WX_CARD = "#FFFFFF"
WX_TEXT = "#1A1A1A"
WX_SUB = "#5A5A5A"
WX_GREEN_SOFT = "#D4ECD7"   # 导航激活态浅绿底（轻量，在灰侧栏上仍可见）
WX_GREEN_TXT = "#2E7D32"    # 导航激活态绿色文字

ctk.set_default_color_theme("green")


def _nav_icon(kind, color):
    """绘制与展示图一致的单色线框导航图标（Pillow 内存生成，避免 emoji 风格差异）。"""
    s = 24
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = color
    if kind == "xiaoyuzhou":           # 麦克风
        d.ellipse([7, 7, 17, 17], outline=col, width=2)
        d.line([12, 7, 12, 3], fill=col, width=2)
        d.arc([8, 16, 16, 23], start=200, end=340, fill=col, width=2)
    elif kind == "bilibili":           # 播放三角
        d.polygon([(8, 5), (8, 19), (18, 12)], fill=col)
    elif kind == "local":              # 声波
        d.line([7, 9, 7, 15], fill=col, width=2)
        d.line([12, 5, 12, 19], fill=col, width=2)
        d.line([17, 9, 17, 15], fill=col, width=2)
    elif kind == "tasks":              # 列表
        d.line([6, 7, 18, 7], fill=col, width=2)
        d.line([6, 12, 18, 12], fill=col, width=2)
        d.line([6, 17, 18, 17], fill=col, width=2)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(14, 14))


class Toast:
    """轻量非阻塞完成提示。"""
    def __init__(self, root):
        self.root = root

    def show(self, title, msg, kind="info"):
        colors = {"info": "#07C160", "error": "#FA5151", "warn": "#FF9D00"}
        tl = ctk.CTkToplevel(self.root)
        tl.geometry("300x80")
        tl.overrideredirect(True)
        tl.attributes("-topmost", True)
        tl.configure(fg_color=colors.get(kind, "#07C160"))
        ctk.CTkLabel(tl, text=title, font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="white").pack(anchor="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(tl, text=msg, font=ctk.CTkFont(size=12),
                     text_color="white", wraplength=270).pack(anchor="w", padx=16)
        # 居中偏右下
        self.root.update_idletasks()
        x = self.root.winfo_x() + self.root.winfo_width() - 320
        y = self.root.winfo_y() + self.root.winfo_height() - 120
        tl.geometry(f"+{x}+{y}")
        tl.after(3200, tl.destroy)


class LogPanel:
    """底部常驻运行日志控制台（调用方需保证在主线程写入）。"""
    COLORS = {
        "info": "#3A3A3A", "ok": "#07C160", "warn": "#FF9D00",
        "error": "#FA5151", "ffmpeg": "#1677FF", "task": "#7A5CFF",
    }
    TAGS = {
        "info": "lg_info", "ok": "lg_ok", "warn": "lg_warn",
        "error": "lg_err", "ffmpeg": "lg_ff", "task": "lg_task",
    }

    def __init__(self, master):
        self.frame = ctk.CTkFrame(master, fg_color=WX_CARD, corner_radius=0,
                                  border_width=1, border_color="#E6E6E6")
        hdr = ctk.CTkFrame(self.frame, fg_color="transparent", height=34)
        hdr.pack(fill="x", side="top")
        ctk.CTkLabel(hdr, text="📜 运行日志", font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=WX_TEXT).pack(side="left", padx=14, pady=6)
        self.toggle_btn = ctk.CTkButton(hdr, text="收起 ▴", width=64, height=24,
                                         font=ctk.CTkFont(size=11),
                                         fg_color="#F2F2F2", hover_color="#E5E5E5",
                                         text_color=WX_TEXT, command=self.toggle)
        self.toggle_btn.pack(side="right", padx=(0, 6))
        ctk.CTkButton(hdr, text="清空", width=52, height=24, font=ctk.CTkFont(size=11),
                      fg_color="#F2F2F2", hover_color="#E5E5E5", text_color=WX_TEXT,
                      command=self.clear).pack(side="right", padx=(0, 6))

        self.body = tk.Text(self.frame, font=("Consolas", "11"), bg="#FBFBFB",
                            fg="#3A3A3A", relief="flat", wrap="word", height=8,
                            state="disabled", borderwidth=0, padx=10, pady=6)
        for lvl, tag in self.TAGS.items():
            self.body.tag_config(tag, foreground=self.COLORS[lvl])
        self.body.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self._collapsed = False
        self.log("info", "日志已就绪，等待操作…")

    def log(self, level, msg):
        tag = self.TAGS.get(level, "lg_info")
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.body.configure(state="normal")
        self.body.insert("end", line)
        self.body.tag_add(tag, "end-1l linestart", "end-1c")
        self.body.configure(state="disabled")
        self.body.see("end")
        self._trim()

    def _trim(self):
        lines = int(self.body.index("end-1c").split(".")[0])
        if lines > 2000:
            self.body.configure(state="normal")
            self.body.delete("1.0", f"{lines - 1500}.0")
            self.body.configure(state="disabled")

    def clear(self):
        self.body.configure(state="normal")
        self.body.delete("1.0", "end")
        self.body.configure(state="disabled")

    def toggle(self):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.body.pack_forget()
            self.toggle_btn.configure(text="展开 ▾")
        else:
            self.body.pack(fill="both", expand=True, padx=6, pady=(0, 6))
            self.toggle_btn.configure(text="收起 ▴")


class TaskCard(ctk.CTkFrame):
    def __init__(self, master, task, on_open, on_cancel, on_open_dir, on_retry, **kw):
        super().__init__(master, corner_radius=14, fg_color=WX_CARD,
                         border_width=1, border_color="#E3E3E3", **kw)
        self.task = task
        self.on_open = on_open
        self.on_cancel = on_cancel
        self.on_open_dir = on_open_dir
        self.on_retry = on_retry
        self._pulsing = False
        self._pulse_val = 0.0

        ctk.CTkLabel(self, text=self._kind_icon(), font=ctk.CTkFont(size=20)).grid(
            row=0, column=0, rowspan=2, padx=(14, 8), pady=12)
        self.title_lbl = ctk.CTkLabel(self, text=self._title(),
                                      font=ctk.CTkFont(size=14, weight="bold"),
                                      anchor="w", text_color=WX_TEXT)
        self.title_lbl.grid(row=0, column=1, sticky="ew", padx=6, pady=(12, 0))
        self.status_lbl = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12),
                                       anchor="w", text_color=WX_SUB)
        self.status_lbl.grid(row=1, column=1, sticky="ew", padx=6, pady=(0, 4))
        self.grid_columnconfigure(1, weight=1)

        self.bar = ctk.CTkProgressBar(self, height=6, corner_radius=3)
        self.bar.set(0)
        self.bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 6))

        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.grid(row=3, column=0, columnspan=2, sticky="e", padx=10, pady=(0, 10))
        self._build_buttons()

    def _kind_icon(self):
        return {"xiaoyuzhou": "🎙️", "bilibili": "📺", "local": "🎵"}.get(self.task.kind, "📄")

    def _title(self):
        t = self.task.title or self.task.label
        if len(t) > 60:
            t = t[:57] + "…"
        return t

    def _build_buttons(self):
        for w in self.btn_frame.winfo_children():
            w.destroy()
        self.cancel_btn = ctk.CTkButton(self.btn_frame, text="取消", width=56, height=26,
                                        font=ctk.CTkFont(size=12),
                                        fg_color="#F2F2F2", hover_color="#E5E5E5",
                                        text_color="#FA5151",
                                        command=lambda: self.on_cancel(self.task.id))
        self.cancel_btn.pack(side="right", padx=4)
        if self.task.status == "done":
            self.cancel_btn.destroy()
            if self.task.outputs.get("markdown"):
                ctk.CTkButton(self.btn_frame, text="打开文稿", width=72, height=26,
                              font=ctk.CTkFont(size=12),
                              fg_color=WX_GREEN, hover_color=WX_GREEN_HOVER,
                              text_color="white",
                              command=lambda: self.on_open(self.task.outputs["markdown"])).pack(side="right", padx=4)
            ctk.CTkButton(self.btn_frame, text="打开文件", width=72, height=26,
                          font=ctk.CTkFont(size=12),
                          fg_color=WX_GREEN, hover_color=WX_GREEN_HOVER, text_color="white",
                          command=lambda: self.on_open(self.task.outputs.get("media"))).pack(side="right", padx=4)
            ctk.CTkButton(self.btn_frame, text="打开目录", width=72, height=26,
                          font=ctk.CTkFont(size=12),
                          fg_color="#F2F2F2", hover_color="#E5E5E5", text_color=WX_TEXT,
                          command=lambda: self.on_open_dir(self.task)).pack(side="right", padx=4)
        elif self.task.status in ("error", "cancelled"):
            self.cancel_btn.destroy()
            ctk.CTkButton(self.btn_frame, text="重试", width=56, height=26,
                          font=ctk.CTkFont(size=12),
                          fg_color=WX_GREEN, hover_color=WX_GREEN_HOVER, text_color="white",
                          command=lambda: self.on_retry(self.task)).pack(side="right", padx=4)

    def update(self, task):
        self.task = task
        self.title_lbl.configure(text=self._title())
        msg = task.message or ""
        if task.status == "running" and task.progress is not None:
            msg = f"{msg}  {task.progress:.0f}%"
        self.status_lbl.configure(text=f"[{self._status_cn()}] {msg}".strip())
        if task.status == "running" and task.progress is None:
            self._start_pulse()
        else:
            self._stop_pulse()
            self.bar.set(max(0.0, min(1.0, (task.progress or 0) / 100.0)))
        self._build_buttons()

    def _status_cn(self):
        return {"queued": "排队", "running": "进行中", "done": "完成",
                "error": "失败", "cancelled": "已取消"}.get(self.task.status, "")

    def _start_pulse(self):
        if self._pulsing:
            return
        self._pulsing = True
        self._pulse_val = 0.0
        self._tick()

    def _tick(self):
        if not self._pulsing:
            return
        self._pulse_val = (self._pulse_val + 0.06) % 1.0
        self.bar.set(self._pulse_val)
        self.after(120, self._tick)

    def _stop_pulse(self):
        self._pulsing = False


class App:
    def __init__(self):
        self.settings = Settings()
        ctk.set_appearance_mode(self.settings.theme)

        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME}  v{__version__}")
        # 竖屏比例（高度 > 宽度），适合单栏内容 + 底部日志的阅读场景
        self.W, self.H = 820, 980
        self.root.geometry(f"{self.W}x{self.H}")
        self.root.minsize(700, 760)
        self._center()
        self.root.configure(fg_color=WX_BG)

        self.local_files = []
        self.cards = {}
        self._cleared_ids = set()   # 记录被「清空」移除的任务，拦截其延迟到达的回调
        self.ffmpeg = None
        self.manager = None
        self._logpanel = None

        self._build_sidebar()
        self._build_topbar()
        self._build_views()
        self._build_logpanel()
        self.toast = Toast(self.root)

        self.show_view("xiaoyuzhou")
        self.log("info", f"{APP_NAME} v{__version__} 启动")
        self._set_status("环境准备中…")
        # ffmpeg 可能首次需下载；后台准备，避免阻塞界面，进度实时写入日志
        threading.Thread(target=self._prep_ffmpeg, daemon=True).start()
        self.root.mainloop()

    # ----------------------------------------------------------- ffmpeg 准备
    def _prep_ffmpeg(self):
        self.log("info", "正在检查 ffmpeg（音频/视频处理所需组件）…")
        try:
            ffmpeg = ensure_ffmpeg(
                on_progress=lambda p, m: self.log(
                    "ffmpeg", f"{m}" + (f"  {p}%" if p is not None else ""))
            )
        except FileNotFoundError as e:
            self.log("error", f"ffmpeg 准备失败：{e}")
            self.root.after(0, lambda: messagebox.showerror("缺少 ffmpeg", str(e)))
            self._set_status("环境未就绪")
            return
        self.ffmpeg = ffmpeg
        self.log("ok", f"ffmpeg 已就绪：{os.path.basename(ffmpeg)}")
        self._build_manager()
        self.log("ok", "运行环境就绪，可以开始添加任务 ✅")
        self._set_status("就绪")

    # ----------------------------------------------------------- 日志 / 状态
    def log(self, level, msg):
        if getattr(self, "_logpanel", None):
            self.root.after(0, self._logpanel.log, level, msg)

    def _on_log(self, level, msg):
        self.log(level, msg)

    def _set_status(self, text):
        if getattr(self, "stat_lbl", None):
            self.root.after(0, lambda: self.stat_lbl.configure(text=text))

    def _build_logpanel(self):
        self._logpanel = LogPanel(self.root)
        self._logpanel.frame.grid(row=2, column=1, sticky="ew")
        self.root.grid_rowconfigure(2, weight=0, minsize=150)

    # ----------------------------------------------------------- 布局
    def _center(self):
        self.root.update_idletasks()
        w, h = self.W, self.H
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self.root, width=184, fg_color=WX_SIDEBAR, corner_radius=0)
        sb.grid(row=0, column=0, rowspan=3, sticky="ns")
        sb.grid_propagate(False)
        ctk.CTkLabel(sb, text="媒体转写助手", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=WX_TEXT).pack(pady=(12, 1))
        ctk.CTkLabel(sb, text="播客 · 视频 · 音频 → 文稿", font=ctk.CTkFont(size=9),
                     text_color=WX_SUB).pack(pady=(0, 6))

        # 四个导航项：每个 = 一个可点击的 Frame（悬停/激活背景）+ 内部一个 compound Label（图标+文字紧挨）。
        # 不再嵌套多层 Frame / Grid，让内容自然决定大小，天然紧凑。
        nav_group = ctk.CTkFrame(sb, fg_color="transparent")
        nav_group.pack(pady=(4, 4))

        self.nav_items = {}
        items = [("xiaoyuzhou", "小宇宙"), ("bilibili", "B站视频"),
                 ("local", "本地音频"), ("tasks", "任务队列")]

        def on_enter(it):
            if self.current != it._nav_key:
                it.configure(fg_color="#EAEAEA")

        def on_leave(it):
            if self.current != it._nav_key:
                it.configure(fg_color="transparent")

        for key, txt in items:
            img_off = _nav_icon(key, WX_SUB)
            img_on = _nav_icon(key, WX_GREEN_TXT)

            # 外框：只负责点击区域 + 悬停/激活底色；不锁尺寸，由内容撑开
            item = ctk.CTkFrame(nav_group, fg_color="transparent", corner_radius=6)
            item.pack(fill="x", pady=1)
            item._nav_key = key  # 绑定 key 供闭包用

            # 唯一内层：图标 + 文字合为一个 Label（compound=left），天然紧凑
            lbl = ctk.CTkLabel(item, text=txt, image=img_off, compound="left",
                               font=ctk.CTkFont(size=12),
                               text_color=WX_TEXT, cursor="hand2",
                               anchor="w", padx=10, pady=5)
            lbl.pack(anchor="w")

            for w in (item, lbl):
                w.bind("<Button-1>", lambda e, k=key: self.show_view(k))
            item.bind("<Enter>", lambda e, it=item: on_enter(it))
            item.bind("<Leave>", lambda e, it=item: on_leave(it))
            self.nav_items[key] = (item, lbl, img_on, img_off)

        ctk.CTkButton(sb, text="⚙  设置", height=26, anchor="w",
                      font=ctk.CTkFont(size=10), fg_color="transparent",
                      hover_color="#DCDCDC", text_color=WX_SUB, corner_radius=6,
                      command=self.open_settings).pack(side="bottom", fill="x", padx=8, pady=(0, 8))

    def _build_topbar(self):
        tb = ctk.CTkFrame(self.root, height=56, fg_color=WX_CARD, corner_radius=0)
        tb.grid(row=0, column=1, sticky="ew")
        tb.grid_columnconfigure(1, weight=1)
        self.section_lbl = ctk.CTkLabel(tb, text="", font=ctk.CTkFont(size=16, weight="bold"),
                                        text_color=WX_TEXT)
        self.section_lbl.grid(row=0, column=0, padx=18, pady=14)
        self.stat_lbl = ctk.CTkLabel(tb, text="", font=ctk.CTkFont(size=12), text_color=WX_SUB)
        self.stat_lbl.grid(row=0, column=1, sticky="e", padx=10)
        ctk.CTkButton(tb, text="打开输出目录", width=110, height=32,
                      font=ctk.CTkFont(size=12), fg_color="#F2F2F2", hover_color="#E5E5E5",
                      text_color=WX_TEXT, command=self.open_output_dir).grid(row=0, column=2, padx=10)
        ctk.CTkButton(tb, text="更改目录", width=90, height=32,
                      font=ctk.CTkFont(size=12), fg_color=WX_GREEN, hover_color=WX_GREEN_HOVER,
                      text_color="white", command=self.change_output_dir).grid(row=0, column=3, padx=(0, 16))

    def _build_views(self):
        self.content = ctk.CTkFrame(self.root, fg_color=WX_BG, corner_radius=0)
        self.content.grid(row=1, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)   # 关键：否则各视图 f 不横向扩展，滚动区缩在中间
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(1, weight=1)
        self.views = {}
        for name in ("xiaoyuzhou", "bilibili", "local", "tasks"):
            f = ctk.CTkFrame(self.content, fg_color=WX_BG, corner_radius=0)
            f.grid(row=0, column=0, sticky="nsew")
            f.grid_remove()
            self.views[name] = f
        self._build_input_view("xiaoyuzhou", "小宇宙播客下载",
                               "粘贴小宇宙节目链接，每行一个（支持批量）。勾选后可自动生成文字稿。")
        self._build_input_view("bilibili", "B站视频下载",
                               "粘贴 B站视频链接，每行一个（支持批量）。将下载当前最高清晰度。")
        self._build_local_view()
        self._build_tasks_view()

    def _build_input_view(self, key, title, desc):
        f = self.views[key]
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=WX_TEXT).pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(f, text=desc, font=ctk.CTkFont(size=12), text_color=WX_SUB).pack(
            anchor="w", padx=24, pady=(0, 12))

        box = ctk.CTkFrame(f, fg_color=WX_CARD, corner_radius=14, border_width=1,
                           border_color="#E3E3E3")
        box.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        self.textbox = ctk.CTkTextbox(box, font=ctk.CTkFont(size=13), corner_radius=8,
                                      border_width=0, wrap="word")
        self.textbox.pack(fill="both", expand=True, padx=14, pady=14)
        setattr(self, f"textbox_{key}", self.textbox)

        opt = ctk.CTkFrame(f, fg_color="transparent")
        opt.pack(fill="x", padx=24, pady=(0, 14))
        chk = ctk.CTkCheckBox(opt, text=("生成文字稿" if key == "xiaoyuzhou"
                                         else "提取文字并生成文稿"),
                              font=ctk.CTkFont(size=13), checkbox_width=20, checkbox_height=20,
                              text_color=WX_TEXT,
                              fg_color=WX_GREEN, hover_color=WX_GREEN_HOVER)
        chk.pack(side="left")
        setattr(self, f"chk_{key}", chk)
        ctk.CTkButton(opt, text="加入队列", width=120, height=36,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      fg_color=WX_GREEN, hover_color=WX_GREEN_HOVER, text_color="white",
                      command=lambda k=key: self.add_from_text(k)).pack(side="right")

    def _build_local_view(self):
        key = "local"
        f = self.views[key]
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(f, text="本地音频导入", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=WX_TEXT).pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(f, text="选择本地音频/视频文件，执行转写流程生成逐字稿。",
                     font=ctk.CTkFont(size=12), text_color=WX_SUB).pack(anchor="w", padx=24, pady=(0, 12))

        ctk.CTkButton(f, text="＋ 选择音频/视频文件", width=200, height=36,
                      font=ctk.CTkFont(size=13),
                      fg_color=WX_GREEN, hover_color=WX_GREEN_HOVER, text_color="white",
                      command=self.pick_local_files).pack(anchor="w", padx=24, pady=(0, 10))

        self.local_list = ctk.CTkScrollableFrame(f, fg_color=WX_CARD, corner_radius=14,
                                                 border_width=1, border_color="#E3E3E3")
        self.local_list.pack(fill="both", expand=True, padx=24, pady=(0, 12))

        opt = ctk.CTkFrame(f, fg_color="transparent")
        opt.pack(fill="x", padx=24, pady=(0, 14))
        chk = ctk.CTkCheckBox(opt, text="生成逐字稿", font=ctk.CTkFont(size=13),
                              checkbox_width=20, checkbox_height=20,
                              text_color=WX_TEXT,
                              fg_color=WX_GREEN, hover_color=WX_GREEN_HOVER)
        chk.select()
        chk.pack(side="left")
        setattr(self, f"chk_{key}", chk)
        ctk.CTkButton(opt, text="加入队列", width=120, height=36,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      fg_color=WX_GREEN, hover_color=WX_GREEN_HOVER, text_color="white",
                      command=self.add_local).pack(side="right")

    def _build_tasks_view(self):
        f = self.views["tasks"]
        f.grid_columnconfigure(0, weight=1)
        f.grid_rowconfigure(1, weight=1)
        hdr = ctk.CTkFrame(f, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=24, pady=(16, 4))
        ctk.CTkLabel(hdr, text="任务队列", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=WX_TEXT).pack(side="left")
        ctk.CTkButton(hdr, text="清空", width=72, height=32,
                      font=ctk.CTkFont(size=12), fg_color="#F2F2F2", hover_color="#FBE3E3",
                      text_color="#FA5151", command=self.clear_all).pack(side="right", padx=(0, 8))
        ctk.CTkButton(hdr, text="全部取消", width=90, height=32,
                      font=ctk.CTkFont(size=12), fg_color="#F2F2F2", hover_color="#E5E5E5",
                      text_color="#FA5151", command=self.cancel_all).pack(side="right")

        self.tasks_frame = ctk.CTkScrollableFrame(f, fg_color=WX_BG, corner_radius=0)
        self.tasks_frame.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)

    # ----------------------------------------------------------- 管理
    def _build_manager(self):
        if not self.ffmpeg:
            return
        self.manager = TaskManager(
            self.settings, self.ffmpeg,
            on_update=self._on_update, on_done=self._on_done,
            on_log=self._on_log,
        )

    # ----------------------------------------------------------- 视图切换
    def show_view(self, name):
        self.current = name
        titles = {"xiaoyuzhou": "小宇宙播客下载", "bilibili": "B站视频下载",
                  "local": "本地音频导入", "tasks": "任务队列"}
        self.section_lbl.configure(text=titles.get(name, ""))
        for k, v in self.views.items():
            if k == name:
                v.grid()
            else:
                v.grid_remove()
        for k, (item, lbl, img_on, img_off) in self.nav_items.items():
            active = (k == name)
            item.configure(fg_color=WX_GREEN_SOFT if active else "transparent")
            lbl.configure(image=img_on if active else img_off,
                          text_color=WX_GREEN_TXT if active else WX_TEXT)

    # ----------------------------------------------------------- 添加任务
    def add_from_text(self, key):
        if not self.manager:
            self.log("warn", "环境尚未就绪，已拒绝添加（请在日志中查看准备进度）")
            self.toast.show("请稍候", "环境准备中，请稍后重试", "warn")
            return
        tb = getattr(self, f"textbox_{key}")
        text = tb.get("0.0", "end").strip()
        links = parse_links(text)
        if not links:
            messagebox.showinfo("提示", "请先粘贴有效的链接。")
            return
        chk = getattr(self, f"chk_{key}")
        transcribe = bool(chk.get())
        added = 0
        for url in links:
            if key == "xiaoyuzhou":
                # 小宇宙：节目页展开为「每集一个任务」，单集页则单个任务
                added += self._add_xiaoyuzhou(url, transcribe)
            else:
                self.manager.add(key, url, transcribe, label=url)
                added += 1
        tb.delete("0.0", "end")
        self.log("task", f"已加入队列：{added} 个链接" + ("（含转写）" if transcribe else "（仅下载）"))
        self.toast.show("已加入队列", f"共添加 {added} 个任务", "info")
        self.show_view("tasks")
        self._refresh_stats()

    def _add_xiaoyuzhou(self, url: str, transcribe: bool) -> int:
        """解析小宇宙页面，展开为每集一个任务；解析失败则回退为单个原始链接任务。"""
        try:
            info = xiaoyuzhou.parse(url)
            eps = info.get("episodes") or []
            if not eps:
                raise RuntimeError("未找到单集")
            for ep in eps:
                if not ep.get("eid"):
                    continue
                ep_url = xiaoyuzhou.episode_page_url(ep["eid"])
                self.manager.add("xiaoyuzhou", ep_url, transcribe, label=ep["title"])
            return len(eps)
        except Exception as e:
            self.log("warn", f"小宇宙解析失败，仅添加原始链接：{e}")
            self.manager.add("xiaoyuzhou", url, transcribe, label=url)
            return 1

    def pick_local_files(self):
        paths = filedialog.askopenfilenames(
            title="选择音频/视频文件",
            filetypes=[("音频", "*.mp3 *.m4a *.aac *.wav *.flac *.ogg *.opus *.wma *.ape"),
                       ("视频", "*.mp4 *.mkv *.mov *.webm *.avi *.flv"),
                       ("全部", "*.*")])
        for p in paths:
            if p not in self.local_files:
                self.local_files.append(p)
        self._render_local_list()

    def _render_local_list(self):
        for w in self.local_list.winfo_children():
            w.destroy()
        if not self.local_files:
            ctk.CTkLabel(self.local_list, text="（尚未选择文件）", text_color=WX_SUB,
                         font=ctk.CTkFont(size=12)).pack(pady=20)
            return
        for p in self.local_files:
            row = ctk.CTkFrame(self.local_list, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text="🎵 " + os.path.basename(p), anchor="w",
                         font=ctk.CTkFont(size=12), text_color=WX_TEXT).pack(side="left", padx=6)
            ctk.CTkButton(row, text="移除", width=56, height=24,
                          font=ctk.CTkFont(size=11), fg_color="#F2F2F2",
                          hover_color="#E5E5E5", text_color="#FA5151",
                          command=lambda pp=p: self._remove_local(pp)).pack(side="right", padx=6)

    def _remove_local(self, p):
        if p in self.local_files:
            self.local_files.remove(p)
        self._render_local_list()

    def add_local(self):
        if not self.manager:
            self.log("warn", "环境尚未就绪，已拒绝添加（请在日志中查看准备进度）")
            self.toast.show("请稍候", "环境准备中，请稍后重试", "warn")
            return
        if not self.local_files:
            messagebox.showinfo("提示", "请先选择至少一个文件。")
            return
        chk = getattr(self, f"chk_local")
        transcribe = bool(chk.get())
        n = len(self.local_files)
        for p in self.local_files:
            self.manager.add("local", p, transcribe, label=os.path.basename(p))
        self.local_files = []
        self._render_local_list()
        self.log("task", f"已加入队列：{n} 个本地文件" + ("（含转写）" if transcribe else "（仅拷贝）"))
        self.toast.show("已加入队列", "本地文件任务已添加", "info")
        self.show_view("tasks")
        self._refresh_stats()

    # ----------------------------------------------------------- 回调
    def _on_update(self, task):
        self.root.after(0, self._refresh_task, task)

    def _on_done(self, task):
        self.root.after(0, self._refresh_task, task)
        name = task.title or task.label
        if task.status == "done":
            self.log("ok", f"完成：{name}")
            self.toast.show("任务完成", name, "info")
        elif task.status == "error":
            self.log("error", f"失败：{name} — {task.error[:160]}")
            self.toast.show("任务失败", task.error[:80], "error")
        elif task.status == "cancelled":
            self.log("warn", f"已取消：{name}")
            self.toast.show("已取消", name, "warn")
        self._refresh_stats()

    def _refresh_task(self, task):
        # 该任务已被用户「清空」移除，忽略其可能因取消而延迟到达的后续回调
        if task.id in self._cleared_ids:
            return
        card = self.cards.get(task.id)
        if card is None:
            card = TaskCard(self.tasks_frame, task,
                            on_open=self.open_file, on_cancel=self.cancel_task,
                            on_open_dir=self.open_task_dir, on_retry=self.retry_task)
            card.pack(fill="x", padx=10, pady=6)
            self.cards[task.id] = card
        else:
            card.update(task)
        self._refresh_stats()

    def _refresh_stats(self):
        if not self.manager:
            return
        ts = self.manager.all()
        running = sum(1 for t in ts if t.status == "running")
        done = sum(1 for t in ts if t.status == "done")
        err = sum(1 for t in ts if t.status == "error")
        total = len(ts)
        self.stat_lbl.configure(text=f"共 {total} · 进行中 {running} · 完成 {done} · 失败 {err}")

    # ----------------------------------------------------------- 操作
    def cancel_task(self, tid):
        if self.manager:
            self.manager.cancel(tid)

    def cancel_all(self):
        if not self.manager:
            return
        for t in self.manager.all():
            if t.status in ("queued", "running"):
                self.manager.cancel(t.id)

    def clear_all(self):
        """清空整个任务队列：取消进行中任务并移除全部卡片（不删除已生成的输出文件）。"""
        if not self.manager:
            return
        tasks = self.manager.all()
        if not tasks:
            return
        ok = messagebox.askyesno(
            "清空任务队列",
            "将移除队列中的全部任务：\n\n"
            "• 进行中 / 排队中的任务会被取消；\n"
            "• 已完成 / 失败的任务卡片也会被移除。\n\n"
            "此操作仅清空列表，已生成的输出文件不会删除。是否继续？"
        )
        if not ok:
            return
        # 记录被清任务的 id，避免其（因取消而延迟到达的）on_done 回调再次重建卡片
        self._cleared_ids = set(t.id for t in tasks)
        self.manager.clear()
        for card in self.cards.values():
            card._stop_pulse()
            card.destroy()
        self.cards.clear()
        self.log("task", "已清空任务队列")
        self.toast.show("已清空", "任务队列已全部移除", "info")
        self._refresh_stats()

    def retry_task(self, task):
        if not self.manager:
            return
        # 重新入队（相同参数）
        self.manager.add(task.kind, task.source, task.transcribe, label=task.label)

    def open_file(self, path):
        if path and os.path.exists(path):
            os.startfile(path)

    def open_task_dir(self, task):
        d = os.path.join(self.settings.output_dir,
                         {"xiaoyuzhou": "小宇宙", "bilibili": "B站视频", "local": "本地音频"}.get(task.kind, ""))
        if os.path.isdir(d):
            os.startfile(d)

    def open_output_dir(self):
        d = self.settings.output_dir
        os.makedirs(d, exist_ok=True)
        os.startfile(d)

    def change_output_dir(self):
        d = filedialog.askdirectory(initialdir=self.settings.output_dir, title="选择输出目录")
        if d:
            self.settings.set("output_dir", d)
            self.toast.show("已更新", f"输出目录：{d}", "info")

    # ----------------------------------------------------------- 设置
    def open_settings(self):
        s = ctk.CTkToplevel(self.root)
        s.title("设置")
        # 窗口可调整大小 + 可滚动，保证“保存”按钮永远可见、不被裁掉
        s.geometry("520x620")
        s.minsize(440, 420)
        s.resizable(True, True)
        s.attributes("-topmost", True)
        s.grid_columnconfigure(0, weight=1)
        s.grid_rowconfigure(1, weight=1)   # 中部滚动区自适应展开

        ctk.CTkLabel(s, text="设置", font=ctk.CTkFont(size=18, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="w", padx=24, pady=(16, 8))

        # 中部：可滚动内容区（字段多时滚动，不裁掉）
        scroll = ctk.CTkScrollableFrame(s, fg_color="transparent", corner_radius=0)
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        def field(parent, label, widget):
            ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=12),
                         text_color=WX_SUB, anchor="w").pack(anchor="w", padx=24, pady=(8, 2))
            widget.pack(fill="x", padx=24)

        # 输出目录
        out_var = ctk.StringVar(value=self.settings.output_dir)
        out_entry = ctk.CTkEntry(scroll, textvariable=out_var, font=ctk.CTkFont(size=12))
        field(scroll, "输出目录", out_entry)
        ctk.CTkButton(scroll, text="浏览", width=80, height=28,
                      command=lambda: out_var.set(filedialog.askdirectory() or out_var.get())).pack(anchor="e", padx=24, pady=(2, 0))

        # ASR 引擎
        eng_var = ctk.StringVar(value=self.settings.asr_engine)
        eng = ctk.CTkOptionMenu(scroll, values=["local", "openai"], variable=eng_var,
                                font=ctk.CTkFont(size=12))
        field(scroll, "语音识别引擎（local=本地离线 / openai=API）", eng)

        # 模型
        model_var = ctk.StringVar(value=self.settings.whisper_model)
        model = ctk.CTkOptionMenu(scroll, values=["small", "medium", "large-v3", "large-v3-turbo"],
                                  variable=model_var, font=ctk.CTkFont(size=12))
        field(scroll, "本地模型（越大越准越慢）", model)

        # OpenAI key
        key_var = ctk.StringVar(value=self.settings.openai_api_key)
        key = ctk.CTkEntry(scroll, textvariable=key_var, show="*", font=ctk.CTkFont(size=12))
        field(scroll, "OpenAI API Key（引擎选 openai 时必填）", key)

        # OpenAI model
        omodel_var = ctk.StringVar(value=self.settings.openai_model)
        omodel = ctk.CTkOptionMenu(scroll, values=["whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"],
                                   variable=omodel_var, font=ctk.CTkFont(size=12))
        field(scroll, "OpenAI 模型", omodel)

        # 并发
        conc_var = ctk.StringVar(value=str(self.settings.concurrent_tasks))
        conc = ctk.CTkOptionMenu(scroll, values=["1", "2", "3", "4"], variable=conc_var,
                                 font=ctk.CTkFont(size=12))
        field(scroll, "并发任务数", conc)

        # 主题
        theme_var = ctk.StringVar(value=self.settings.theme)
        theme = ctk.CTkOptionMenu(scroll, values=["light", "dark"], variable=theme_var,
                                  font=ctk.CTkFont(size=12))
        field(scroll, "界面主题", theme)

        ctk.CTkLabel(scroll, text="本地引擎首次使用会下载模型（medium≈1.5GB），请保持联网。",
                     font=ctk.CTkFont(size=10), text_color=WX_SUB, wraplength=420).pack(anchor="w", padx=24, pady=(10, 4))

        def save():
            # 1) 先把设置落盘——这一步最关键，必须确保执行
            try:
                self.settings.update({
                    "output_dir": out_var.get().strip(),
                    "asr_engine": eng_var.get(),
                    "whisper_model": model_var.get(),
                    "openai_api_key": key_var.get(),
                    "openai_model": omodel_var.get(),
                    "concurrent_tasks": int(conc_var.get()),
                    "theme": theme_var.get(),
                })
            except Exception as e:
                # 写盘失败要明明白白告诉用户（之前可能被弹窗一闪而过吞掉）
                messagebox.showerror(
                    "保存失败",
                    f"设置未能保存：\n{e}\n\n文件位置：\n{self.settings._PATH}\n\n"
                    "请检查该目录是否可写（是否被杀毒软件/系统权限拦截）。"
                )
                return
            # 2) 应用外观（即便后续步骤出错，设置也已落盘）
            try:
                ctk.set_appearance_mode(self.settings.theme)
            except Exception:
                pass
            # 3) 让已存在的任务管理器按新设置重建转写器
            #    （只清缓存、不重建队列，避免丢失已排队/进行中的任务）
            if getattr(self, "manager", None):
                self.manager._transcriber = None
            # 4) 明确、不可错过的成功反馈（弹窗 + 日志 + 提示，并显示落地路径）
            path = self.settings._PATH
            self.log("ok", f"设置已保存 → {path}")
            self.toast.show("已保存", f"输出目录：{os.path.basename(self.settings.output_dir)}", "info")
            messagebox.showinfo(
                "设置已保存",
                f"所有修改已成功写入磁盘。\n\n文件位置：\n{path}"
            )
            s.destroy()

        # 底部固定按钮栏（不随滚动消失，永远可见可点）
        bar = ctk.CTkFrame(s, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=24, pady=(10, 14))
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(bar, text="取消", width=120, height=38,
                      font=ctk.CTkFont(size=13),
                      fg_color="#F2F2F2", hover_color="#E5E5E5", text_color=WX_TEXT,
                      command=s.destroy).grid(row=0, column=0, padx=(0, 8), sticky="e")
        ctk.CTkButton(bar, text="保存", width=120, height=38,
                      font=ctk.CTkFont(size=13, weight="bold"),
                      fg_color=WX_GREEN, hover_color=WX_GREEN_HOVER, text_color="white",
                      command=save).grid(row=0, column=1, sticky="w")


if __name__ == "__main__":
    App()
