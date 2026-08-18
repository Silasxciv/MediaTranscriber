"""无显示环境下的初始化体检：用桩替换 customtkinter / tkinter 控件，真实执行
App.__init__ 的全部流程（含新增的日志面板），确认无属性/方法错误。仅用于开发验证。"""
import sys
import types


class Dummy:
    """万能桩：任何属性访问/调用都返回自身；数值运算返回 0；字符串返回 ''。"""
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        if name in ("winfo_screenwidth", "winfo_screenheight",
                    "winfo_width", "winfo_height", "winfo_x", "winfo_y"):
            return lambda *a: 1200
        if name in ("get", "get_string"):
            return lambda *a: ""
        return Dummy()

    def __setattr__(self, n, v):
        pass

    def __call__(self, *a, **k):
        return Dummy()

    def __sub__(self, o):
        return 0

    def __add__(self, o):
        return 0

    def __mul__(self, o):
        return 0

    def __floordiv__(self, o):
        return 0

    def __truediv__(self, o):
        return 0

    def __radd__(self, o):
        return 0

    def __int__(self):
        return 0

    def __str__(self):
        return ""

    def __bool__(self):
        return False


# ---- 桩：customtkinter ----
import customtkinter as ctk

for _name in ("CTk", "CTkFrame", "CTkLabel", "CTkButton", "CTkFont",
              "CTkToplevel", "CTkOptionMenu", "StringVar", "CTkEntry",
              "CTkTextbox", "CTkCheckBox", "CTkScrollableFrame", "CTkTabview"):
    setattr(ctk, _name, Dummy)
ctk.set_appearance_mode = lambda *a, **k: None
ctk.set_default_color_theme = lambda *a, **k: None

# ---- 桩：tkinter + 子模块 ----
tk_mod = types.ModuleType("tkinter")


class FakeText:
    def __init__(self, *a, **k):
        pass

    def configure(self, *a, **k):
        pass

    def insert(self, *a, **k):
        pass

    def tag_add(self, *a, **k):
        pass

    def tag_config(self, *a, **k):
        pass

    def see(self, *a, **k):
        pass

    def delete(self, *a, **k):
        pass

    def index(self, *a, **k):
        return "1.0"

    def pack(self, *a, **k):
        pass

    def pack_forget(self, *a, **k):
        pass


tk_mod.Text = FakeText
tk_mod.Tk = Dummy
tk_mod.PhotoImage = Dummy
font_mod = types.ModuleType("tkinter.font")
font_mod.Font = Dummy

fd_mod = types.ModuleType("tkinter.filedialog")
fd_mod.askopenfilenames = lambda *a, **k: ()
fd_mod.askdirectory = lambda *a, **k: ""
mb_mod = types.ModuleType("tkinter.messagebox")
mb_mod.showinfo = mb_mod.showerror = mb_mod.askyesno = lambda *a, **k: None

tk_mod.filedialog = fd_mod
tk_mod.messagebox = mb_mod
sys.modules["tkinter"] = tk_mod
sys.modules["tkinter.font"] = font_mod
sys.modules["tkinter.filedialog"] = fd_mod
sys.modules["tkinter.messagebox"] = mb_mod

# ---- 真实主流程 ----
import main

# 绕过网络：让环境准备直接返回一个假 ffmpeg 路径
main.ensure_ffmpeg = lambda *a, **k: "fake_ffmpeg.exe"


if __name__ == "__main__":
    try:
        app = main.App()
        # 给后台准备线程一点时间跑完（它会走 log -> after(0)）
        import time as _t
        _t.sleep(0.3)
        # 触发一次日志，确认 LogPanel 写入链路无异常
        app.log("info", "体检探针：日志写入正常")
        print("INIT_PASS: App.__init__ 完整执行，日志面板与初始化流程无属性/方法错误")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("INIT_FAIL:", type(e).__name__, e)
        sys.exit(1)
