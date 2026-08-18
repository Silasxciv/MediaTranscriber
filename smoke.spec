# -*- mode: python ; coding: utf-8 -*-
"""轻量验证：仅打包 tkinter + customtkinter，headless 运行确认 Tcl/Tk 资源就位。"""
import os

HERE = os.path.dirname(os.path.abspath(SPEC)) if "SPEC" in globals() else os.getcwd()
hook_dir = os.path.join(HERE, "pyinstaller_hooks")

a = Analysis(
    ["smoke_tk.py"],
    pathex=[HERE],
    binaries=[],
    datas=[],
    hiddenimports=["customtkinter", "tkinter"],
    hookspath=[hook_dir],
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
    name="smoke_tk",
    debug=False,
    console=True,
    upx=False,
)
