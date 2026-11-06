from io import BytesIO
import json
import unittest

from PIL import Image, ImageDraw

from src.core import TranslationError
from src.diagram import load_font, parse_regions, render_translation
from src.window import resized_bounds


def diagram_fixture():
    image = Image.new('RGB', (900, 360), 'white')
    draw = ImageDraw.Draw(image)
    font = load_font(26)
    draw.text((20, 15), 'Transformer architecture', font=load_font(30), fill='#19223A')
    labels = [('Input', '输入', 30, 205), ('Encoder', '编码器', 260, 465), ('Attention', '注意力', 520, 725)]
    regions = [dict(source='Transformer architecture', text='Transformer 模型结构', bbox=[20 / 900 * 1000, 15 / 360 * 1000, 500 / 900 * 1000, 57 / 360 * 1000])]
    for source, target, left, right in labels:
        draw.rounded_rectangle((left, 120, right, 230), radius=12, fill='#E6EDFF', outline='#526AE3', width=3)
        box = draw.textbbox((0, 0), source, font=font)
        width = box[2] - box[0]
        x = (left + right - width) // 2
        draw.text((x, 155), source, font=font, fill='#19223A')
        regions.append(dict(source=source, text=target, bbox=[(x - 3) / 900 * 1000, 153 / 360 * 1000, (x + width + 3) / 900 * 1000, 190 / 360 * 1000]))
    for left, right in [(205, 260), (465, 520)]:
        draw.line((left, 175, right - 7, 175), fill='#526AE3', width=3)
        draw.polygon([(right - 1, 175), (right - 11, 169), (right - 11, 181)], fill='#526AE3')
    draw.text((40, 290), 'y = f(x) + x', font=font, fill='#19223A')
    regions.append(dict(source='y = f(x) + x', text='y = f(x) + x', bbox=[40, 800, 350, 950]))
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue(), regions


class DiagramTests(unittest.TestCase):
    def test_parse_fenced_json_and_invalid_regions(self):
        _, regions = diagram_fixture()
        self.assertEqual(len(parse_regions('```json\n' + json.dumps({'regions': regions}) + '\n```')), 5)
        for box in ([0, 0, 1001, 20], [10, 10, 2, 20], [0, 0, float('nan'), 20], [0, 1, 2]):
            with self.assertRaises(TranslationError):
                parse_regions(json.dumps({'regions': [{'bbox': box, 'text': '翻译'}]}))
        for response in ['not json', '{}', '[]', '{"regions":null}']:
            with self.assertRaises(TranslationError):
                parse_regions(response)

    def test_graphics_and_formulas_remain_pixel_identical(self):
        data, regions = diagram_fixture()
        original, translated = render_translation(data, regions)
        self.assertEqual(original.size, translated.size)
        self.assertNotEqual(original.tobytes(), translated.tobytes())
        # Blue arrows, node borders, formula and background are outside text masks.
        for crop in [(205, 120, 260, 230), (465, 120, 520, 230), (30, 120, 205, 145), (0, 280, 900, 360)]:
            self.assertEqual(original.crop(crop).tobytes(), translated.crop(crop).tobytes())

    def test_no_text_and_dense_labels(self):
        data, _ = diagram_fixture()
        original, result = render_translation(data, [])
        self.assertEqual(original.tobytes(), result.tobytes())
        _, dense = render_translation(data, [{'bbox': [0, 0, 25, 25], 'text': '很长的目标语言标签' * 8}])
        self.assertEqual(dense.size, original.size)

    def test_resizing_west_north_and_minimum(self):
        self.assertEqual(resized_bounds((100, 100, 500, 700), -50, -30, 'nw', (380, 480)), (50, 70, 550, 730))
        self.assertEqual(resized_bounds((100, 100, 500, 700), 400, 600, 'nw', (380, 480)), (220, 320, 380, 480))
        self.assertEqual(resized_bounds((-100, 100, 500, 700), 50, 20, 'se', (380, 480)), (-100, 100, 550, 720))
