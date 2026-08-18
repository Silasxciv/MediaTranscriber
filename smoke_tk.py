import tkinter
import customtkinter

# 仅验证冻结后能否正常 import tkinter / customtkinter 及 Tcl/Tk 资源是否就位
print("TK_SMOKE_OK", tkinter.TkVersion, customtkinter.__version__)
