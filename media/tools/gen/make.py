"""Генератор «аят → ролик», первый заход (style §13): Reel 9:16 + обложка.

    python media/tools/gen/make.py media/videos/04_slovo_huda/sheet.json
    python media/tools/gen/make.py <sheet> --stills 0,1.9,5.9      # только контрольные кадры
    python media/tools/gen/make.py <sheet> --work <папка>           # временные файлы (кадры, звук)

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

    if a.stills:
        ts = [float(x) for x in a.stills.split(",")]
        lay = page.frames(work / "page.html", work / "stills", ts, a.dsf, ["t%06.3f.png" % t for t in ts])
        print("\n".join(report + live_notes + tl.warnings), "\nраскладка:", lay)
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
    print("\n".join(report + live_notes + tl.warnings + notes))
    print("раскладка:", lay)
    print("готово:", out, vdir / "cover.png")


if __name__ == "__main__":
    main()
