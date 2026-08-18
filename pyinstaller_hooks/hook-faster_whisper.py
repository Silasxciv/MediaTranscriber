# -*- mode: python ; coding: utf-8 -*-
"""收集 faster_whisper 的数据文件（assets/*.onnx 等 VAD 模型）。

faster_whisper 运行时从包内 `assets/` 目录加载 silero_vad_v6.onnx，
PyInstaller 默认只收集 .py，不收集这些非 py 资源，导致冻结后运行报
[ONNXRuntimeError] NO_SUCHFILE。用 collect_data_files 把整个 assets 打进 exe。
"""
from PyInstaller.utils.hooks import collect_data_files

datas = collect_data_files("faster_whisper", include_py_files=False)
