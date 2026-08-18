# -*- mode: python ; coding: utf-8 -*-
"""确保 customtkinter 的主题/字体/图标等 assets 一并被打进 exe。

否则冻结后的程序在启动时 import customtkinter 会因找不到资源而崩溃。
"""
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("customtkinter")
