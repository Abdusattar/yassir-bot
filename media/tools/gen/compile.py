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
MEAN_IN = 0.20   # значение под словом проявляется за 0,2 с
WAQF = "ۖۗۘۙۚۛۜ"
MODES = "ABC"


def onehot(mode):
    return [1.0 if m == mode else 0.0 for m in MODES]


def ayah_tokens(page, surah, ayah, words=None):
    """Слова аята со страницы мусхафа; words=[от, до] — часть аята (знак аята только у последней)."""
    d = json.loads((ROOT / "mushaf_data" / ("page%d.json" % page)).read_text("utf-8"))
    a = [x for x in d["ayahs"] if x["surah"] == surah and x["ayah"] == ayah][0]
    ws = [{"pos": t["position"], "glyph": t["code_v4"], "meaning": t.get("translation", ""),
           "waqf": "".join(c for c in t["html"] if c in WAQF)} for t in a["tokens"] if t["type"] == "word"]
    end = [t["code_v4"] for t in a["tokens"] if t["type"] == "ayah_end"][0]
    if words:
        last = ws[-1]["pos"]
        ws = [w for w in ws if words[0] <= w["pos"] <= words[1]]
        end = end if ws[-1]["pos"] == last else None
    return ws, end


def compile_sheet(sheet, tl, live=None):
    """live — {номер плана: (file-URI папки кадров, число кадров)} от нарезки живых клипов."""
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
        op = {"c0": 0, "kfs": [[t0, 1, p["in"]["dur"], 0]]}
        if p["out"]:
            op["kfs"].append([chk(T(p["out"]["at"]), "выход плана %d" % p["plan"]), 0, p["out"]["dur"], 0])
        plan = {"id": p["plan"], "t0": t0, "t1": t1, "zoom": p["zoom"], "op": op,
                "finale": p.get("finale", False), "texts": [], "block": None, "live": None}
        if p.get("ayah"):
            a = p["ayah"]
            words, end = ayah_tokens(a["page"], a["surah"], a["ayah"], a.get("words"))
            for w in words:  # значение из листа важнее пословного перевода страницы
                w["meaning"] = a.get("meanings", {}).get(str(w["pos"]), w["meaning"])
            first = [s["mode"] for s in sheet["scenes"] if s["plan"] == p["plan"]][0]
            plan["block"] = {"page": a["page"], "ref": "%d:%d" % (a["surah"], a["ayah"]), "words": words,
                             "end": end, "values": bool(sheet.get("values")),
                             "move": {"c0": onehot(first), "kfs": []},
                             "colors": [{"c0": DIM, "kfs": []} for _ in words],
                             "means": [{"c0": 0, "kfs": []} for _ in words]}
        if p.get("live"):
            L = p["live"]
            base, n = live[p["plan"]]
            br = {"c0": 0, "kfs": []}
            if L.get("brighten"):
                br["kfs"].append([T(L["brighten"]["at"]), 1, L["brighten"]["dur"], 1])
            plan["live"] = {"base": base, "n": n, "at": T(L.get("at", p["in"]["at"])), "bright": br,
                            "green": bool(L.get("green"))}
        plans.append(plan)
    byid = {p["id"]: p for p in plans}
    for a in sheet["audio"]:  # шум — до и после чтения, никогда под ним (style §7)
        if a["kind"] == "noise":
            e = a["at"] + a["out"] - a["in"]
            if any(s < e and a["at"] < v for s, v in tl.voiced()):
                tl.warnings.append("шум %.2f–%.2f звучит под чтением" % (a["at"], e))

    for s in sheet["scenes"]:
        plan = byid[s["plan"]]
        b = plan["block"]
        if b and s.get("move"):
            at = chk(T(s["move"]["at"]), "переезд сц. %d" % s["scene"])
            to = s["move"].get("to", s["mode"])
            b["move"]["kfs"].append([at, onehot(to), s["move"]["dur"], 1])
            if to != "A":  # в B и C значения прозрачны, место за ними остаётся (style §3)
                for m in b["means"]:
                    m["kfs"].append([at, 0, 0.25, 0])
        if b and s.get("reset"):
            at = T(s["reset"]["at"])
            for w, c in zip(b["words"], b["colors"]):
                if w["pos"] not in s.get("key", []):
                    c["kfs"].append([at, DIM, s["reset"]["dur"], 0])
        if b and s.get("voice"):
            seg = tl.seg[s["voice"]]
            end_seg = T(s["voice"] + ".end")
            lit_end = T(s["lit_end"]) if s.get("lit_end") else None
            voiced = [p for p in seg["words"] if p in [w["pos"] for w in b["words"]]]
            for i, pos in enumerate(voiced):
                k = [w["pos"] for w in b["words"]].index(pos)
                c = b["colors"][k]
                t_on = tl.word(s["voice"], pos)[0] - LEAD
                if s["mode"] == "A" and b["values"]:
                    b["means"][k]["kfs"].append([t_on, 1, MEAN_IN, 0])
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
            # fade 0 — текст входит вместе с планом (кадр 0 или растворение плана)
            item["op"] = {"c0": 0, "kfs": [[on, 1, x.get("fade_in", 0), 0]]}
            if x.get("off") is not None:
                off = chk(T(x["off"]), "уход «%s»" % x.get("text", x["role"]))
                item["op"]["kfs"].append([off, 0, x["fade_out"], 0])
                item["t_off"] = off
            item["t_on"] = on
            plan["texts"].append(item)
    for p in plans:
        if p["block"]:
            for c in p["block"]["colors"] + p["block"]["means"]:
                c["kfs"].sort(key=lambda k: k[0])
            # знак конца аята идёт за последним словом, но синим и золотым не бывает: dim -> ink
            last = p["block"]["colors"][-1]
            p["block"]["end_color"] = {"c0": DIM, "kfs": [[k[0], DIM if k[1] == DIM else INK, k[2], k[3]]
                                                         for k in last["kfs"] if k[1] != BLUE]}
    frames = math.ceil(dur * fps - 1e-9)
    return {"fps": fps, "duration": dur, "frames": frames, "plans": plans}
