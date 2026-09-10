"""Значки приложения для экрана телефона (10.09.2026).

Утром они были сделаны разовым скриптом «на коленке», и перегенерировать их
было нечем. Здесь то же самое, но постоянным скриптом: сменили оттенок или
знак - перезапустили, а не вспоминали, как оно делалось.

    python scripts/make_app_icons.py                 # показать варианты
    python scripts/make_app_icons.py --apply solid   # записать выбранный

Что записывается в mushaf_data/ при --apply:
    icon-192.png, icon-512.png   - обычный значок (purpose "any")
    icon-maskable-512.png        - для Android, где система сама режет форму:
                                   знак мельче, вокруг поле, иначе край срежут
    apple-touch-icon.png         - iOS, 180x180, без прозрачности

Знак - ۩ (U+06E9, место сажды в мусхафе). Он же стоит на двери «Мусхаф»
внутри приложения: значок на экране телефона и дверь внутри должны быть
одним и тем же знаком, иначе связь не читается.
"""
import argparse
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "mushaf_data"
PREVIEW = ROOT / "logs" / "dash_variants"

MARK = "\u06e9"
EMERALD = (31, 122, 82)          # --accent, тот же изумруд, что во всём приложении
CREAM = (248, 246, 239)          # background_color манифеста, цвет бумаги мусхафа
INK = (24, 28, 26)               # почти чёрный тёмной темы
WHITE = (255, 255, 255)

# Шрифт нужен арабо-способный: в обычном системном ۩ вырождается в квадрат.
FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/tahoma.ttf",
    "C:/Windows/Fonts/seguisym.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def find_font(size):
    for path in FONT_CANDIDATES:
        try:
            font = ImageFont.truetype(path, size)
            if font.getmask(MARK).size[0] > 4:
                return font
        except OSError:
            continue
    raise SystemExit("нет шрифта, умеющего рисовать ۩ — допиши FONT_CANDIDATES")


def rounded(size, radius_ratio=0.22):
    """Маска скруглённого квадрата. Android и iOS режут значок сами, но для
    обычного purpose "any" форму задаём мы - иначе на части оболочек он
    останется резким квадратом."""
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * radius_ratio), fill=255)
    return m


def vertical_gradient(size, top, bottom):
    g = Image.new("RGB", (1, size))
    for y in range(size):
        k = y / max(1, size - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)))
    return g.resize((size, size))


def draw_mark(img, color, fill_ratio):
    """Знак по центру. Центруем по РЕАЛЬНЫМ границам глифа (bbox), а не по
    метрикам шрифта: у ۩ большой внутренний отступ сверху, и по метрикам он
    садится заметно ниже середины."""
    size = img.size[0]
    font = find_font(int(size * fill_ratio))
    d = ImageDraw.Draw(img)
    box = d.textbbox((0, 0), MARK, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]), MARK, font=font, fill=color)
    return img


# Каждый вариант: (подпись, чем описывается, функция отрисовки).
def v_solid(size, pad=False):
    img = Image.new("RGB", (size, size), EMERALD)
    draw_mark(img, WHITE, 0.44 if pad else 0.62)
    return img


def v_light(size, pad=False):
    img = Image.new("RGB", (size, size), CREAM)
    draw_mark(img, EMERALD, 0.44 if pad else 0.62)
    return img


def v_gradient(size, pad=False):
    img = vertical_gradient(size, (38, 143, 96), (18, 92, 61))
    draw_mark(img, WHITE, 0.44 if pad else 0.62)
    return img


def v_night(size, pad=False):
    img = Image.new("RGB", (size, size), INK)
    draw_mark(img, EMERALD, 0.44 if pad else 0.62)
    return img


VARIANTS = {
    "solid": ("A. Сейчас",
              "Белый знак на сплошном изумруде. Фирменный цвет, читается "
              "издалека и не теряется среди пёстрых значков.",
              v_solid),
    "light": ("B. Светлый",
              "Изумрудный знак на цвете бумаги мусхафа — том же, что фон "
              "приложения. Тише, но на светлых обоях почти сливается.",
              v_light),
    "gradient": ("C. Градиент",
                 "Изумруд сверху вниз — тот же переход, что на фоне дашборда: "
                 "значок и первый экран одно целое. На мелком размере разница "
                 "почти не видна.",
                 v_gradient),
    "night": ("D. Тёмный",
              "Изумрудный знак на чернильном. Контрастен на любых обоях, но "
              "выбивается из изумрудного, которым помечено всё остальное.",
              v_night),
}


# ── Знак из логотипа Yassir (10.09.2026) ─────────────────────────────────
# Решение пользователя: значок приложения — это логотип проекта. Сам
# скриншот (materials/лого.jpeg) в дело не годится: значок там 124 точки,
# а нужны 512 и maskable — растягивание даёт мыло и jpeg-шум по краям
# линий. Поэтому тот же знак перерисован геометрией: две страницы контуром
# и три луча, чистые на любом размере. Координаты сняты с оригинала и
# заданы в долях стороны знака.

BLUE_TOP = (74, 150, 250)        # верх градиента на оригинальном лого
BLUE_BOT = (82, 96, 235)         # низ — уходит в сине-фиолетовый
SS = 4                           # суперсемплинг: у Pillow нет сглаживания линий


def _curve(a, b, bow, steps=26):
    """Дуга от a к b с прогибом bow (минус — выгиб вверх)."""
    (ax, ay), (bx, by) = a, b
    out = []
    for i in range(steps + 1):
        t = i / steps
        out.append((ax + (bx - ax) * t,
                    ay + (by - ay) * t + bow * (t * (1 - t) * 4)))
    return out


def _stroke(d, pts, w, fill):
    """Ломаная с круглыми стыками и торцами: без этого на углах щели."""
    d.line(pts, fill=fill, width=max(1, int(round(w))), joint="curve")
    r = w / 2.0
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


# Знак живёт в своём квадрате: ширина 1.0, высота MARK_H. Все числа сняты
# с materials/лого.jpeg по пикселям (белые точки внутри синего квадрата),
# а не на глаз: первый заход рисовался «примерно» и вышел чашей.
MARK_H = 0.79


def draw_logo_mark(d, x0, y0, side, color, rays=True):
    def P(u, v):
        return (x0 + u * side, y0 + v * side)

    # Толще, чем в большом логотипе (там контур 0.03 стороны): на 48 точках
    # такая линия исчезает.
    w = side * 0.055
    for sx in (-1, 1):
        outer_top = P(0.5 + sx * 0.5, 0.325)
        outer_bot = P(0.5 + sx * 0.5, 0.591)
        inner_top = P(0.5 + sx * 0.022, 0.524)
        point = P(0.5, MARK_H)              # обе страницы сходятся в «V»
        # Верхняя кромка страницы выгнута ВВЕРХ: внешний край поднят, лист
        # скатывается к центру. Выгиб вниз превращает книгу в чашу.
        _stroke(d, _curve(inner_top, outer_top, -side * 0.031), w, color)
        _stroke(d, [outer_top, outer_bot], w, color)
        _stroke(d, _curve(outer_bot, point, -side * 0.022), w, color)
    if rays:
        # Три коротких луча над книгой: средний вертикальный, боковые
        # расходятся веером.
        _stroke(d, [P(0.5, 0.155), P(0.5, 0.0)], w * 0.9, color)
        for sx in (-1, 1):
            _stroke(d, [P(0.5 + sx * 0.146, 0.173), P(0.5 + sx * 0.206, 0.075)],
                    w * 0.9, color)


def logo_tile(size, bg, color, pad=False, rays=True):
    """Значок целиком. bg — функция (сторона) -> картинка фона."""
    s = size * SS
    img = bg(s)
    d = ImageDraw.Draw(img)
    # На maskable знак мельче: систему не переспоришь, она режет края сама.
    side = s * (0.50 if pad else 0.66)
    draw_logo_mark(d, (s - side) / 2, (s - side * MARK_H) / 2, side, color, rays)
    return img.resize((size, size), Image.LANCZOS)


def v_logo_blue(size, pad=False):
    return logo_tile(size, lambda s: vertical_gradient(s, BLUE_TOP, BLUE_BOT), WHITE, pad)


def v_logo_emerald(size, pad=False):
    return logo_tile(size, lambda s: Image.new("RGB", (s, s), EMERALD), WHITE, pad)


def v_logo_emerald_grad(size, pad=False):
    return logo_tile(size, lambda s: vertical_gradient(s, (38, 143, 96), (18, 92, 61)),
                     WHITE, pad)


def v_logo_norays(size, pad=False):
    return logo_tile(size, lambda s: Image.new("RGB", (s, s), EMERALD), WHITE, pad,
                     rays=False)


LOGO_VARIANTS = {
    "blue": ("A. Как в лого",
             "Тот же синий градиент, что на логотипе. Узнаётся сразу, но "
             "синего внутри приложения нет нигде.",
             v_logo_blue),
    "emerald": ("B. Знак лого, цвет приложения",
                "Та же книга на изумруде #1f7a52. Значок и первый экран "
                "одного цвета.",
                v_logo_emerald),
    "emerald_grad": ("C. Изумруд градиентом",
                     "Тот же переход, что на фоне дашборда. На мелком размере "
                     "от сплошного почти не отличается.",
                     v_logo_emerald_grad),
    "norays": ("D. Без лучей",
               "Книга без лучей на изумруде. На 48 точках лучи слипаются в "
               "крап, без них книга читается чище.",
               v_logo_norays),
}
VARIANTS.update(LOGO_VARIANTS)


# ── Как значок смотрится на экране телефона ───────────────────────────────
# Лист на белом фоне обманывает: значок живёт размером с ноготь, среди чужих
# и поверх обоев. Здесь он показан именно так - и на светлых обоях, и на
# тёмных, потому что светлый и тёмный варианты ведут себя на них по-разному.
#
# Соседние значки - НЕЙТРАЛЬНЫЕ заглушки, не подражание чужим приложениям:
# приглушённый квадрат и простой знак, чтобы дать окружение, а не логотипы.
NEIGHBOURS = [
    ((196, 122, 92), "✉"), ((104, 126, 168), "☎"),
    ((150, 136, 176), "♪"), ((122, 156, 132), "⏲"),
    ((176, 150, 96), "☁"),
]


def _home_cell(fn, dark, w, h):
    """Кусок домашнего экрана: два ряда по три значка, наш - первый."""
    bg_top = (26, 30, 34) if dark else (232, 234, 228)
    bg_bot = (12, 14, 17) if dark else (206, 214, 205)
    cell = vertical_gradient_rect(w, h, bg_top, bg_bot)
    d = ImageDraw.Draw(cell)
    ico, gap, cols = 54, 22, 3
    left = (w - (ico * cols + gap * (cols - 1))) // 2
    top = 16
    name_font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 9)
    def put(i, img, title):
        x = left + (i % cols) * (ico + gap)
        y = top + (i // cols) * (ico + 30)
        img = img.resize((ico, ico), Image.LANCZOS).convert("RGBA")
        img.putalpha(rounded(ico))
        cell.paste(img, (x, y), img)
        tw = d.textlength(title, font=name_font)
        d.text((x + (ico - tw) / 2, y + ico + 5), title,
               font=name_font, fill=(235, 238, 233) if dark else (48, 54, 50))
    put(0, fn(160), "YassirApp")
    for k, (colour, glyph) in enumerate(NEIGHBOURS):
        tile = Image.new("RGB", (160, 160), colour)
        gf = ImageFont.truetype("C:/Windows/Fonts/seguisym.ttf", 78)
        dd = ImageDraw.Draw(tile)
        box = dd.textbbox((0, 0), glyph, font=gf)
        dd.text(((160 - (box[2] - box[0])) / 2 - box[0],
                 (160 - (box[3] - box[1])) / 2 - box[1]), glyph, font=gf, fill=(255, 255, 255))
        put(k + 1, tile, "")
    return cell


def vertical_gradient_rect(w, h, top, bottom):
    g = Image.new("RGB", (1, h))
    for y in range(h):
        k = y / max(1, h - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)))
    return g.resize((w, h))


def home():
    PREVIEW.mkdir(parents=True, exist_ok=True)
    w, h, pad, top = 220, 190, 16, 30
    names = list(VARIANTS)
    sheet = Image.new("RGB", (pad + (w + pad) * len(names), top + (h + 10) * 2 + pad), "white")
    d = ImageDraw.Draw(sheet)
    label = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 13)
    for i, key in enumerate(names):
        cap, _why, fn = VARIANTS[key]
        x = pad + i * (w + pad)
        d.text((x, 9), cap, font=label, fill=(31, 122, 82))
        sheet.paste(_home_cell(fn, False, w, h), (x, top))
        sheet.paste(_home_cell(fn, True, w, h), (x, top + h + 10))
    out = PREVIEW / "app_icons_home.jpg"
    sheet.save(out, "JPEG", quality=92)
    print("на экране телефона:", out)

def preview():
    PREVIEW.mkdir(parents=True, exist_ok=True)
    cell, pad, top = 190, 26, 118
    names = list(VARIANTS)
    sheet = Image.new("RGB", (pad + (cell + pad) * len(names), cell + top + pad), "white")
    d = ImageDraw.Draw(sheet)
    label = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 13)
    note = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 11)
    for i, key in enumerate(names):
        cap, why, fn = VARIANTS[key]
        x = pad + i * (cell + pad)
        icon = fn(cell).convert("RGBA")
        icon.putalpha(rounded(cell))
        sheet.paste(icon, (x, 34), icon)
        d.text((x, 12), cap, font=label, fill=(31, 122, 82))
        # Описание переносим по словам - иначе вылезает за свою колонку.
        line, y = "", 34 + cell + 10
        for word in why.split():
            probe = (line + " " + word).strip()
            if d.textlength(probe, font=note) > cell:
                d.text((x, y), line, font=note, fill=(70, 78, 74)); y += 15; line = word
            else:
                line = probe
        d.text((x, y), line, font=note, fill=(70, 78, 74))
    out = PREVIEW / "app_icons.jpg"
    sheet.save(out, "JPEG", quality=90)
    print("варианты:", out)


def apply(key):
    if key not in VARIANTS:
        raise SystemExit("нет варианта %s (есть: %s)" % (key, ", ".join(VARIANTS)))
    fn = VARIANTS[key][2]
    for size, name in ((192, "icon-192.png"), (512, "icon-512.png")):
        img = fn(size).convert("RGBA")
        img.putalpha(rounded(size))
        img.save(OUT / name)
    # Маскируемый: система режет по своей форме, поэтому знак мельче и на
    # сплошном поле без скругления - обрежут ровно столько, сколько надо.
    fn(512, pad=True).save(OUT / "icon-maskable-512.png")
    # iOS не любит прозрачность в apple-touch-icon и скругляет сама.
    fn(180).save(OUT / "apple-touch-icon.png")
    print("записано в", OUT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", default="", help="записать вариант: " + ", ".join(VARIANTS))
    ap.add_argument("--home", action="store_true",
                    help="показать значки на экране телефона, а не листом")
    a = ap.parse_args()
    if a.apply:
        apply(a.apply)
    elif a.home:
        home()
    else:
        preview()
