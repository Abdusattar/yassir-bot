"""Лист + замеры -> данные страницы: планы, ключевые точки opacity/цвета/переезда (всё — от t).

Ключевая точка [t, значение, длительность, ease]: с момента t значение плавно идёт к новому
за «длительность» (линейно или ease-in-out). Страница вычисляет кадр по ним как чистую функцию t.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# токены цвета style §1 (RGBA)
DIM = [29, 26, 22, 0.40]
BLUE = [36, 86, 184, 1]
INK = [29, 26, 22, 1]
GOLD = [138, 96, 21, 1]
LEAD = 0.04      # подсветка опережает голос (style §7)
LIGHT = 0.10     # слово загорается за 0,1 с (style §4)
WAQF = "ۖۗۘۙۚۛۜ"


def ayah_tokens(page, surah, ayah):
    d = json.loads((ROOT / "mushaf_data" / ("page%d.json" % page)).read_text("utf-8"))
    a = [x for x in d["ayahs"] if x["surah"] == surah and x["ayah"] == ayah][0]
    words = [{"pos": t["position"], "glyph": t["code_v4"],
              "waqf": "".join(c for c in t["html"] if c in WAQF)} for t in a["tokens"] if t["type"] == "word"]
    end = [t["code_v4"] for t in a["tokens"] if t["type"] == "ayah_end"][0]
    return words, end


def compile_sheet(sheet, tl):
    fps = sheet["fps"]
    dur = sheet["duration"]
    T = tl.t
    chk = tl.check_change
    plans = []
    for p in sheet["plans"]:
        t0 = T(p["in"]["at"])
        t1 = T(p["out"]["at"]) + p["out"]["dur"] if p["out"] else dur
        if p["in"]["dur"]:
            t0 = chk(t0, "вход плана %d" % p["plan"])
        if p["out"]:
            chk(T(p["out"]["at"]), "выход плана %d" % p["plan"])
        op = {"c0": 0, "kfs": [[t0, 1, p["in"]["dur"], 0]]}
        if p["out"]:
            op["kfs"].append([T(p["out"]["at"]), 0, p["out"]["dur"], 0])
        plan = {"id": p["plan"], "t0": t0, "t1": t1, "zoom": p["zoom"], "op": op,
                "finale": p.get("finale", False), "texts": [], "block": None}
        if p.get("ayah"):
            a = p["ayah"]
            words, end = ayah_tokens(a["page"], a["surah"], a["ayah"])
            plan["block"] = {"page": a["page"], "ref": "%d:%d" % (a["surah"], a["ayah"]), "words": words,
                             "end": end, "move": {"c0": 0, "kfs": []},
                             "colors": [{"c0": DIM, "kfs": []} for _ in words]}
        plans.append(plan)
    byid = {p["id"]: p for p in plans}

    for s in sheet["scenes"]:
        plan = byid[s["plan"]]
        b = plan["block"]
        if b and s.get("move"):
            at = chk(T(s["move"]["at"]), "переезд сц. %d" % s["scene"])
            b["move"]["kfs"].append([at, 1, s["move"]["dur"], 1])  # 0 = режим B, 1 = режим C
        if b and s.get("reset"):
            at = T(s["reset"]["at"])
            for w, c in zip(b["words"], b["colors"]):
                if w["pos"] not in s.get("key", []):
                    c["kfs"].append([at, DIM, s["reset"]["dur"], 0])
        if b and s.get("voice"):
            seg = tl.seg[s["voice"]]
            end_seg = T(s["voice"] + ".end")
            lit_end = T(s["lit_end"]) if s.get("lit_end") else None
            voiced = seg["words"]
            for i, pos in enumerate(voiced):
                k = [w["pos"] for w in b["words"]].index(pos)
                c = b["colors"][k]
                t_on = tl.word(s["voice"], pos)[0] - LEAD
                if pos in s.get("key", []):
                    if s.get("key_from_scene"):
                        c["c0"] = GOLD  # золото с первого кадра сцены (craft)
                    else:
                        c["kfs"].append([t_on, GOLD, LIGHT, 0])
                    continue
                c["kfs"].append([t_on, BLUE, LIGHT, 0])
                if i + 1 < len(voiced):
                    t_off = tl.word(s["voice"], voiced[i + 1])[0] - LEAD
                else:
                    t_off = lit_end if lit_end is not None else min(tl.word(s["voice"], pos)[1], end_seg)
                c["kfs"].append([t_off, INK, LIGHT, 0])
        for x in s.get("texts", []):
            on = T(x["on"])
            if x.get("fade_in"):
                on = chk(on, "%s сц. %d" % (x.get("text", x["role"]), s["scene"]))
            item = {k: v for k, v in x.items() if k not in ("on", "off", "fade_in", "fade_out")}
            item.setdefault("mode", s["mode"])
            # текст сцены с кадра 0 / вместе с планом: fade 0 -> виден сразу, исчезает вместе с планом
            item["op"] = {"c0": 0, "kfs": [[on, 1, x.get("fade_in", 0), 0]]}
            if x.get("off") is not None:
                off = chk(T(x["off"]), "уход «%s»" % x.get("text", x["role"]))
                item["op"]["kfs"].append([off, 0, x["fade_out"], 0])
                item["t_off"] = off
            item["t_on"] = on
            plan["texts"].append(item)
    for p in plans:
        if p["block"]:
            for c in p["block"]["colors"]:
                c["kfs"].sort(key=lambda k: k[0])
    frames = math.ceil(dur * fps - 1e-9)
    return {"fps": fps, "duration": dur, "frames": frames, "plans": plans}
