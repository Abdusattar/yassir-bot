"""Наброски знака приложения: буква Y, нарисованная геометрией (10.09.2026).

Не глиф из шрифта, а свой знак: пользователь попросил «обыграть саму букву».
Рисуем в четырёхкратном размере и уменьшаем — у Pillow нет сглаживания линий,
и без этого края выходят рваными.

Каждый набросок должен что-то ЗНАЧИТЬ для этого проекта, иначе это просто
монограмма, каких много. Что значит - в докстроке каждой функции.

    from mark_sketches import SKETCHES
    SKETCHES["bookmark"](384)   -> PIL.Image
"""
from PIL import Image, ImageDraw

EMERALD = (31, 122, 82)
WHITE = (255, 255, 255)
K = 4                       # во сколько раз рисуем крупнее итогового


def _canvas(size):
    return Image.new("RGB", (size * K, size * K), EMERALD)


def _done(img, size):
    return img.resize((size, size), Image.LANCZOS)


def _y_points(size, spread=1.0):
    """Опорные точки буквы: две ветви сверху сходятся в узле, ниже - ножка."""
    s = size * K
    cx = s / 2
    return ((cx - s * 0.20 * spread, s * 0.24),   # левая ветвь
            (cx + s * 0.20 * spread, s * 0.24),   # правая
            (cx, s * 0.55),                       # узел
            (cx, s * 0.80))                       # низ ножки


def merge(size):
    """Две ветви сливаются в одну ножку, и ножка вдвое толще ветвей:
    сорок и сорок сходятся в одну выученную страницу - метод проекта."""
    img = _canvas(size); d = ImageDraw.Draw(img)
    l, r, k, b = _y_points(size)
    w = int(size * K * 0.075)
    d.line([l, k], fill=WHITE, width=w)
    d.line([r, k], fill=WHITE, width=w)
    d.line([k, b], fill=WHITE, width=w * 2)
    for p, rad in ((l, w / 2), (r, w / 2)):
        d.ellipse([p[0] - rad, p[1] - rad, p[0] + rad, p[1] + rad], fill=WHITE)
    # Низ срезан ровно, а не скруглён: круглая пятка читалась как пестик.
    d.rectangle([b[0] - w, b[1] - w, b[0] + w, b[1]], fill=WHITE)
    return _done(img, size)


def bookmark(size):
    """Ножка уходит вниз лентой с вырезом - хвост закладки. Указатель в
    мусхафе, вокруг которого построено всё приложение."""
    img = _canvas(size); d = ImageDraw.Draw(img)
    s = size * K
    l, r, k, _b = _y_points(size)
    w = int(s * 0.075)
    d.line([l, k], fill=WHITE, width=w)
    d.line([r, k], fill=WHITE, width=w)
    for p in (l, r):
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=WHITE)
    bw, top, bottom, notch = w * 1.6, k[1] - w * 0.2, s * 0.86, s * 0.055
    d.polygon([(k[0] - bw / 2, top), (k[0] + bw / 2, top), (k[0] + bw / 2, bottom),
               (k[0], bottom - notch), (k[0] - bw / 2, bottom)], fill=WHITE)
    return _done(img, size)


def stand(size):
    """Ветви - две раскрытые страницы, ножка с перекладиной - рахл, подставка
    под мусхаф."""
    img = _canvas(size); d = ImageDraw.Draw(img)
    s = size * K
    cx, top, mid, span = s / 2, s * 0.26, s * 0.56, s * 0.26
    w = int(s * 0.062)
    for sx in (-1, 1):
        d.polygon([(cx, mid), (cx + sx * span, top + s * 0.05),
                   (cx + sx * span, top + s * 0.05 + w * 1.9), (cx, mid + w * 1.9)], fill=WHITE)
    d.line([(cx, mid + w * 0.9), (cx, s * 0.80)], fill=WHITE, width=w)
    d.line([(cx - span * 0.55, s * 0.80), (cx + span * 0.55, s * 0.80)], fill=WHITE, width=w)
    return _done(img, size)


def seal(size):
    """Буква вырезана в круге - знак-печать, как оттиск на титуле книги."""
    img = _canvas(size); d = ImageDraw.Draw(img)
    s = size * K
    r, cx = s * 0.34, s / 2
    d.ellipse([cx - r, cx - r, cx + r, cx + r], fill=WHITE)
    l, rt, k, b = _y_points(size, 0.62)
    w, off = int(s * 0.058), s * 0.02
    for p0, p1 in ((l, k), (rt, k), (k, (b[0], b[1] - s * 0.03))):
        d.line([(p0[0], p0[1] + off), (p1[0], p1[1] + off)], fill=EMERALD, width=w)
    return _done(img, size)


SKETCHES = {"merge": merge, "bookmark": bookmark, "stand": stand, "seal": seal}


# ── Идея пользователя (10.09.2026): раскрытая книга на стойке ─────────────
# «Книжку можно изящно чёрточку вниз сделать, как будто на стойке раскрытая
# книга, и ещё будет похожа на Y». Два разворота вверх - это и страницы, и
# ветви буквы; чёрточка вниз - и подставка, и ножка Y.

def _band(d, spine, outer, thick, bow, fill):
    """Полоса-страница от корешка к внешнему краю. bow выгибает верхнюю
    кромку - от этого полоса читается как страница, а не как палка."""
    sx, sy = spine
    ox, oy = outer
    pts_top, pts_bot = [], []
    steps = 24
    for i in range(steps + 1):
        t = i / steps
        x = sx + (ox - sx) * t
        y = sy + (oy - sy) * t
        # Выгиб максимален посередине и сходит на нет по краям.
        lift = bow * (t * (1 - t) * 4)
        pts_top.append((x, y - lift))
        pts_bot.append((x, y + thick - lift * 0.35))
    d.polygon(pts_top + list(reversed(pts_bot)), fill=fill)


def _book(size, bow, foot):
    s = size * K
    img = _canvas(size)
    d = ImageDraw.Draw(img)
    spine = (s * 0.50, s * 0.575)
    thick = s * 0.085
    for sx in (-1, 1):
        _band(d, spine, (s * (0.50 + sx * 0.345), s * 0.375), thick, bow * s, WHITE)
    # Чёрточка вниз - тонкая, изящная: она держит книгу, а не спорит с ней.
    stem_w = s * 0.052
    d.rectangle([spine[0] - stem_w / 2, spine[1] + thick * 0.55,
                 spine[0] + stem_w / 2, s * 0.845], fill=WHITE)
    if foot:
        fw = s * 0.20
        d.rectangle([spine[0] - fw / 2, s * 0.845 - stem_w * 0.9,
                     spine[0] + fw / 2, s * 0.845], fill=WHITE)
    return _done(img, size)


def book_plain(size):
    """Прямые развороты, тонкая чёрточка вниз. Самое геометричное чтение."""
    return _book(size, bow=0.0, foot=False)


def book_bowed(size):
    """Развороты выгнуты, как настоящие страницы раскрытой книги."""
    return _book(size, bow=0.030, foot=False)


def book_stand(size):
    """То же, но с короткой перекладиной внизу - книга стоит на рахле."""
    return _book(size, bow=0.030, foot=True)


SKETCHES.update({"book_plain": book_plain,
                 "book_bowed": book_bowed,
                 "book_stand": book_stand})


# ── По существующему лого Yassir (10.09.2026) ─────────────────────────────
# В materials/лого.jpeg книга нарисована КОНТУРОМ: два разворота с прогибом,
# сверху короткие лучи. Здесь та же форма плюс просьба пользователя -
# «изящно чёрточку вниз, как будто на стойке раскрытая книга, и ещё будет
# похожа на Y».

def _stroke(d, pts, w, fill):
    """Ломаная с круглыми стыками: у Pillow нет line-join, иначе на углах
    остаются щели."""
    d.line(pts, fill=fill, width=int(w), joint="curve")
    for x, y in pts:
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=fill)


def _curve(a, b, bow, steps=18):
    """Дуга от a к b с прогибом bow (вверх при отрицательном)."""
    (ax, ay), (bx, by) = a, b
    out = []
    for i in range(steps + 1):
        t = i / steps
        out.append((ax + (bx - ax) * t,
                    ay + (by - ay) * t + bow * (t * (1 - t) * 4)))
    return out


def _book_outline(size, rays, foot):
    s = size * K
    img = _canvas(size)
    d = ImageDraw.Draw(img)
    w = s * 0.045
    spine_top, spine_bot = (s * 0.50, s * 0.455), (s * 0.50, s * 0.650)

    for sx in (-1, 1):
        # Внешний край страницы заметно ВЫШЕ корешка, и страница скатывается
        # к центру - без этого книга читается как гамак (10.09.2026, первый
        # заход вышел плоским).
        outer_top = (s * (0.50 + sx * 0.330), s * 0.310)
        outer_bot = (s * (0.50 + sx * 0.330), s * 0.468)
        top = _curve(spine_top, outer_top, s * 0.042)
        bot = _curve(outer_bot, spine_bot, s * 0.038)
        _stroke(d, top, w, WHITE)
        _stroke(d, bot, w, WHITE)
        _stroke(d, [outer_top, outer_bot], w, WHITE)

    # Корешок - он же начало чёрточки вниз.
    _stroke(d, [spine_top, spine_bot], w, WHITE)
    _stroke(d, [spine_bot, (s * 0.50, s * 0.855)], w * 1.05, WHITE)

    if foot:
        _stroke(d, [(s * 0.395, s * 0.855), (s * 0.605, s * 0.855)], w, WHITE)

    if rays:
        # Три коротких луча над книгой - как в существующем лого.
        for dx, y0, y1 in ((-0.105, 0.300, 0.245), (0.0, 0.285, 0.222),
                           (0.105, 0.300, 0.245)):
            _stroke(d, [(s * (0.50 + dx * 1.10), s * y0),
                        (s * (0.50 + dx * 1.45), s * y1)], w * 0.85, WHITE)
    return _done(img, size)


def logo_stem(size):
    """Книга из лого плюс чёрточка вниз. Без лучей - чистая форма."""
    return _book_outline(size, rays=False, foot=False)


def logo_stem_rays(size):
    """То же с лучами - ближе всего к нынешнему лого Yassir."""
    return _book_outline(size, rays=True, foot=False)


def logo_stem_foot(size):
    """Чёрточка вниз с короткой перекладиной - книга стоит на рахле."""
    return _book_outline(size, rays=False, foot=True)


SKETCHES.update({"logo_stem": logo_stem,
                 "logo_stem_rays": logo_stem_rays,
                 "logo_stem_foot": logo_stem_foot})
