"""Чек-лист постановщика style §11 — замеры по готовому mp4 и build.json генератора.

    python media/tools/gen/check.py media/videos/04_slovo_huda/sheet.json --work <папка make.py>

Печатает таблицу пунктов (✓/✗ + число), кладёт полосы кадров вокруг смен и растяжку ×12 в work/check/.
"""
import argparse
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from compile import BLUE, GOLD  # noqa: E402,F401

FPS = 30


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def frame(mp4, t, gray=False):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.4f" % t, "-i", str(mp4), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24", "-"],
                         capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint8)
    return a.reshape(1920, 1080) if gray else a.reshape(1920, 1080, 3)


def frames_range(mp4, t0, t1, gray=True):
    """Все кадры [t0, t1) подряд (точнее, чем -ss на каждый)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.4f" % t0, "-i", str(mp4), "-t", "%.4f" % (t1 - t0),
                          "-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24", "-"],
                         capture_output=True, check=True).stdout
    sz = 1920 * 1080 * (1 if gray else 3)
    a = np.frombuffer(raw, np.uint8)
    n = len(a) // sz
    return a[:n * sz].reshape((n, 1920, 1080) if gray else (n, 1920, 1080, 3))


def png_range(work, t0, t1):
    """Кадры PNG до кодера (make.py --keep-frames): дрожь рендера без шума CRF 18."""
    d = Path(work) / "frames"
    if not (d / "00000.png").exists():
        return None
    return np.stack([np.asarray(Image.open(d / ("%05d.png" % i)).convert("L"), float)
                     for i in range(round(t0 * FPS), round(t1 * FPS))])


def background(work):
    """Чистая бумага той же страницы (все планы прозрачны) — опора для безопасных зон."""
    from playwright.async_api import async_playwright
    out = Path(work) / "check" / "bg.png"

    async def run():
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            pg = await b.new_page(viewport={"width": 1080, "height": 1920})
            await pg.goto((Path(work) / "page.html").as_uri(), wait_until="networkidle")
            await pg.evaluate("boot()")
            await pg.evaluate("render(0); document.querySelectorAll('.plan').forEach(p => p.style.opacity = 0)")
            await pg.screenshot(path=str(out))
            await b.close()
    asyncio.run(run())
    return np.asarray(Image.open(out).convert("L"), float)


def strip(mp4, ts, path, w=216):
    ims = [Image.fromarray(frame(mp4, max(0, t))).resize((w, int(w * 16 / 9)), Image.LANCZOS) for t in ts]
    out = Image.new("RGB", (w * len(ims), ims[0].height), "white")
    for i, im in enumerate(ims):
        out.paste(im, (i * w, 0))
    out.save(path)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    sheet_path = Path(a.sheet).resolve()
    sheet = json.loads(sheet_path.read_text("utf-8"))
    vdir, work = sheet_path.parent, Path(a.work)
    mp4 = vdir / ("%s.mp4" % sheet.get("version", "draft"))
    B = json.loads((work / "build.json").read_text("utf-8"))
    D = B["data"]
    (work / "check").mkdir(exist_ok=True)
    R = []

    def res(n, ok, msg):
        R.append((n, "✓" if ok else "✗", msg))

    # ---- события (из данных страницы) ----
    events = []  # (t, что)
    texts = []
    for p in D["plans"]:
        for k in p["op"]["kfs"]:
            events.append((k[0], "план %d %s" % (p["id"], "вход" if k[1] else "уход"), k[2]))
        if p["block"]:
            for k in p["block"]["move"]["kfs"]:
                events.append((k[0], "переезд план %d" % p["id"], k[2]))
            for c in p["block"]["colors"]:
                for k in c["kfs"]:
                    events.append((k[0], "цвет слова", k[2]))
        for x in p["texts"]:
            texts.append((p, x))
            for k in x["op"]["kfs"]:
                events.append((k[0], "%s %s" % (x.get("text", x["role"]), "вход" if k[1] else "уход"), k[2]))
    events.sort()

    # 1. Склейки: детектор сцен
    err = sh(["ffmpeg", "-i", str(mp4), "-vf", "select='gt(scene,0.25)',showinfo", "-f", "null", "-"]).stderr
    cuts = [float(x) for x in re.findall(r"pts_time:([\d.]+)", err)]
    fades = sorted({round(e[2], 2) for e in events if e[1].startswith("план") and e[2] > 0})
    res(1, not cuts, "scene>0.25: %d склеек %s; растворения планов %s с" % (len(cuts), cuts, fades))

    # 2. Ни один текст не появляется/исчезает за 1 кадр
    bad = []
    for p, x in texts:
        for k in x["op"]["kfs"]:
            if k[2] < 1.5 / FPS:
                plan_in = p["op"]["kfs"][0]
                if not (abs(k[0] - plan_in[0]) < 1e-6 and (plan_in[2] > 0 or k[0] == 0)):
                    bad.append(x.get("text", x["role"]))
    res(2, not bad, "все входы/уходы текста ≥0,2 с или вместе с растворением плана" if not bad else str(bad))

    # 3. Раскладка
    lay = [l for l in B["layout"] if "ref" in l]
    ok3 = all(l["ratio"] <= 0.25 and not l["warn"] for l in lay)
    mv = sorted({e[2] for e in events if e[1].startswith("переезд")})
    res(3, ok3 and all(abs(m - 0.5) < 1e-6 for m in mv),
        "; ".join("%s: %d px, строки %s, разница %.0f %%" % (l["ref"], l["k"], l["rows"], 100 * l["ratio"])
                  for l in lay) + "; знак аята приклеен к последнему слову; переезды %s с" % mv)

    # 4. Дрожь наезда: центр текста (линейный вес = бумага − кадр) на статичных отрезках;
    #    остаток к квадратичной подгонке и вторая разность кадр к кадру
    bg = background(work)
    jit, d2s, slow = [], [], []
    for t0, t1, zones in ((2.3, 5.3, ((240, 520), (560, 940))), (23.0, 26.5, ((600, 920),)),
                          (8.45, 11.7, ((250, 640), (620, 1040)))):
        fr = png_range(work, t0, t1)
        fr = fr if fr is not None else frames_range(mp4, t0, t1).astype(float)
        for y0, y1 in zones:
            w = np.clip(bg[None, y0:y1] - fr[:, y0:y1], 0, None)
            w[w < 3] = 0
            ys, xs = np.mgrid[y0:y1, 0:1080]
            c = np.stack([(w * xs).sum((1, 2)) / w.sum((1, 2)), (w * ys).sum((1, 2)) / w.sum((1, 2))], 1)
            n = np.arange(len(c))
            for k in (0, 1):
                r = c[:, k] - np.polyval(np.polyfit(n, c[:, k], 2), n)
                hp = c[2:-2, k] - np.convolve(c[:, k], np.ones(5) / 5, "valid")  # дрожь кадр к кадру
                jit.append(abs(hp).max())
                slow.append(abs(r).max())
                print("  дрожь %.1f–%.1f y%d–%d %s: %.3f / %.3f" % (t0, t1, y0, y1, "xy"[k], abs(r).max(),
                                                                  np.abs(np.diff(c[:, k], 2)).max()))
                d2s.append(np.abs(np.diff(c[:, k], 2)).max())
    zooms = ["план %d: 1→%.2f" % (p["id"], 1 + p["zoom"]) for p in D["plans"]]
    src = "PNG до кодера" if png_range(work, 0, 0.04) is not None else "mp4 (с шумом кодера)"
    res(4, max(jit) < 0.2, src + ": центр текста гуляет по кадрам max %.3f px (от скользящего среднего 5 кадров); медленная волна "
        "от квадратичной подгонки max %.3f px (фаза пикселя при ресэмпле, у идеального ресэмпла 0,19); %s; "
        "наезд — ресэмпл Lanczos слоя плана (dsf 2), без скачка: входящий план с 1,00" % (
            max(jit), max(slow), ", ".join(zooms)))

    # 5. Безопасные зоны: всё, что отличается от чистой бумаги
    allv = frames_range(mp4, 0, D["frames"] / FPS)[::3].astype(float)
    m = (np.abs(allv - bg[None]) > 14).any(0)
    ys, xs = np.nonzero(m)
    low = m[1050:]
    lys, lxs = np.nonzero(low)
    ok5 = xs.min() >= 65 and xs.max() <= 1015 and ys.min() >= 270 and ys.max() <= 1250 and \
        (not len(lxs) or (lxs.min() >= 130 and lxs.max() <= 950))
    res(5, ok5, "содержимое x %d–%d, y %d–%d; ниже 1050: x %s" % (
        xs.min(), xs.max(), ys.min(), ys.max(), "%d–%d" % (lxs.min(), lxs.max()) if len(lxs) else "пусто"))

    # 6. Время на текст (style §6)
    def visible(p, x):
        on = x["op"]["kfs"][0][0]
        off = x.get("t_off", p["op"]["kfs"][-1][0] if len(p["op"]["kfs"]) > 1 else D["duration"])
        return on, off
    lines = []
    ok6 = True
    for p, x in texts:
        if "text" not in x and x["role"] not in ("root",):
            continue
        on, off = visible(p, x)
        n = len(x.get("text", "").split())
        need = {"translation": max(2.5, n / 3 + 0.5, 4.0 if n >= 10 else 0)}.get(x["role"], max(1.2, n / 3 + 0.5))
        if x["role"] in ("source", "label", "yassir", "root"):
            need = 1.2
        if x["role"] == "yassir":
            need = 1.5 + 0.4
        ok = off - on >= need - 1e-6
        ok6 &= ok
        lines.append("%s %.2f/%.1f%s" % ((x.get("text") or x["role"])[:18], off - on, need, "" if ok else "✗"))
    # промежуток без смены: от конца перехода до начала следующего
    ev = sorted(events)
    gaps = np.array([max(0, min(e[0] for e in ev if e[0] > a[0] + a[2] - 1e-9) - (a[0] + a[2]))
                     for a in ev if any(e[0] > a[0] + a[2] - 1e-9 for e in ev)])
    res(6, ok6 and gaps.max() <= 4.0 + 1e-6, "; ".join(lines) + "; дольше всего без смены %.2f с" % gaps.max())

    # 7. Синхрон: акустическое начало ٱهْدِنَا (R1) в готовой дорожке тем же правилом, что и замер
    #    (style §7), против начала перехода цвета на кадрах (середина 0,1-с перехода − 0,05 с)
    import audio
    au = {x["id"]: x for x in B["audio"]}
    x = audio.decode(vdir / "audio_final.wav", 2.0)
    r1, rule = audio.measure_onset(x, au["R1"]["at"] + 0.1)
    fr = frames_range(mp4, 0, 1.0, gray=False).astype(float)[:, 560:940]
    chroma = (fr.max(3) - fr.min(3)).mean((1, 2))
    lo, hi = chroma[:3].mean(), chroma[-5:].mean()
    k = int(np.argmax(chroma > (lo + hi) / 2))
    t_half = (k - 1 + ((lo + hi) / 2 - chroma[k - 1]) / (chroma[k] - chroma[k - 1])) / FPS
    lead = (t_half - 0.05) - r1
    chg = B["warnings"]
    res(7, abs(lead + 0.04) <= 0.06 and not chg,
        "ٱهْدِنَا: голос %.3f с (%s), золото начинает загораться %.3f с -> опережение %.0f мс (норма 40 ±60); "
        "остальные слова — qdc + offset_measured (%s); смены текста вне границ: %s" % (
            r1, rule, t_half - 0.05, -1000 * lead,
            ", ".join("%s %+.3f" % (k_, v["offset_measured"]) for k_, v in au.items() if "offset_measured" in v),
            chg or "нет"))

    # 8. Звук
    err = sh(["ffmpeg", "-i", str(mp4), "-af", "ebur128=peak=true", "-f", "null", "-"]).stderr
    I = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", err)[-1])
    TP = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)[-1])
    err = sh(["ffmpeg", "-i", str(mp4), "-af", "silencedetect=noise=-90dB:d=2", "-f", "null", "-"]).stderr
    sil = re.findall(r"silence_start: ([\d.]+)", err)
    pr = json.loads(sh(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(mp4)]).stdout)
    v = [x for x in pr["streams"] if x["codec_type"] == "video"][0]
    au_s = [x for x in pr["streams"] if x["codec_type"] == "audio"][0]
    dv, da = float(v["duration"]), float(au_s["duration"])
    res(8, au_s["sample_rate"] == "48000" and abs(I + 16) <= 1 and TP <= -1.5 and not sil and abs(dv - da) <= 1 / FPS,
        "48 кГц %s; I %.1f LUFS, TP %.1f dBTP; −∞ >2 с: %s; видео %.3f / звук %.3f с; %s" % (
            au_s["sample_rate"], I, TP, sil or "нет", dv, da, "; ".join(B["audio_notes"])))

    # 13. Выход
    ok13 = v["codec_name"] == "h264" and v["profile"] == "High" and v["pix_fmt"] == "yuv420p" and \
        v.get("color_primaries") == v.get("color_transfer") == v.get("color_space") == "bt709" and \
        v["r_frame_rate"] == v["avg_frame_rate"] == "30/1" and au_s["codec_name"] == "aac"
    res(13, ok13, "%s %s %s, %s/%s/%s, %s CFR (avg %s), %s %s Гц, %s кадров" % (
        v["codec_name"], v["profile"], v["pix_fmt"], v.get("color_primaries"), v.get("color_transfer"),
        v.get("color_space"), v["r_frame_rate"], v["avg_frame_rate"], au_s["codec_name"], au_s["sample_rate"],
        v.get("nb_frames")))

    # 14. Полосы: растяжка ×12, шум бумаги
    out = []
    for t, name in ((3.5, "ayah"), (28.8, "final")):
        y = frame(mp4, t, gray=True).astype(float)
        st = np.clip((y - y.mean()) * 12 + 128, 0, 255).astype(np.uint8)
        Image.fromarray(st).resize((360, 640), Image.LANCZOS).save(work / "check" / ("x12_%s.png" % name))
        pap = y[1300:1700, 150:930]
        from scipy.ndimage import gaussian_filter
        sd = (pap - gaussian_filter(pap, 12)).std()
        out.append("%s σ %.2f" % (name, sd))
    res(14, all(float(re.search(r"σ ([\d.]+)", o).group(1)) >= 0.8 for o in out), "; ".join(out) +
        " (≥0,8); кольца и ступени — глазами по x12_*.png")

    # полосы кадров вокруг смен — смотреть глазами
    keyt = sorted({round(e[0], 2) for e in events if not e[1].startswith("цвет")})
    for i, t in enumerate(keyt):
        strip(mp4, [t - 0.1, t, t + 0.1, t + 0.2, t + 0.4], work / "check" / ("s%02d_%05.2f.png" % (i, t)))

    for n, ok, msg in sorted(R):
        print("%2d %s %s" % (n, ok, msg))


if __name__ == "__main__":
    main()
