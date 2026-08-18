@echo off
chcp 65001 >nul
REM ============================================================
REM  打包 MediaTranscriber 为单文件 Windows exe
REM
REM  重要：请用「自带 Tcl/Tk 的 Python」运行本脚本
REM  （官方 python.org 安装包，或 winget install Python.Python.3.12）。
REM  用不自带 Tcl/Tk 的精简 Python 打包，运行时会报
REM  "No module named 'tkinter'"。
REM ============================================================

setlocal
set VENV=.buildenv

if not exist "%VENV%\Scripts\python.exe" (
    echo [0/3] 创建虚拟环境（请确认当前 python 自带 Tcl/Tk）...
    python -m venv %VENV%
)

echo [1/3] 安装依赖...
call %VENV%\Scripts\pip install -r requirements.txt pyinstaller

echo [2/3] 打包 exe（ffmpeg 无需预置，首次运行会自动下载）...
call %VENV%\Scripts\pyinstaller build.spec --noconfirm

echo.
echo 完成：dist\MediaTranscriber.exe
echo 注意：本机若遇到 "No module named tkinter"，请改用带 Tcl/Tk 的 Python 重跑本脚本。
pause
