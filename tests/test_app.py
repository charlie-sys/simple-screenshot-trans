"""Native Tk smoke tests without remote services or persistent user settings."""
import os
import tempfile
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import patch

from src.capture import dpi_aware
from src.core import ConfigStore, DEFAULTS
from src.app import App, Selector


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


if __name__ == '__main__':
    unittest.main()
