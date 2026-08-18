# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：生成 Windows exe（内置 ffmpeg）。"""
import os

HERE = os.path.dirname(os.path.abspath(SPEC)) if "SPEC" in globals() else os.getcwd()
bin_dir = os.path.join(HERE, "bin")
# customtkinter 自带主题/字体/图标，需要 hook 一并收集，否则冻结后找不到资源会崩溃
hook_dir = os.path.join(HERE, "pyinstaller_hooks")

# faster_whisper 运行时从包内 assets 目录加载 silero_vad_v6.onnx（VAD 模型）。
# 该 .onnx 是非 py 资源，PyInstaller 默认不收集，必须显式打进 exe，否则冻结后
# 转写报 [ONNXRuntimeError] NO_SUCHFILE。hook 自动发现在此环境下不可靠，故显式收集。
fw_datas = []
try:
    import faster_whisper as _fw
    _fw_assets = os.path.join(os.path.dirname(_fw.__file__), "assets")
    if os.path.isdir(_fw_assets):
        fw_datas = [(os.path.join(_fw_assets, "*"), "faster_whisper/assets")]
except Exception as _e:
    print("WARN: faster_whisper assets 未打包:", _e)

a = Analysis(
    ["main.py"],
    pathex=[HERE],
    binaries=[],
    datas=([(os.path.join(bin_dir, "*"), "bin")] if os.path.isdir(bin_dir) else []) + fw_datas,
    hiddenimports=[
        "faster_whisper",
        "ctranslate2",
        "onnxruntime",
        "av",
        "customtkinter",
        "tkinter",
        "yt_dlp",
        "huggingface_hub",
        "tokenizers",
        "numpy",
        "requests",
        "PIL",
    ],
    hookspath=[hook_dir],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MediaTranscriber",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 不显示控制台黑窗
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
