#!/bin/bash
# Шаг 2 (13.11.2026): 599 голосовых Умар устаза -> виды пометок. 4 процесса, фоном.
# Запускает пользователь через "!" (аудио уходит в Gemini через OpenRouter).
cd "$(dirname "$0")/.."
for i in 0 1 2 3; do
  nohup python scripts/ustaz_voice_classify.py --shard $i/4 > data/_voices_$i.log 2>&1 &
done
echo "запущено 4 процесса; прогресс: wc -l data/ustaz_voice_classified.jsonl"
