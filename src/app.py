import ctypes
from ctypes import wintypes
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from .capture import capture_region, desktop_bounds, dpi_aware
from .core import ConfigStore, DEFAULTS, LANGUAGES, endpoint, translate

BG = '#F5F6FA'
WHITE = '#FFFFFF'
INK = '#20263A'
MUTED = '#7B8194'
ACCENT = '#5666E9'


def button(parent, text, command, primary=False, **kw):
    return tk.Button(parent, text=text, command=command, bg=ACCENT if primary else WHITE,
                     fg=WHITE if primary else INK, activebackground='#E5E8FF',
                     activeforeground=INK, relief='flat', bd=0, padx=12, pady=7,
                     cursor='hand2', font=('Microsoft YaHei UI', 10), **kw)


class Selector:
    def __init__(self, app):
        self.app = app
        self.origin = None
        self.rect = None
        self.closed = False
        x, y, width, height = desktop_bounds()
        self.offset = (x, y)
        self.win = tk.Toplevel(app.root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.attributes('-alpha', 0.28)
        self.win.geometry(f'{width}x{height}{x:+d}{y:+d}')
        # Tk interprets negative geometry positions as offsets from the right edge.
        # Move with Win32 coordinates for monitors left/above the primary display.
        self.win.update_idletasks()
        self.canvas = tk.Canvas(self.win, bg='#10172A', highlightthickness=0, cursor='crosshair')
        self.canvas.pack(fill='both', expand=True)
        self.canvas.create_text(width // 2, 55, text='拖动选择翻译区域  ·  Esc / 右键取消', fill='white', font=('Microsoft YaHei UI', 16))
        self.canvas.bind('<ButtonPress-1>', self.start)
        self.canvas.bind('<B1-Motion>', self.move)
        self.canvas.bind('<ButtonRelease-1>', self.finish)
        self.win.bind('<Escape>', lambda e: self.cancel())
        self.win.bind('<Button-3>', lambda e: self.cancel())
        self.win.deiconify()
        user = ctypes.windll.user32
        user.GetParent.argtypes, user.GetParent.restype = [wintypes.HWND], wintypes.HWND
        user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        handle = user.GetParent(self.win.winfo_id())
        user.SetWindowPos(handle, -1, x, y, width, height, 0x0040)
        self.win.lift()
        self.win.grab_set()
        self.win.focus_force()

    def start(self, event):
        self.origin = (event.x_root, event.y_root)
        if self.rect:
            self.canvas.delete(self.rect)
        x, y = event.x_root - self.offset[0], event.y_root - self.offset[1]
        self.rect = self.canvas.create_rectangle(x, y, x, y, outline='#A8C4FF', width=3, fill='#FFFFFF')

    def move(self, event):
        if self.origin:
            x, y = self.origin
            self.canvas.coords(self.rect, x - self.offset[0], y - self.offset[1],
                               event.x_root - self.offset[0], event.y_root - self.offset[1])

    def dismiss(self):
        self.closed = True
        self.win.grab_release()
        self.win.destroy()
        self.app.selector = None

    def cancel(self):
        if not self.closed:
            self.dismiss()
            self.app.restore()
            self.app.status.set('已取消截图')

    def finish(self, event):
        if not self.origin or self.closed:
            return
        x, y = self.origin
        region = (min(x, event.x_root), min(y, event.y_root), abs(x - event.x_root), abs(y - event.y_root))
        self.dismiss()
        # Let the compositor remove the selection overlay before capturing.
        self.app.root.after(160, lambda: self.app.capture(region))


class App:
    def __init__(self, root):
        self.root = root
        self.store = ConfigStore()
        warning = None
        try:
            self.config = self.store.load()
        except Exception:
            self.config = DEFAULTS.copy()
            warning = '配置读取失败，请重新填写设置。原配置文件未修改。'
        self.events = queue.Queue()
        self.busy = False
        self.job = 0
        self.image = None
        self.selector = None
        self.selecting = False
        self.settings_win = None
        self.compact = False
        self.ui_scale = root.winfo_fpixels('1i') / 96
        self.scaled = lambda value: round(value * self.ui_scale)
        self.normal_size = (self.scaled(460), self.scaled(650))
        self.drag = (0, 0)
        root.title('轻译 · Float Translate')
        root.geometry(f'{self.normal_size[0]}x{self.normal_size[1]}+160+120')
        root.minsize(self.scaled(380), self.scaled(550))
        root.overrideredirect(True)
        root.configure(bg=BG, highlightbackground='#DDE0EB', highlightthickness=1)
        root.attributes('-topmost', self.config['topmost'])
        root.after(100, self.show_in_taskbar)
        root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TCombobox', padding=6, fieldbackground=WHITE, background=WHITE, bordercolor='#E3E6EF')

        self.header = tk.Frame(root, bg=WHITE, height=48)
        self.header.pack(fill='x')
        self.title = tk.Label(self.header, text='◈  轻译', fg=ACCENT, bg=WHITE, font=('Microsoft YaHei UI', 13, 'bold'), padx=14)
        self.title.pack(side='left', pady=9)
        self.header.bind('<ButtonPress-1>', self.drag_start)
        self.header.bind('<B1-Motion>', self.drag_move)
        self.title.bind('<ButtonPress-1>', self.drag_start)
        self.title.bind('<B1-Motion>', self.drag_move)
        button(self.header, '×', self.close).pack(side='right')
        self.collapse_btn = button(self.header, '−', self.toggle_compact)
        self.collapse_btn.pack(side='right')
        button(self.header, '设置', self.settings).pack(side='right')
        self.mini_capture = button(self.header, '截图', self.screenshot, primary=True)

        self.body = tk.Frame(root, bg=BG, padx=18, pady=15)
        self.body.pack(fill='both', expand=True)
        row = tk.Frame(self.body, bg=BG)
        row.pack(fill='x')
        self.source = tk.StringVar(value=self.config['source'])
        self.target = tk.StringVar(value=self.config['target'])
        self.source_box = ttk.Combobox(row, textvariable=self.source, values=['自动识别'] + LANGUAGES, width=13)
        self.source_box.pack(side='left', fill='x', expand=True)
        button(row, '⇄', self.swap).pack(side='left', padx=5)
        self.target_box = ttk.Combobox(row, textvariable=self.target, values=LANGUAGES, width=13)
        self.target_box.pack(side='left', fill='x', expand=True)
        tk.Label(self.body, text='原文', bg=BG, fg=MUTED, anchor='w').pack(fill='x', pady=(17, 6))
        input_card = tk.Frame(self.body, bg=WHITE, padx=11, pady=9)
        input_card.pack(fill='both', expand=True)
        self.input = tk.Text(input_card, height=5, wrap='word', bg=WHITE, fg=INK, insertbackground=ACCENT,
                             relief='flat', undo=True, font=('Microsoft YaHei UI', 11), spacing3=5)
        self.input.pack(fill='both', expand=True)
        self.input.bind('<Control-Return>', lambda e: self.run_text())
        self.image_note = tk.StringVar(value='输入文字，或框选屏幕中的内容')
        tk.Label(input_card, textvariable=self.image_note, bg=WHITE, fg=MUTED, anchor='w', font=('Microsoft YaHei UI', 9)).pack(fill='x', pady=(5, 0))
        actions = tk.Frame(self.body, bg=BG)
        actions.pack(fill='x', pady=12)
        self.capture_btn = button(actions, '框选截图', self.screenshot)
        self.capture_btn.pack(side='left')
        button(actions, '清空', self.clear).pack(side='left', padx=6)
        self.translate_btn = button(actions, '翻译  ↵', self.run_current, primary=True)
        self.translate_btn.pack(side='right')
        result_header = tk.Frame(self.body, bg=BG)
        result_header.pack(fill='x')
        tk.Label(result_header, text='译文', bg=BG, fg=MUTED).pack(side='left')
        button(result_header, '复制', self.copy).pack(side='right')
        output_card = tk.Frame(self.body, bg=WHITE, padx=11, pady=9)
        output_card.pack(fill='both', expand=True, pady=(5, 0))
        self.output = tk.Text(output_card, height=7, wrap='word', bg=WHITE, fg=INK, relief='flat',
                              state='disabled', font=('Microsoft YaHei UI', 11), spacing3=6)
        scroll = ttk.Scrollbar(output_card, command=self.output.yview)
        scroll.pack(side='right', fill='y')
        self.output.configure(yscrollcommand=scroll.set)
        self.output.pack(fill='both', expand=True)
        self.footer = tk.Frame(root, bg=BG)
        self.footer.pack(fill='x', padx=18, pady=(0, 10))
        self.status = tk.StringVar(value='就绪 · Ctrl+Enter 翻译')
        tk.Label(self.footer, textvariable=self.status, bg=BG, fg=MUTED, anchor='w', font=('Microsoft YaHei UI', 9)).pack(side='left', fill='x', expand=True)
        grip = tk.Label(self.footer, text='◢', bg=BG, fg=MUTED, cursor='sizing')
        grip.pack(side='right')
        grip.bind('<ButtonPress-1>', self.resize_start)
        grip.bind('<B1-Motion>', self.resize)
        root.bind('<Escape>', lambda e: self.cancel_job())
        self.hotkeys = []
        user = ctypes.windll.user32
        for ident, key in ((1, 0x41), (2, 0x54)):
            if user.RegisterHotKey(None, ident, 0x4003, key):
                self.hotkeys.append(ident)
        self.root.after(100, self.poll)
        if len(self.hotkeys) != 2:
            self.status.set('部分快捷键被占用，请使用窗口按钮')
        if warning:
            root.after(300, lambda: messagebox.showwarning('配置提示', warning, parent=root))
        elif not self.config['model']:
            root.after(400, self.settings)

    def show_in_taskbar(self):
        user = ctypes.windll.user32
        user.GetParent.argtypes, user.GetParent.restype = [wintypes.HWND], wintypes.HWND
        getter = user.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user.GetWindowLongW
        setter = user.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user.SetWindowLongW
        getter.argtypes, getter.restype = [wintypes.HWND, ctypes.c_int], ctypes.c_ssize_t
        setter.argtypes, setter.restype = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t
        handle = user.GetParent(self.root.winfo_id())
        setter(handle, -20, (getter(handle, -20) & ~0x80) | 0x40000)
        # Remap so Explorer notices the changed extended window style.
        self.root.withdraw()
        self.root.deiconify()

    def drag_start(self, event):
        self.drag = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def drag_move(self, event):
        user = ctypes.windll.user32
        user.GetParent.argtypes, user.GetParent.restype = [wintypes.HWND], wintypes.HWND
        user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user.SetWindowPos(user.GetParent(self.root.winfo_id()), None,
                          event.x_root - self.drag[0], event.y_root - self.drag[1], 0, 0, 0x0015)

    def resize_start(self, event):
        self.resize_origin = (event.x_root, event.y_root, self.root.winfo_width(), self.root.winfo_height())

    def resize(self, event):
        x, y, width, height = self.resize_origin
        self.root.geometry(f'{max(self.scaled(380), width + event.x_root - x)}x{max(self.scaled(550), height + event.y_root - y)}')

    def toggle_compact(self):
        self.compact = not self.compact
        if self.compact:
            self.normal_size = (self.root.winfo_width(), self.root.winfo_height())
            self.body.pack_forget()
            self.footer.pack_forget()
            self.root.minsize(self.scaled(310), self.scaled(48))
            self.root.geometry(f'{self.scaled(310)}x{self.scaled(48)}')
            self.mini_capture.pack(side='right', padx=4)
            self.collapse_btn.configure(text='□')
        else:
            self.mini_capture.pack_forget()
            self.root.minsize(self.scaled(380), self.scaled(550))
            self.root.geometry(f'{self.normal_size[0]}x{self.normal_size[1]}')
            self.body.pack(fill='both', expand=True)
            self.footer.pack(fill='x', padx=18, pady=(0, 10))
            self.collapse_btn.configure(text='−')

    def restore(self):
        self.root.deiconify()
        self.root.lift()

    def expand(self):
        if self.selector:
            return
        if self.compact:
            self.toggle_compact()
        self.restore()
        self.input.focus_set()

    def swap(self):
        if self.source.get() == '自动识别':
            self.status.set('先指定源语言，再交换语言')
            return
        src, dst = self.source.get(), self.target.get()
        self.source.set(dst)
        self.target.set(src)

    def active_config(self):
        config = dict(self.config, source=self.source.get().strip(), target=self.target.get().strip())
        if not config['source'] or not config['target'] or config['target'] == '自动识别':
            raise ValueError('请填写源语言和明确的目标语言。')
        endpoint(config['base_url'])
        if not config['model'].strip():
            raise ValueError('请先在设置中填写视觉模型名称。')
        return config

    def screenshot(self):
        if self.busy or self.selector or self.selecting:
            return
        if self.settings_win and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return
        try:
            self.active_config()
        except ValueError as exc:
            self.status.set(str(exc))
            self.settings()
            return
        self.selecting = True
        self.root.withdraw()
        self.root.after(180, self.open_selector)

    def open_selector(self):
        try:
            self.selector = Selector(self)
        except Exception as exc:
            self.restore()
            self.status.set('无法打开截图选区：' + str(exc))
        finally:
            self.selecting = False

    def capture(self, region):
        try:
            self.image = capture_region(*region)
            self.input.delete('1.0', 'end')
            self.image_note.set(f'已选截图 {region[2]} × {region[3]} · 输入文字可切回文字翻译')
        except Exception as exc:
            self.restore()
            self.status.set(str(exc))
            return
        self.expand()
        self.start(image=self.image)

    def run_text(self):
        self.start(text=self.input.get('1.0', 'end'))
        return 'break'

    def run_current(self):
        text = self.input.get('1.0', 'end').strip()
        self.start(text=text, image=self.image if not text else None)

    def start(self, text='', image=None):
        if self.busy:
            return
        try:
            config = self.active_config()
            if not text.strip() and image is None:
                raise ValueError('请输入文字或框选截图。')
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.job += 1
        ident = self.job
        self.set_busy(True)
        self.status.set('正在翻译… · Esc 取消等待')
        self.set_output('')
        def worker():
            try:
                result = translate(config, text=text, image=image)
                self.events.put((ident, True, result))
            except Exception as exc:
                self.events.put((ident, False, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def set_busy(self, value):
        self.busy = value
        self.translate_btn.configure(state='disabled' if value else 'normal', text='翻译中…' if value else '翻译  ↵')
        self.capture_btn.configure(state='disabled' if value else 'normal')

    def cancel_job(self):
        if self.busy:
            self.job += 1
            self.set_busy(False)
            self.status.set('已取消等待；服务端请求可能仍在处理')

    def poll(self):
        try:
            while True:
                ident, ok, result = self.events.get_nowait()
                if ident != self.job:
                    continue
                self.set_busy(False)
                if ok:
                    self.set_output(result)
                    self.status.set('翻译完成')
                else:
                    self.status.set('翻译失败 · 可重试')
                    self.set_output(result)
        except queue.Empty:
            pass
        msg = wintypes.MSG()
        while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0x0312, 0x0312, 1):
            if msg.wParam == 1:
                self.screenshot()
            elif msg.wParam == 2:
                self.expand()
        self.root.after(80, self.poll)

    def set_output(self, text):
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', text)
        self.output.configure(state='disabled')

    def copy(self):
        text = self.output.get('1.0', 'end').strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.status.set('译文已复制')

    def clear(self):
        self.cancel_job()
        self.image = None
        self.input.delete('1.0', 'end')
        self.set_output('')
        self.image_note.set('输入文字，或框选屏幕中的内容')
        self.status.set('已清空')

    def settings(self):
        if self.selector:
            return
        if self.settings_win and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return
        win = self.settings_win = tk.Toplevel(self.root)
        win.title('轻译 · 模型设置')
        win.configure(bg=BG)
        win.geometry('490x550')
        win.resizable(False, False)
        win.attributes('-topmost', True)
        frame = tk.Frame(win, bg=BG, padx=24, pady=20)
        frame.pack(fill='both', expand=True)
        tk.Label(frame, text='连接你的视觉模型', bg=BG, fg=INK, font=('Microsoft YaHei UI', 16, 'bold')).pack(anchor='w')
        tk.Label(frame, text='使用 OpenAI 兼容的 Chat Completions 接口', bg=BG, fg=MUTED).pack(anchor='w', pady=(4, 15))
        entries = {}
        for key, label in [('base_url', '接口地址（Base URL 或完整请求地址）'), ('model', '模型名称（需支持图片输入）'), ('api_key', 'API Key（本地服务可留空）'), ('timeout', '请求超时（5–300 秒）')]:
            tk.Label(frame, text=label, bg=BG, fg=INK).pack(anchor='w', pady=(8, 5))
            var = tk.StringVar(value=str(self.config[key]))
            entry = ttk.Entry(frame, textvariable=var, show='●' if key == 'api_key' else '')
            entry.pack(fill='x', ipady=4)
            entries[key] = var
        topmost = tk.BooleanVar(value=self.config['topmost'])
        tk.Checkbutton(frame, text='窗口始终置顶', variable=topmost, bg=BG, activebackground=BG).pack(anchor='w', pady=(12, 4))
        tk.Label(frame, text='Ctrl+Alt+A  截图    ·    Ctrl+Alt+T  展开窗口\n截图仅保留在内存，翻译时发送至所配置的接口。\n密钥通过 Windows DPAPI 加密，仅当前 Windows 用户可解密。',
                 bg=BG, fg=MUTED, justify='left', font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=8)
        def save():
            try:
                config = dict(self.config)
                for key, var in entries.items():
                    config[key] = var.get().strip()
                endpoint(config['base_url'])
                config['timeout'] = int(config['timeout'])
                if not 5 <= config['timeout'] <= 300:
                    raise ValueError('超时应为 5–300 秒。')
                if not config['model']:
                    raise ValueError('请填写模型名称。')
                config.update(topmost=topmost.get(), source=self.source.get(), target=self.target.get())
                self.store.save(config)
                self.config = config
                self.root.attributes('-topmost', config['topmost'])
                self.status.set('设置已保存')
                win.destroy()
            except Exception as exc:
                messagebox.showerror('无法保存', str(exc), parent=win)
        button(frame, '保存设置', save, primary=True).pack(anchor='e', pady=(6, 0))
        win.update_idletasks()
        # Derive size from font metrics, including Windows text/DPI scaling.
        win.geometry(f'{max(490, frame.winfo_reqwidth())}x{frame.winfo_reqheight()}')

    def close(self):
        try:
            # Do not overwrite a damaged config merely by closing the app.
            if self.config.get('model'):
                self.config.update(source=self.source.get(), target=self.target.get())
                self.store.save(self.config)
        except Exception as exc:
            messagebox.showerror('配置保存失败', str(exc), parent=self.root)
            return
        for ident in self.hotkeys:
            ctypes.windll.user32.UnregisterHotKey(None, ident)
        for timer in self.root.tk.call('after', 'info'):
            self.root.after_cancel(timer)
        self.root.destroy()


def main():
    dpi_aware()
    root = tk.Tk()
    App(root)
    root.mainloop()
