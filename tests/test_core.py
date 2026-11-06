import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
import zlib

from src.capture import encode_png, capture_region, dpi_aware, desktop_bounds
from src.core import ConfigStore, DEFAULTS, TranslationError, endpoint, translate
from src.diagram import parse_regions


class Handler(BaseHTTPRequestHandler):
    payload = None
    mode = 'ok'

    def log_message(self, *args):
        pass

    def do_POST(self):
        type(self).payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.send_response(401 if self.mode == 'unauthorized' else 200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        if self.mode == 'invalid':
            self.wfile.write(b'<html>bad gateway</html>')
        else:
            text = json.dumps({'regions': [{'bbox': [10, 20, 200, 100], 'source': 'Input', 'text': '输入'}]}) if self.mode == 'diagram' else '你好'
            self.wfile.write(json.dumps({'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]}).encode())


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Handler.mode = 'ok'
        self.config = dict(DEFAULTS, base_url=f'http://127.0.0.1:{self.server.server_port}/v1', model='test-vision', api_key='test-secret')

    def test_text_and_custom_language(self):
        self.config.update(source='English', target='日本語')
        self.assertEqual(translate(self.config, text='hello'), '你好')
        self.assertEqual(Handler.payload['messages'][1]['content'], 'hello')
        self.assertIn('日本語', Handler.payload['messages'][0]['content'])
        self.assertIn('English', Handler.payload['messages'][0]['content'])

    def test_image_request_and_auto_detection(self):
        translate(self.config, image=encode_png(1, 1, bytes([0, 0, 255, 255])))
        msg = Handler.payload['messages']
        self.assertIn('Automatically detect', msg[0]['content'])
        self.assertTrue(msg[1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,iVBOR'))

    def test_diagram_api_requests_coordinates_and_translation(self):
        Handler.mode = 'diagram'
        result = translate(self.config, image=encode_png(1, 1, bytes([0, 0, 255, 255])), diagram=True)
        self.assertEqual(parse_regions(result)[0]['text'], '输入')
        self.assertIn('0..1000', Handler.payload['messages'][0]['content'])
        self.assertIn('简体中文', Handler.payload['messages'][0]['content'])

    def test_error_responses(self):
        Handler.mode = 'unauthorized'
        with self.assertRaisesRegex(TranslationError, '401'):
            translate(self.config, text='hello')
        Handler.mode = 'invalid'
        with self.assertRaisesRegex(TranslationError, 'JSON'):
            translate(self.config, text='hello')

    def test_endpoint_validation(self):
        self.assertEqual(endpoint('https://example.org/v1/'), 'https://example.org/v1/chat/completions')
        self.assertEqual(endpoint('https://example.org/chat/completions'), 'https://example.org/chat/completions')
        for url in ['file:///tmp/a', 'http://remote.example/v1', 'https://example.org?key=secret', 'https://user:secret@example.org']:
            with self.assertRaises(ValueError):
                endpoint(url)

    def test_png_pixels_and_dimensions(self):
        png = encode_png(2, 1, bytes([0, 0, 255, 255, 255, 0, 0, 255]))
        self.assertEqual(struct.unpack('!II', png[16:24]), (2, 1))
        length = struct.unpack('!I', png[33:37])[0]
        self.assertEqual(zlib.decompress(png[41:41 + length]), b'\0\xff\0\0\0\0\xff')

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_key_is_encrypted_and_round_trips(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ConfigStore(Path(folder) / 'config.json')
            store.save(self.config)
            self.assertNotIn('test-secret', store.path.read_text(encoding='utf-8'))
            self.assertEqual(store.load()['api_key'], 'test-secret')
            self.config['api_key'] = ''
            store.save(self.config)
            self.assertEqual(store.load()['api_key'], '')

    def test_window_preferences_round_trip_and_legacy_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ConfigStore(Path(folder) / 'config.json')
            config = dict(DEFAULTS, opacity=60, window_width=640, window_height=800, image_mode=False)
            store.save(config)
            loaded = store.load()
            for key in ('opacity', 'window_width', 'window_height', 'image_mode'):
                self.assertEqual(loaded[key], config[key])
            store.path.write_text('{"source":"English","target":"简体中文"}', encoding='utf-8')
            self.assertEqual(store.load()['opacity'], 100)
            self.assertTrue(store.load()['image_mode'])

    @unittest.skipUnless(os.name == 'nt', 'Windows screen capture')
    def test_real_gdi_capture(self):
        dpi_aware()
        x, y, _, _ = desktop_bounds()
        png = capture_region(x, y, 32, 24)
        self.assertEqual(struct.unpack('!II', png[16:24]), (32, 24))
        with self.assertRaises(ValueError):
            capture_region(0, 0, 1, 1)


if __name__ == '__main__':
    unittest.main()
