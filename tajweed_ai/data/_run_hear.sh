#!/bin/bash
# Ветка «слух» (12.11.2026): весь корпус Умар устаза с вердиктом - представления слов
# (--emb) + те же поля, что этап 3. Сначала сдачи с пометками, потом остальные.
# Возобновляемо. Остановить: Stop-Process по PID python.
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 HIFZ_RESULTS=data/hear_results.jsonl
python scripts/hifz_eval.py --emb data/hear_emb --ids "$(cat data/hear_marked_ids.txt)" > data/_hear.log 2>&1
python scripts/hifz_eval.py --emb data/hear_emb >> data/_hear.log 2>&1
echo DONE >> data/_hear.log
