"""Монтажный лист -> шкала времени (style §5, §7).

Якоря времени: число секунд или «R1.w3.start-0.04», «R1.w3.end», «R1.start», «R1.end».
Время слова = qdc_start − in + at + offset_measured; края отрезка — at и at + (out − in).
"""
import json
import re
import urllib.request
from pathlib import Path

QDC = "https://api.qurancdn.com/api/qdc/audio/reciters/7/audio_files?chapter=%d&segments=true"
AUDIO = "https://download.quranicaudio.com/qdc/mishari_al_afasy/murattal/%d.mp3"
ROOT_DIR = Path(__file__).resolve().parents[3]
ANCHOR = re.compile(r"^(R\d+)\.(?:w(\d+)\.)?(start|end)([+-]\d+(?:\.\d+)?)?$")


def fetch(url, path):
    """Скачать один раз в кэш (qurancdn без User-Agent отвечает 403)."""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        path.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return path


def chapter_of(src):
    # «qdc:mishari_al_afasy/2» -> 2
    return int(src.split("/")[-1])


def qdc_words(cache, chapter, ayah):
    """{позиция слова: (начало, конец)} в секундах файла суры."""
    d = json.loads(fetch(QDC % chapter, Path(cache) / ("qdc_%d.json" % chapter)).read_text("utf-8"))
    v = [x for x in d["audio_files"][0]["verse_timings"] if x["verse_key"] == "%d:%d" % (chapter, ayah)][0]
    return {s[0]: (s[1] / 1000, s[2] / 1000) for s in v["segments"] if len(s) == 3}


class Timeline:
    def __init__(self, sheet, cache):
        self.sheet = sheet
        self.cache = Path(cache)
        self.seg = {a["id"]: a for a in sheet["audio"]}
        for a in sheet["audio"]:
            if a["kind"] == "recitation":
                q = qdc_words(cache, chapter_of(a["src"]), a["ayah"])
                a["qdc"] = {p: q[p] for p in a["words"]}
        self.warnings = []

    def word(self, sid, pos):
        """(t, t_end) слова на шкале ролика с замеренным смещением."""
        a = self.seg[sid]
        s, e = a["qdc"][pos]
        k = a["at"] - a["in"] + a.get("offset_measured", 0.0)
        return s + k, e + k

    def t(self, x):
        if isinstance(x, (int, float)):
            return float(x)
        m = ANCHOR.match(x)
        if not m:
            raise ValueError("непонятный якорь: %s" % x)
        sid, pos, edge, d = m.groups()
        a = self.seg[sid]
        if pos:
            v = self.word(sid, int(pos))[0 if edge == "start" else 1]
        else:
            v = a["at"] if edge == "start" else a["at"] + a["out"] - a["in"]
        return v + (float(d) if d else 0.0)

    def voiced(self):
        """Интервалы звучащих слов [(t, t_end)] по всем отрезкам, по порядку."""
        out = []
        for a in self.sheet["audio"]:
            if a["kind"] != "recitation":
                continue
            end = self.t(a["id"] + ".end")
            for p in a["words"]:
                s, e = self.word(a["id"], p)
                out.append((max(s, a["at"]), min(e, end)))
        return sorted(out)

    def allowed(self, t):
        """Смена текста допустима (style §5): ±100 мс от границы слова или в паузе ≥300 мс."""
        iv = self.voiced()
        bounds = [b for s, e in iv for b in (s, e)]
        if any(abs(t - b) <= 0.1 + 1e-6 for b in bounds):
            return True
        for s, e in iv:
            if s < t < e:
                return False
        # вне слов: пауза между соседними словами должна быть ≥300 мс
        prev = max([e for s, e in iv if e <= t], default=-1e9)
        nxt = min([s for s, e in iv if s >= t], default=1e9)
        return nxt - prev >= 0.3

    def nearest_allowed(self, t):
        for k in range(1, 2000):
            for c in (t - k * 0.001, t + k * 0.001):
                if self.allowed(c):
                    return c
        return t

    def check_change(self, t, what):
        """Проверить начало смены текста; не попало — сдвинуть и предупредить."""
        if self.allowed(t):
            return t
        n = self.nearest_allowed(t)
        self.warnings.append("смена «%s» в %.3f посреди слова -> сдвинута на %.3f" % (what, t, n))
        return n
