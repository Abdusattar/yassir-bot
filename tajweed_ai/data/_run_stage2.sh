#!/bin/bash
# Этап 2 дома (11.11.2026): ждём конца скачивания, затем hifz_eval на 4 ядрах.
# Сначала сдачи с пометками (самое ценное к утру), потом чистые.
cd "$(dirname "$0")/.."
until grep -q "Готово\|Traceback" data/_fetch_stage2.log; do sleep 30; done
export PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 HIFZ_RESULTS=data/hifz_eval_results_stage2.jsonl
IDS=$(sed -n 2p data/stage2_ids.txt)
MARKED=$(python - "$IDS" <<'PY'
import json,sys
from pathlib import Path
out=[]
for i in sys.argv[1].split(","):
    p=Path("data/umar_corpus")/i/"meta.json"
    if p.exists() and (json.loads(p.read_text(encoding="utf-8")).get("error_words") or []): out.append(i)
print(",".join(out))
PY
)
python scripts/hifz_eval.py --ids "$MARKED" > data/_stage2_marked.log 2>&1
python scripts/hifz_eval.py --ids "$IDS" > data/_stage2_all.log 2>&1
echo DONE >> data/_stage2_all.log
