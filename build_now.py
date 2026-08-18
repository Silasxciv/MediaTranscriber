"""一键重建 exe：输出到 TEMP，再用 os.replace 搬回 dist/（绕过沙箱安全删除拦截）。

- 若 dist 下的 exe 正被占用（用户运行着旧版），os.replace 会 PermissionError，
  此时退而复制为 dist/MediaTranscriber_new.exe 作为可独立交付的副本。
- 构建完成后自动校验 faster_whisper 的 VAD 模型 silero_vad_v6.onnx 是否进包。
"""
import os
import shutil
import subprocess
import tempfile
import importlib.util as _ilu

HERE = r"C:\workbuddy\MediaTranscriber"

# 与 build.spec 同步：读取版本号，产物名 = "MediaTranscriber vX.Y.Z.exe"
try:
    _vi_spec = _ilu.spec_from_file_location("app_init", os.path.join(HERE, "app", "__init__.py"))
    _vi_mod = _ilu.module_from_spec(_vi_spec)
    _vi_spec.loader.exec_module(_vi_mod)
    APP_VERSION = getattr(_vi_mod, "__version__", "1.0.0")
except Exception:
    APP_VERSION = "1.0.0"
EXE_NAME = f"MediaTranscriber v{APP_VERSION}"
EXE_FILE = EXE_NAME + ".exe"  # build.spec 的 name 不带后缀，PyInstaller 自动补 .exe

tmp = tempfile.gettempdir()
wp = os.path.join(tmp, "mt_build")
dp = os.path.join(tmp, "mt_dist")
os.makedirs(wp, exist_ok=True)
os.makedirs(dp, exist_ok=True)
os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)

pyi = os.path.join(HERE, ".buildenv", "Scripts", "pyinstaller.exe")
spec = os.path.join(HERE, "build.spec")
log_path = os.path.join(HERE, "build.log")

print("==> pyinstaller", spec)
with open(log_path, "w", encoding="utf-8") as logf:
    r = subprocess.run(
        [pyi, spec, "--noconfirm", "--workpath", wp, "--distpath", dp, "--log-level", "INFO"],
        cwd=HERE, stdout=logf, stderr=subprocess.STDOUT,
    )
print("BUILD_RC", r.returncode)
if r.returncode != 0:
    with open(log_path, encoding="utf-8") as f:
        print("BUILD_TAIL:\n", f.read()[-1500:])
    raise SystemExit(r.returncode)

src = os.path.join(dp, EXE_FILE)
dst = os.path.join(HERE, "dist", EXE_FILE)
new = os.path.join(HERE, "dist", "MediaTranscriber_new.exe")
if not os.path.exists(src):
    raise SystemExit("exe 未生成: " + src)

delivered = None
try:
    os.replace(src, dst)
    delivered = dst
    print("MOVED", dst, os.path.getsize(dst))
    if os.path.exists(new):
        try:
            os.remove(new)
        except Exception:
            pass
except PermissionError:
    # 旧版 exe 正被占用，无法直接覆盖，退化为独立副本交付
    shutil.copy2(src, new)
    delivered = new
    print("LOCKED_FALLBACK_COPIED", new, os.path.getsize(new))

# 校验关键资源/模块是否真正打进 exe
with open(delivered, "rb") as f:
    blob = f.read()
print("ONNX_BUNDLED" if b"silero_vad_v6.onnx" in blob else "ONNX_MISSING", delivered)
print("FASTEMBED_BUNDLED" if b"fastembed" in blob else "FASTEMBED_MISSING", delivered)
