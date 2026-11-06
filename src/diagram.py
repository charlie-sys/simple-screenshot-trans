"""Translate image labels without regenerating the original diagram."""
from collections import Counter
from io import BytesIO
import json
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .core import TranslationError


def parse_regions(response):
    response = response.strip()
    if response.startswith('```') and response.endswith('```'):
        response = response.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    try:
        data = json.loads(response)
        regions = data['regions']
        if not isinstance(regions, list) or len(regions) > 300:
            raise ValueError()
        validated = []
        for region in regions:
            box, text = region['bbox'], region['text']
            if (not isinstance(box, list) or len(box) != 4 or
                    not all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1000 for v in box) or
                    box[2] <= box[0] or box[3] <= box[1] or
                    not isinstance(text, str) or not text.strip() or len(text) > 4000):
                raise ValueError()
            source = region.get('source', '')
            if not isinstance(source, str):
                raise ValueError()
            validated.append(dict(bbox=box, text=text.strip(), source=source))
        return validated
    except (ValueError, TypeError, KeyError):
        raise TranslationError('模型未返回有效的文字坐标。请重试、缩小截图，或关闭“图片译文”使用文字翻译。') from None


def load_font(size):
    fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    for name in ('msyh.ttc', 'msgothic.ttc', 'malgun.ttf', 'arial.ttf'):
        path = fonts / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    raise TranslationError('找不到系统字体，请安装 Microsoft YaHei 字体。')


def wrap_text(text, font, width):
    lines = []
    for paragraph in text.split('\n'):
        current = ''
        for char in paragraph:
            if current and font.getlength(current + char) > width:
                lines.append(current.rstrip())
                current = char.lstrip()
            else:
                current += char
        lines.append(current.rstrip())
    return '\n'.join(lines)


def label_patch(text, size, background):
    width, height = size
    draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    chosen = None
    # Binary search actual ink bounds; supports Chinese and Latin labels.
    low, high = 5, min(96, max(5, height))
    while low <= high:
        mid = (low + high) // 2
        font = load_font(mid)
        wrapped = wrap_text(text, font, max(1, width - 2))
        box = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=1, align='center')
        if box[2] - box[0] <= width - 2 and box[3] - box[1] <= height - 2:
            chosen = (font, wrapped, box)
            low = mid + 1
        else:
            high = mid - 1
    if chosen is None:
        font = load_font(5)
        wrapped = wrap_text(text, font, max(4, width - 2))
        box = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=1, align='center')
        chosen = (font, wrapped, box)
    font, wrapped, box = chosen
    ink_w, ink_h = max(1, box[2] - box[0]), max(1, box[3] - box[1])
    patch = Image.new('RGB', (max(width, ink_w + 2), max(height, ink_h + 2)), background)
    brightness = sum(c * weight for c, weight in zip(background, (.299, .587, .114)))
    color = '#171B29' if brightness > 140 else '#FFFFFF'
    ImageDraw.Draw(patch).multiline_text(((patch.width - ink_w) / 2 - box[0],
                                        (patch.height - ink_h) / 2 - box[1]),
                                       wrapped, font=font, fill=color, spacing=1, align='center')
    if patch.size != size:
        patch = patch.resize(size, Image.Resampling.LANCZOS)
    return patch


def render_translation(image_bytes, regions):
    with Image.open(BytesIO(image_bytes)) as image:
        original = image.convert('RGB')
    result = original.copy()
    for region in regions:
        # Preserve labels already in the requested language, including formulas.
        if region['text'] == region.get('source'):
            continue
        left, top, right, bottom = region['bbox']
        x0, y0 = int(left * original.width / 1000), int(top * original.height / 1000)
        x1, y1 = min(original.width, math.ceil(right * original.width / 1000)), min(original.height, math.ceil(bottom * original.height / 1000))
        width, height = x1 - x0, y1 - y0
        if width < 2 or height < 2:
            continue
        # Sample the inside edge of the ORIGINAL label area, usually blank fill.
        crop = original.crop((x0, y0, x1, y1))
        pixels = [crop.getpixel((x, y)) for x in range(0, width, max(1, width // 80)) for y in (0, height - 1)]
        pixels += [crop.getpixel((x, y)) for y in range(0, height, max(1, height // 80)) for x in (0, width - 1)]
        background = Counter(pixels).most_common(1)[0][0]
        result.paste(label_patch(region['text'], (width, height), background), (x0, y0))
    return original, result
