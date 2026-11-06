"""Native Tk smoke tests without remote services or persistent user settings."""
import os
import ctypes
import tempfile
from pathlib import Path
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.capture import dpi_aware
from src.core import ConfigStore, DEFAULTS
from src.app import App, Selector
from test_diagram import diagram_fixture
from src.diagram import render_translation
from src.window import window_handle, mouse_passthrough


@unittest.skipUnless(os.name == 'nt', 'Windows native app')
class AppTests(unittest.TestCase):
    def setUp(self):
        dpi_aware()
        self.temp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.temp.name) / 'config.json')
        store.save(dict(DEFAULTS, model='test-vision'))
        self.root = tk.Tk()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        with patch('src.app.ConfigStore', return_value=store):
            self.app = App(self.root)
        self.root.update()

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_compact_expand_and_language_swap(self):
        self.app.toggle_compact()
        self.root.update()
        self.assertFalse(self.app.body.winfo_ismapped())
        self.app.expand()
        self.root.update()
        self.assertTrue(self.app.body.winfo_ismapped())
        self.app.source.set('English')
        self.app.target.set('日本語')
        self.app.swap()
        self.assertEqual(self.app.source.get(), '日本語')
        self.assertEqual(self.app.target.get(), 'English')
        self.assertFalse(self.errors)

    def test_settings_save_button_is_visible(self):
        self.app.settings()
        self.root.update()
        win = self.app.settings_win
        frame = win.winfo_children()[0]
        save = frame.winfo_children()[-1]
        self.assertTrue(save.winfo_ismapped())
        self.assertLessEqual(save.winfo_y() + save.winfo_height(), frame.winfo_height())
        win.destroy()
        self.assertFalse(self.errors)

    def test_selection_cancel_and_stale_result(self):
        self.app.selector = Selector(self.app)
        self.root.update()
        self.app.selector.cancel()
        self.assertIsNone(self.app.selector)
        self.app.job = 3
        self.app.set_busy(True)
        self.app.cancel_job()
        self.app.events.put((3, True, 'obsolete'))
        self.app.poll()
        self.assertEqual(self.app.output.get('1.0', 'end').strip(), '')
        self.assertFalse(self.app.busy)
        self.assertFalse(self.errors)

    def test_opacity_and_resize(self):
        self.app.opacity.set(55)
        self.app.apply_opacity()
        self.assertAlmostEqual(self.root.attributes('-alpha'), .55, places=2)
        self.app.resize_start(SimpleNamespace(x_root=100, y_root=100))
        old_width = self.root.winfo_width()
        self.app.resize(SimpleNamespace(x_root=240, y_root=160))
        self.root.update()
        self.assertEqual(self.root.winfo_width(), old_width + 140)
        self.assertEqual(len(self.app.resize_handles), 8)
        self.root.geometry(f'{self.app.scaled(380)}x{self.app.scaled(480)}')
        self.root.update()
        self.assertTrue(self.app.footer.winfo_ismapped())
        self.assertGreater(self.app.results.winfo_height(), 30)
        self.assertFalse(self.errors)

    def test_diagram_result_preview_and_clear(self):
        data, regions = diagram_fixture()
        original, translated = render_translation(data, regions)
        self.app.image_view.load_capture(data)
        self.app.results.select(self.app.image_view)
        self.app.events.put((self.app.job, True, dict(text='输入 / 编码器', original=original, translated=translated, count=5)))
        self.app.poll()
        self.root.update()
        self.assertIsNotNone(self.app.image_view.photo)
        self.assertIsNotNone(self.app.image_view.translated)
        self.assertIn('编码器', self.app.output.get('1.0', 'end'))
        self.app.image_view.show_original.set(True)
        self.app.image_view.redraw()
        self.app.image_view.change_zoom(1.25)
        export_path = Path(self.temp.name) / 'translated.png'
        with patch('src.image_view.filedialog.asksaveasfilename', return_value=str(export_path)):
            self.app.image_view.export()
        self.assertTrue(export_path.read_bytes().startswith(b'\x89PNG'))
        self.app.clear()
        self.assertIsNone(self.app.image_view.translated)
        self.assertFalse(self.errors)

    def test_native_passthrough_flag_and_recovery(self):
        user = ctypes.windll.user32
        getter = user.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user.GetWindowLongW
        getter.restype = ctypes.c_ssize_t
        mouse_passthrough(self.root, True)
        try:
            self.assertTrue(getter(window_handle(self.root), -20) & 0x20)
        finally:
            mouse_passthrough(self.root, False)
        self.assertFalse(getter(window_handle(self.root), -20) & 0x20)


if __name__ == '__main__':
    unittest.main()
