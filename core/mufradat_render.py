"""Рендер арабского слова муфрадата в PNG крупным шрифтом - обход того,
что Telegram Bot API HTML не поддерживает font-size (проверено эмпирически
18.08.2026 - жирный <b> уже был, крупнее текст стать не может, это
ограничение самого Bot API, не кода бота).

Обычный PIL ImageFont.truetype без raqm (сервер не даёт эту сборку Pillow,
apt install системной libraqm требует root, которого нет ни у claude-access,
ни в автодеплое) рисует арабские буквы РАЗДЕЛЬНО, без соединения и с
неправильно расположенными огласовками - непригодно для усманского текста
Корана. Поэтому шейпинг делаем сами через uharfbuzz (чистый pip-пакет,
бандлит HarfBuzz статически, root не нужен), а растеризацию - через
freetype-py по glyph id, а не по символу (PIL этого не умеет). Проверено
на сервере в реальном venv (не только локально) - размеры кропа совпали
1-в-1 с локальными (advisor 18.08.2026, жёсткий блокер деплоя).

Шрифт - Scheherazade New (SIL OFL, assets/fonts/), не Amiri Quran: Amiri
Quran спроектирован под многослойную мусхафную вёрстку и на отдельных
словах даёт огромный разрыв между базовой буквой и огласовкой (проверено
эмпирически на "هُدًۭى" и "ٱلَّذِينَ" - метки улетали на полкартинки вверх).
Scheherazade New прошёл проверку на "ٱللَّهِ" (самое частое слово Корана)
и на плотных словах с хамзой/маддой/сукуном - огласовки легли точно.
Один edge-case (طَلَّقْتُمُ - шадда на нетипичной контекстной форме) даёт
такой же разрыв меток В ХРОМЕ с тем же шрифтом (эталонный HarfBuzz,
проверено 18.08.2026) - значит это ограничение самого шрифта на этой
форме, не баг пайплайна, чинить нечем.

Финальный холст ФИКСИРОВАННОГО размера (CANVAS_W x CANVAS_H) для всех
слов - иначе карточка в Telegram прыгает по высоте на каждый тап
(advisor 18.08.2026). Слово рендерится с большим запасом (SHAPE_SIZE),
обрезается по фактическим чернилам и масштабируется так, чтобы всегда
занимать одну и ту же долю холста (FILL_FRACTION) - короткие слова
увеличиваются, длинные чуть уменьшаются, но визуальный размер шрифта
на карточке стабилен от слова к слову (это и решает исходную жалобу
"мелко читать", а не просто больший FONT_SIZE сам по себе)."""
import io
import os

import freetype
import uharfbuzz as hb
from PIL import Image, ImageChops

FONT_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "fonts", "ScheherazadeNew-Regular.ttf")
SHAPE_SIZE = 300  # размер шейпинга/растеризации ДО подгонки под холст - запас на upscale коротких слов
CANVAS_W, CANVAS_H = 900, 480
FILL_FRACTION = 0.82  # доля холста, которую должны занимать чернила слова
MAX_UPSCALE = 4.0  # предел увеличения совсем коротких слов - выше уже размывает растровые глифы
BG_COLOR = "white"
TEXT_COLOR = "black"
_TIGHT_PAD = 8  # небольшой запас при первичной обрезке, чтобы не срезать сглаживание по краю

_hb_blob = hb.Blob.from_file_path(FONT_PATH)
_hb_face = hb.Face(_hb_blob)
_ft_face = freetype.Face(FONT_PATH)
_ft_face.set_char_size(SHAPE_SIZE * 64)
_FT_LOAD_FLAGS = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING  # хинтинг подгоняет под пиксельную сетку и рассинхронизирует с offset'ами HarfBuzz


def _shape(text):
    hb_font = hb.Font(_hb_face)
    hb_font.scale = (SHAPE_SIZE * 64, SHAPE_SIZE * 64)
    hb.ot_font_set_funcs(hb_font)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hb_font, buf)
    return buf.glyph_infos, buf.glyph_positions


def _render_raw(text):
    """Рендерит слово на большом холсте с запасом (метки могут уходить
    высоко над/под буквой) и возвращает тесно обрезанное по чернилам
    изображение произвольного размера."""
    infos, positions = _shape(text)
    total_advance = sum(p.x_advance for p in positions) / 64

    canvas_w = max(400, int(total_advance) + 400)
    canvas_h = SHAPE_SIZE * 4
    img = Image.new("RGB", (canvas_w, canvas_h), BG_COLOR)

    pen_x, pen_y = canvas_w // 2, canvas_h // 2
    cursor_x = pen_x - total_advance / 2

    for info, pos in zip(infos, positions):
        _ft_face.load_glyph(info.codepoint, _FT_LOAD_FLAGS)
        glyph = _ft_face.glyph
        bitmap = glyph.bitmap

        x_offset = pos.x_offset / 64
        y_offset = pos.y_offset / 64
        x_advance = pos.x_advance / 64

        glyph_x = int(cursor_x + glyph.bitmap_left + x_offset)
        glyph_y = int(pen_y - glyph.bitmap_top - y_offset)

        cursor_x += x_advance

        if bitmap.width > 0 and bitmap.rows > 0:
            mask = Image.frombytes("L", (bitmap.width, bitmap.rows), bytes(bitmap.buffer))
            black = Image.new("RGB", mask.size, TEXT_COLOR)
            img.paste(black, (glyph_x, glyph_y), mask)

    bbox = _ink_bbox(img)
    if bbox is None:
        return img
    left, top, right, bottom = bbox
    left = max(0, left - _TIGHT_PAD)
    top = max(0, top - _TIGHT_PAD)
    right = min(canvas_w, right + _TIGHT_PAD)
    bottom = min(canvas_h, bottom + _TIGHT_PAD)
    return img.crop((left, top, right, bottom))


def _ink_bbox(img):
    """getbbox() на PIL считает от чёрного (0,0,0) как "пустого" - у нас
    наоборот, фон белый. Разница с белым холстом даёт маску реальных
    чернил."""
    diff = Image.new("RGB", img.size, BG_COLOR)
    delta = ImageChops.difference(img, diff)
    return delta.getbbox()


def render_word_image(text):
    """Возвращает PIL.Image ФИКСИРОВАННОГО размера (CANVAS_W x CANVAS_H,
    RGB, белый фон) - слово центрировано и масштабировано под
    FILL_FRACTION холста, см. модульный docstring."""
    ink = _render_raw(text)
    ink_w, ink_h = ink.size

    scale = min(CANVAS_W * FILL_FRACTION / ink_w, CANVAS_H * FILL_FRACTION / ink_h)
    scale = min(scale, MAX_UPSCALE)
    new_w, new_h = max(1, round(ink_w * scale)), max(1, round(ink_h * scale))
    ink = ink.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)
    canvas.paste(ink, ((CANVAS_W - new_w) // 2, (CANVAS_H - new_h) // 2))
    return canvas


def render_word_png_bytes(text):
    img = render_word_image(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
