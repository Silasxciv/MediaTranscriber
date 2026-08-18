import sys, os, py_compile, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# 1) 语法编译
print("== 语法编译 ==")
ok = True
for f in ["main.py", "app/__init__.py", "app/config.py", "app/utils.py",
          "app/downloader.py", "app/asr.py", "app/tasks.py", "get_ffmpeg.py"]:
    try:
        py_compile.compile(os.path.join(ROOT, f), doraise=True)
        print("  OK ", f)
    except py_compile.PyCompileError as e:
        ok = False
        print("  FAIL", f, e)
assert ok, "语法错误"

# 2) 纯逻辑测试
print("== 纯逻辑 ==")
from app import utils
from app.downloader import parse_links, detect_source
from app.config import Settings, ensure_ffmpeg

assert utils.sanitize_filename('  The "Best" Show/02? *ok*') == "The Best Show 02 ok"
assert utils.sanitize_filename("") == "未命名"
assert utils.fmt_size(1536) == "1.5 KB"
assert utils.fmt_duration(125) == "02:05"

links = parse_links("https://www.xiaoyuzhoufm.com/episode/abc\nhttps://www.bilibili.com/video/BV1xx, https://b23.tv/xyz。")
assert len(links) == 3, links
assert detect_source("https://www.xiaoyuzhoufm.com/episode/abc") == "xiaoyuzhou"
assert detect_source("https://www.bilibili.com/video/BV1xx") == "bilibili"
assert detect_source("https://example.com") is None

# 3) 模块导入（不启动 GUI）
print("== 模块导入 ==")
import importlib
for m in ["app.config", "app.utils", "app.downloader", "app.asr", "app.tasks"]:
    importlib.import_module(m)
    print("  OK ", m)

# 4) ensure_ffmpeg 可调用（联网时会自动下载；此处仅校验接口，不触发下载）
print("== ensure_ffmpeg ==")
import inspect
assert callable(ensure_ffmpeg)
print("  接口 OK（无 ffmpeg 时会在用户机器首次运行自动下载）")

# 5) Settings 持久化
print("== Settings ==")
s = Settings()
s.set("whisper_model", "large-v3-turbo")
assert Settings().get("whisper_model") == "large-v3-turbo"
print("  设置读写 OK，输出目录:", s.output_dir)

print("\nALL SMOKE TESTS PASSED")
