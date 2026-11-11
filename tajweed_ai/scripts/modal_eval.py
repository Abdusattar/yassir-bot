# -*- coding: utf-8 -*-
"""
Этап 2 ИИ-таджвида (11.11.2026): прогон hifz_eval.py на арендованном GPU
(Modal, посекундная оплата, $30/мес бесплатно на Starter) - чтобы не грузить
домашний компьютер на ночь.

Что уходит на Modal: скрипты tajweed_ai/scripts, страницы мусхафа
(page<N>.json мединской и dm/), записи студентов (data/umar_corpus) - в Volume
"yassir-tajweed". Токен бота НЕ уходит: check_voices.py при импорте читает
.env - в контейнере кладём пустышку. После прогона записи из Volume удаляем
(шаг 4).

Шаги (из корня tajweed_ai, после `modal setup`):
  1. modal volume create yassir-tajweed                       (один раз)
  2. modal volume put yassir-tajweed data/umar_corpus /umar_corpus
  3. modal run scripts/modal_eval.py --ids 9414,9292,...       (проба на 10)
     modal run scripts/modal_eval.py --ids-file data/stage2_ids.txt
  4. modal volume get yassir-tajweed /hifz_eval_results_gpu.jsonl data/
     modal volume rm -r yassir-tajweed /umar_corpus           (удалить записи)

Пересчёт правил по результатам GPU - дома, без инференса:
  HIFZ_RESULTS=data/hifz_eval_results_gpu.jsonl python scripts/rules_offline.py
"""
import re
from pathlib import Path

import modal

HERE = Path(__file__).resolve().parent          # tajweed_ai/scripts
PROJECT = HERE.parent.parent                    # корень репо
REMOTE_ROOT = "/root/tajweed_ai"                # ROOT в hifz_eval.py
REMOTE_DATA = f"{REMOTE_ROOT}/data"
GPU = "L4"                                      # 24 ГБ; дешевле A100, Muaalem ~0.6B влезает

_PAGE = re.compile(r"page\d+\.json")


def _not_page(p: Path) -> bool:
    """ignore для mushaf_data: берём только page<N>.json (без _ky/_uz/_zh,
    шрифтов, index.html). У каталогов нет суффикса - не отбрасываем."""
    return bool(p.suffix) and not _PAGE.fullmatch(p.name)


image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch==2.9.0", "torchaudio==2.9.0", "transformers==4.57.1",
        "quran-muaalem==0.1.0", "quran-transcript==0.5.2",
        "librosa==0.11.0", "audioread==3.1.0", "soundfile==0.13.1",
        "rapidfuzz==3.14.5", "diff-match-patch==20241021", "httpx",
    )
    .env({"HF_HOME": f"{REMOTE_DATA}/_hf", "PYTHONIOENCODING": "utf-8",
          "HIFZ_RESULTS": f"{REMOTE_DATA}/hifz_eval_results_gpu.jsonl"})
    .add_local_dir(str(HERE), f"{REMOTE_ROOT}/scripts",
                   ignore=lambda p: "__pycache__" in p.parts)
    .add_local_dir(str(PROJECT / "mushaf_data"), "/root/mushaf_data", ignore=_not_page)
)

app = modal.App("yassir-tajweed-eval")
vol = modal.Volume.from_name("yassir-tajweed", create_if_missing=True)


@app.function(image=image, gpu=GPU, volumes={REMOTE_DATA: vol}, timeout=6 * 3600)
def run(ids: str = "", limit: int = 0):
    import subprocess

    # Пустышка вместо секретов: check_voices.py читает .env при импорте.
    Path(f"{REMOTE_ROOT}/.env").write_text("BOT_TOKEN=x\nSCALING_CHAT_ID=0\n", encoding="utf-8")
    cmd = ["python", f"{REMOTE_ROOT}/scripts/hifz_eval.py", "--device", "cuda"]
    if ids:
        cmd += ["--ids", ids]
    if limit:
        cmd += ["--limit", str(limit)]
    try:
        subprocess.run(cmd, check=True)
    finally:
        vol.commit()   # что успело посчитаться - сохраняем и при падении


@app.local_entrypoint()
def main(ids: str = "", ids_file: str = "", limit: int = 0):
    if ids_file:
        lines = Path(ids_file).read_text(encoding="utf-8").splitlines()
        ids = next(l for l in lines if "," in l).strip()
    run.remote(ids, limit)
