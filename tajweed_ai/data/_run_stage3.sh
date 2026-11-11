#!/bin/bash
# Этап 3 дома (12.11.2026, днём): 484 сдачи заново - с уверенностью модели
# (pred_probs/qp/np). Один процесс, 4 ядра. Остановить: Stop-Process по PID python.
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 HIFZ_RESULTS=data/stage3_results.jsonl
python scripts/hifz_eval.py --ids "$(cat data/stage3_run_ids.txt)" > data/_stage3.log 2>&1
echo DONE >> data/_stage3.log
