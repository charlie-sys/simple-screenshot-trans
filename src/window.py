"""Small Win32 helpers for a borderless, resizable reading window."""
import ctypes
from ctypes import wintypes as w


def resized_bounds(bounds, dx, dy, edges, minimum):
    x, y, width, height = bounds
    min_width, min_height = minimum
    if 'e' in edges:
        width = max(min_width, width + dx)
    if 's' in edges:
        height = max(min_height, height + dy)
    if 'w' in edges:
        new_width = max(min_width, width - dx)
        x += width - new_width
        width = new_width
    if 'n' in edges:
        new_height = max(min_height, height - dy)
        y += height - new_height
        height = new_height
    return x, y, width, height


def window_handle(widget):
    user = ctypes.windll.user32
    user.GetParent.argtypes, user.GetParent.restype = [w.HWND], w.HWND
    return user.GetParent(widget.winfo_id())


def set_bounds(widget, bounds):
    user = ctypes.windll.user32
    user.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT]
    user.SetWindowPos(window_handle(widget), None, *bounds, 0x0014)


def mouse_passthrough(widget, enabled):
    user = ctypes.windll.user32
    getter = user.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user.GetWindowLongW
    setter = user.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user.SetWindowLongW
    getter.argtypes, getter.restype = [w.HWND, ctypes.c_int], ctypes.c_ssize_t
    setter.argtypes, setter.restype = [w.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t
    handle = window_handle(widget)
    flags = getter(handle, -20)
    flags = flags | 0x80020 if enabled else flags & ~0x20
    setter(handle, -20, flags)
