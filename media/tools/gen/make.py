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


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--work", default=None)
    ap.add_argument("--stills", default=None, help="времена через запятую: только кадры в work/stills")
    ap.add_argument("--dsf", type=int, default=2, help="deviceScaleFactor слоёв (2: наезд ресэмплом без мыла)")
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
    data = compile_sheet(sheet, tl)
    total = data["frames"] / data["fps"]
    (work / "page.html").write_text(page.html(data, sorted({p["block"]["page"] for p in data["plans"]
                                                            if p["block"]})), "utf-8")
    build = {"offsets": report, "warnings": tl.warnings, "voiced": tl.voiced(), "data": data,
             "audio": [{k: v for k, v in x.items() if k != "qdc"} for x in sheet["audio"]]}

    if a.stills:
        ts = [float(x) for x in a.stills.split(",")]
        lay = page.frames(work / "page.html", work / "stills", ts, a.dsf, ["t%06.3f.png" % t for t in ts])
        print("\n".join(report + tl.warnings), "\nраскладка:", lay)
        return

    notes = audio.build(sheet, src, total, work, vdir / "audio_final.wav")
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
    print("\n".join(report + tl.warnings + notes))
    print("раскладка:", lay)
    print("готово:", out, vdir / "cover.png")


if __name__ == "__main__":
    main()
