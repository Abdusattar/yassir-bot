"""Гейт №0 — декодирует эталонные (заведомо верные) чтения Хусари/Афаси
через wav2vec2-quran-phonetics. См. tajweed_ai/README.md и
wiki/ai_tajweed_audio.md за контекстом."""
import json
import torch
import librosa
from pathlib import Path
from transformers import Wav2Vec2Processor, Wav2Vec2ForCTC

ROOT = Path(__file__).resolve().parent.parent
CONTROL = ROOT / "audio" / "control"
DATA = ROOT / "data"

MODEL = "TBOGamer22/wav2vec2-quran-phonetics"
proc = Wav2Vec2Processor.from_pretrained(MODEL)
model = Wav2Vec2ForCTC.from_pretrained(MODEL)
model.eval()

def decode(path):
    audio, sr = librosa.load(path, sr=16000, mono=True)
    inputs = proc(audio, sampling_rate=16000, return_tensors="pt", padding=True)
    with torch.no_grad():
        logits = model(inputs.input_values).logits
    pred_ids = torch.argmax(logits, dim=-1)
    text = proc.batch_decode(pred_ids)[0]
    return text

files = {
    "husary_106": CONTROL / "husary_002106.mp3",
    "husary_107": CONTROL / "husary_002107.mp3",
    "husary_108": CONTROL / "husary_002108.mp3",
    "husary_109": CONTROL / "husary_002109.mp3",
    "husary_110": CONTROL / "husary_002110.mp3",
    "husary_111": CONTROL / "husary_002111.mp3",
    "husary_112": CONTROL / "husary_002112.mp3",
    "afasy_106_112": CONTROL / "afasy_106_112.mp3",
}

out = {}
for name, path in files.items():
    print("decoding", name)
    out[name] = decode(str(path))

with open(DATA / "gate0_decodes.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("done")
