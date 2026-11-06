from io import BytesIO
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk


class ImageView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.original = None
        self.translated = None
        self.photo = None
        self.zoom = None
        self.redraw_timer = None
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        self.show_original = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text='原图', variable=self.show_original, command=self.redraw).pack(side='left')
        for text, action in [('适应', self.fit), ('−', lambda: self.change_zoom(.8)), ('+', lambda: self.change_zoom(1.25))]:
            ttk.Button(bar, text=text, width=4, command=action).pack(side='left', padx=2)
        ttk.Button(bar, text='导出 PNG', command=self.export).pack(side='right')
        container = ttk.Frame(self)
        container.pack(fill='both', expand=True)
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(container, bg='#E9EBF2', highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        horizontal = ttk.Scrollbar(container, orient='horizontal', command=self.canvas.xview)
        horizontal.grid(row=1, column=0, sticky='ew')
        vertical = ttk.Scrollbar(container, command=self.canvas.yview)
        vertical.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)
        self.canvas.bind('<Configure>', self.schedule_redraw)
        self.canvas.bind('<ButtonPress-1>', lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind('<B1-Motion>', lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind('<Control-MouseWheel>', lambda e: self.change_zoom(1.25 if e.delta > 0 else .8))
        self.note = tk.StringVar(value='截图后在这里显示原图和图片译文')
        ttk.Label(self, textvariable=self.note, wraplength=450).pack(fill='x', side='bottom', before=container)

    def set_images(self, original, translated=None):
        self.original, self.translated = original, translated
        self.zoom = None
        self.show_original.set(False)
        self.note.set('图片译文：保留图形，仅覆盖文字；可勾选原图核对。' if translated is not None else '原图 · 正在等待图片译文')
        self.redraw()

    def clear(self):
        self.original = self.translated = self.photo = None
        self.canvas.delete('all')
        self.note.set('截图后在这里显示原图和图片译文')

    def fit(self):
        self.zoom = None
        self.redraw()

    def change_zoom(self, factor):
        if self.original is not None:
            self.zoom = min(4, max(.05, self.current_scale() * factor))
            self.redraw()

    def current_scale(self):
        if self.zoom is not None:
            return self.zoom
        if self.original is None:
            return 1
        return min(max(1, self.canvas.winfo_width() - 12) / self.original.width,
                   max(1, self.canvas.winfo_height() - 12) / self.original.height, 1)

    def schedule_redraw(self, event=None):
        if self.redraw_timer:
            self.after_cancel(self.redraw_timer)
        self.redraw_timer = self.after(90, self.redraw)

    def redraw(self):
        if self.redraw_timer:
            self.after_cancel(self.redraw_timer)
            self.redraw_timer = None
        if self.original is None:
            return
        image = self.original if self.show_original.get() or self.translated is None else self.translated
        scale = self.current_scale()
        # Bound preview memory for very large captures. Export retains original resolution.
        scale = min(scale, (16_000_000 / (image.width * image.height)) ** .5)
        size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        self.photo = ImageTk.PhotoImage(image.resize(size, Image.Resampling.LANCZOS), master=self)
        self.canvas.delete('all')
        x, y = max(6, (self.canvas.winfo_width() - size[0]) // 2), max(6, (self.canvas.winfo_height() - size[1]) // 2)
        self.canvas.create_image(x, y, image=self.photo, anchor='nw')
        self.canvas.configure(scrollregion=(0, 0, size[0] + 12, size[1] + 12))

    def export(self):
        if self.translated is None:
            messagebox.showinfo('图片译文', '完成图片翻译后可导出 PNG。', parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, title='导出图片译文', defaultextension='.png',
                                          initialfile='translated-diagram.png', filetypes=[('PNG 图片', '*.png')])
        if path:
            try:
                self.translated.save(path, format='PNG')
            except OSError as exc:
                messagebox.showerror('导出失败', str(exc), parent=self)

    def load_capture(self, image_bytes):
        with Image.open(BytesIO(image_bytes)) as image:
            self.set_images(image.convert('RGB'))
