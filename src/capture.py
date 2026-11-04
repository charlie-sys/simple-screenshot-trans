"""Windows GDI screenshot capture, encoded as PNG without third-party packages."""
import ctypes
from ctypes import wintypes as w
import struct
import zlib


def dpi_aware():
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()


def desktop_bounds():
    user = ctypes.windll.user32
    return tuple(user.GetSystemMetrics(i) for i in (76, 77, 78, 79))


def encode_png(width, height, bgra):
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
    stride = width * 3
    raw = b''.join(b'\0' + rgb[y:y + stride] for y in range(0, len(rgb), stride))
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 4)) + chunk(b'IEND', b''))


class BitmapInfo(ctypes.Structure):
    _fields_ = [('size', w.DWORD), ('width', w.LONG), ('height', w.LONG),
                ('planes', w.WORD), ('bit_count', w.WORD), ('compression', w.DWORD),
                ('image_size', w.DWORD), ('xppm', w.LONG), ('yppm', w.LONG),
                ('colors', w.DWORD), ('important', w.DWORD), ('color', w.DWORD)]


def capture_region(x, y, width, height):
    if width < 3 or height < 3:
        raise ValueError('截图区域太小，请重新框选。')
    if width * height > 24_000_000:
        raise ValueError('截图区域过大，请缩小到 2400 万像素以内。')
    user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
    user.GetDC.argtypes, user.GetDC.restype = [w.HWND], w.HDC
    user.ReleaseDC.argtypes = [w.HWND, w.HDC]
    gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = [w.HDC], w.HDC
    gdi.CreateCompatibleBitmap.argtypes, gdi.CreateCompatibleBitmap.restype = [w.HDC, ctypes.c_int, ctypes.c_int], w.HBITMAP
    gdi.SelectObject.argtypes, gdi.SelectObject.restype = [w.HDC, w.HGDIOBJ], w.HGDIOBJ
    gdi.DeleteObject.argtypes = [w.HGDIOBJ]
    gdi.DeleteDC.argtypes = [w.HDC]
    gdi.BitBlt.argtypes = [w.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HDC, ctypes.c_int, ctypes.c_int, w.DWORD]
    gdi.GetDIBits.argtypes = [w.HDC, w.HBITMAP, w.UINT, w.UINT, ctypes.c_void_p, ctypes.POINTER(BitmapInfo), w.UINT]
    screen = user.GetDC(None)
    mem = gdi.CreateCompatibleDC(screen)
    bitmap = gdi.CreateCompatibleBitmap(screen, width, height)
    old = None
    try:
        if not screen or not mem or not bitmap:
            raise OSError('无法创建截图缓冲区。')
        old = gdi.SelectObject(mem, bitmap)
        if not gdi.BitBlt(mem, 0, 0, width, height, screen, x, y, 0x40CC0020):
            raise OSError('屏幕捕获失败。')
        gdi.SelectObject(mem, old)
        old = None
        info = BitmapInfo()
        info.size, info.width, info.height, info.planes, info.bit_count = 40, width, -height, 1, 32
        buffer = ctypes.create_string_buffer(width * height * 4)
        if gdi.GetDIBits(mem, bitmap, 0, height, buffer, ctypes.byref(info), 0) != height:
            raise OSError('无法读取截图。')
        return encode_png(width, height, buffer.raw)
    finally:
        if old:
            gdi.SelectObject(mem, old)
        if bitmap:
            gdi.DeleteObject(bitmap)
        if mem:
            gdi.DeleteDC(mem)
        if screen:
            user.ReleaseDC(None, screen)
