"""Генератор «аят → ролик», первый заход (style §13): Reel 9:16 + обложка.

    python media/tools/gen/make.py media/videos/04_slovo_huda/sheet.json
    python media/tools/gen/make.py <sheet> --stills 0,1.9,5.9      # только контрольные кадры
    python media/tools/gen/make.py <sheet> --proof                  # СУХОЙ ПРОГОН: звук, лист, кадры на всех
                                                                    # стыках -> work/proof.png + build.json,
                                                                    # затем check.py --dry (секунды, без рендера)
    python media/tools/gen/make.py <sheet> --work <папка>           # временные файлы (кадры, звук)

Правило (06.10): полная сборка — только после зелёного сухого прогона и просмотра proof.png глазами.

Выход рядом с листом: <version>.mp4, cover.png, audio_final.wav. Порядок: лист -> замер звука ->
шкала -> страница render(t) -> кадры Playwright -> звук -> ffmpeg (style §12) -> обложка.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import audio  # noqa: E402
import page  # noqa: E402
from compile import compile_sheet  # noqa: E402
from timeline import Timeline  # noqa: E402


def assemble(frames_dir, wav, total, out):
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-framerate", "30", "-i", str(Path(frames_dir) / "%05d.png"), "-i", str(wav),
        "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",  # ffmpeg 8: теги кадра
        "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "18", "-r", "30", "-fps_mode", "cfr",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", "%.6f" % total, "-movflags", "+faststart", str(out)],
        check=True)


def yuv_means(d):
    """Средние U, V (bt709, 8 бит) по кадрам папки — проверка «нет синего сдвига» (style §1 п. 4)."""
    import numpy as np
    from PIL import Image
    fs = sorted(Path(d).glob("*.png"))[::10]
    rgb = np.stack([np.asarray(Image.open(f).convert("RGB").resize((270, 480)), float) for f in fs])
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    y = .2126 * r + .7152 * g + .0722 * b
    return 128 + (b - y).mean() / 1.8556 * 224 / 255, 128 + (r - y).mean() / 1.5748 * 224 / 255


def sheet_notes(data):
    """Предупреждения листа до рендера: время на текст ниже нормы (style §6) и два текста, делящие одно
    место (style §5: уход, потом вход). То же считает check.py п. 6, но здесь — за секунды, до кадров."""
    notes = []
    area = {"hook": "верх", "question": "верх", "translation": "низ", "line": "низ", "root_line": "низ"}
    for p in data["plans"]:
        end = p["op"]["kfs"][-1][0] if len(p["op"]["kfs"]) > 1 else data["duration"]
        items = []
        for x in p["texts"]:
            if "text" not in x:
                continue
            on, off = x["t_on"], x.get("t_off", end)
            fo = x["op"]["kfs"][-1][2] if "t_off" in x else 0
            n, role = len(x["text"].split()), x["role"]
            need = {"translation": max(2.5, n / 3 + 0.5, 4.0 if n >= 10 else 0)}.get(role, max(1.2, n / 3 + 0.5))
            if role in ("source", "label", "yassir", "root"):
                need = 1.2
            if role == "yassir":
                need = 1.9
            if off - on < need - 1e-6:
                notes.append("время на текст: «%s» %.2f с < нормы %.1f (план %d)" % (x["text"][:30], off - on, need, p["id"]))
            items.append((on, off + fo, area.get(role, role), x["text"][:30]))
        items.sort()
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if a[2] == b[2] and a[3] != b[3] and b[0] < a[1] - 0.05:
                    notes.append("наложение: «%s» и «%s» делят место (%s) в %.2f–%.2f (план %d) — style §5: уход, потом вход"
                                 % (a[3], b[3], a[2], b[0], a[1], p["id"]))
    return notes


def proof_times(data):
    """Кадры для контактного листа: кадр 0, конец, и у каждого события (план, текст, светление) — кадр до,
    середина перехода и кадр после. Ловит каши на стыках и мигание — то, что лист не видит."""
    fps = data["fps"]
    ts = {0.0, data["duration"] - 0.3}
    ev = []
    for p in data["plans"]:
        ev += [(k[0], k[2]) for k in p["op"]["kfs"]]
        if p["live"]:
            ev += [(k[0], k[2]) for k in p["live"]["bright"]["kfs"]]
        for x in p["texts"]:
            ev += [(k[0], k[2]) for k in x["op"]["kfs"]]
    for t, d in ev:
        ts.update([t - 1 / fps, t + d / 2, t + d + 1 / fps] if d > 0 else [t - 1 / fps, t + 1 / fps])
    return sorted({round(float(min(max(t, 0.0), data["duration"] - 1 / fps)), 3) for t in ts})  # float: значения из numpy ломают JS


def contact_sheet(frames_dir, times, out, cols=8, w=180):
    from PIL import Image, ImageDraw
    ims = []
    for t in times:
        im = Image.open(frames_dir / ("t%06.3f.png" % t)).convert("RGB")
        im = im.resize((w, round(w * im.height / im.width)), Image.LANCZOS)
        ImageDraw.Draw(im).rectangle([0, 0, 52, 14], fill=(0, 0, 0))
        ImageDraw.Draw(im).text((2, 1), "%.2f" % t, fill=(255, 255, 255))
        ims.append(im)
    h = ims[0].height
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (40, 40, 40))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(out)


def cut_live(sheet, timeline, work):
    """Живые клипы -> PNG 30 к/с (кроп, 1080×1920, тёплая коррекция); холодный кадр греем ещё шагом."""
    out, notes = {}, []
    for p in sheet["plans"]:
        L = p.get("live")
        if not L:
            continue
        d = work / ("live_%d" % p["plan"])
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        at = timeline.t(L.get("at", p["in"]["at"]))
        end = timeline.t(p["out"]["at"]) + p["out"]["dur"]
        src = Path(L["src"])
        src = src if src.is_absolute() else timeline_root() / src
        x, y, w, h = L.get("crop") or [0, 0, 0, 0]
        crop = "crop=%d:%d:%d:%d," % (w, h, x, y) if w else ""
        for bs in (-0.10, -0.15, -0.20):  # не больше двух лишних шагов bs −0,05
            warm = ",colorbalance=rs=.05:rm=.03:bs=%.2f:bm=-.05" % bs if L.get("warm") else ""
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(L.get("in", 0)), "-i", str(src),
                            "-t", "%.3f" % (end - at + 0.1), "-vf",
                            crop + "scale=1080:1920:flags=lanczos,fps=30" + warm, "-start_number", "0",
                            str(d / "%05d.png")], check=True)
            u, v = yuv_means(d)
            if not L.get("warm") or u <= 128:
                break
        notes.append("живой кадр план %d: %s, UAVG %.1f VAVG %.1f%s" % (
            p["plan"], src.name, u, v, " (bs %.2f)" % bs if L.get("warm") else ""))
        out[p["plan"]] = (d.as_uri() + "/", len(list(d.glob("*.png"))))
    return out, notes


def timeline_root():
    from timeline import ROOT_DIR
    return ROOT_DIR


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--work", default=None)
    ap.add_argument("--stills", default=None, help="времена через запятую: только кадры в work/stills")
    ap.add_argument("--proof", action="store_true", help="сухой прогон: кадры на всех стыках -> work/proof.png, звук и build.json без рендера")
    ap.add_argument("--dsf", type=int, default=4, help="deviceScaleFactor слоёв (наезд — ресэмпл Lanczos, 4: волна центра <0,2 px)")
    ap.add_argument("--keep-frames", action="store_true")
    a = ap.parse_args()

    sheet_path = Path(a.sheet).resolve()
    sheet = json.loads(sheet_path.read_text("utf-8"))
    vdir = sheet_path.parent
    work = Path(a.work) if a.work else Path(tempfile.gettempdir()) / "yassir_gen" / sheet["id"]
    cache = work.parent / "cache"
    work.mkdir(parents=True, exist_ok=True)

    tl = Timeline(sheet, cache)
    src, report = audio.prepare(sheet, cache)       # offset_measured в отрезки листа
    live, live_notes = cut_live(sheet, tl, work)
    data = compile_sheet(sheet, tl, live)
    total = data["frames"] / data["fps"]
    (work / "page.html").write_text(page.html(data, sorted({p["block"]["page"] for p in data["plans"]
                                                            if p["block"]})), "utf-8")
    build = {"offsets": report + live_notes, "warnings": tl.warnings, "voiced": tl.voiced(), "data": data,
             "audio": [{k: v for k, v in x.items() if k != "qdc"} for x in sheet["audio"]]}

    s_notes = sheet_notes(data)
    if a.stills or a.proof:
        if a.proof:
            ts = proof_times(data)
            lay = page.frames(work / "page.html", work / "proof", ts, 2, ["t%06.3f.png" % t for t in ts])
            contact_sheet(work / "proof", ts, work / "proof.png")
            notes = audio.build(sheet, src, total, work, vdir / "audio_final.wav", vdir)
            build.update(layout=lay, audio_notes=notes)
            (work / "build.json").write_text(json.dumps(build, ensure_ascii=False, indent=1), "utf-8")
            print("контактный лист: %s (%d кадров)" % (work / "proof.png", len(ts)))
        else:
            ts = [float(x) for x in a.stills.split(",")]
            lay = page.frames(work / "page.html", work / "stills", ts, a.dsf, ["t%06.3f.png" % t for t in ts])
        print("\n".join(report + live_notes + tl.warnings + tl.notes + s_notes), "\nраскладка:", lay)
        if tl.warnings or s_notes:
            print("ПРЕДУПРЕЖДЕНИЯ ЛИСТА: %d — исправить до полной сборки" % (len(tl.warnings) + len(s_notes)))
        return

    notes = audio.build(sheet, src, total, work, vdir / "audio_final.wav", vdir)
    fdir = work / "frames"
    shutil.rmtree(fdir, ignore_errors=True)
    lay = page.frames(work / "page.html", fdir, [i / data["fps"] for i in range(data["frames"])], a.dsf)
    out = vdir / ("%s.mp4" % sheet.get("version", "draft"))
    assemble(fdir, vdir / "audio_final.wav", total, out)
    if not a.keep_frames:
        shutil.rmtree(fdir, ignore_errors=True)
    page.cover(sheet, work, vdir / "cover.png")
    build.update(layout=lay, audio_notes=notes)
    (work / "build.json").write_text(json.dumps(build, ensure_ascii=False, indent=1), "utf-8")
    print("\n".join(report + live_notes + tl.warnings + tl.notes + s_notes + notes))
    print("раскладка:", lay)
    print("готово:", out, vdir / "cover.png")


if __name__ == "__main__":
    main()
