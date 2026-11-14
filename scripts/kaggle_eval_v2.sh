#!/usr/bin/env bash
# Phase 5 data-v2 loop: evaluate the four v2 GGUF files on the frozen test set inside the Kaggle session
# (Ollama on the free T4), because large files cannot be downloaded from a live Kaggle session (D49).
#   cd /kaggle/working/ru-guard && git pull && bash scripts/kaggle_eval_v2.sh
# Output: /kaggle/working/eval_v2.zip (metrics.json + predictions.jsonl per model; small).
# The chosen model is later downloaded and re-evaluated on the local CPU for the headline numbers.
set -euo pipefail

EXPORT="${EXPORT:-/kaggle/working/export}"
OUT="${OUT:-/kaggle/working/eval_v2}"
cd "$(dirname "$0")/.."

cd "$(dirname "$0")/.." && git pull -q || true
if ! command -v ollama >/dev/null; then
  command -v zstd >/dev/null || (apt-get update -qq && apt-get install -y -qq zstd >/dev/null)  # installer needs it
  curl -fsSL https://ollama.com/install.sh | sh
fi
if ! curl -s http://localhost:11434/api/version >/dev/null; then
  nohup setsid ollama serve > /tmp/ollama.log 2>&1 < /dev/null &
  for _ in $(seq 1 30); do curl -s http://localhost:11434/api/version >/dev/null && break; sleep 2; done
fi
ollama --version

pip install -q httpx pyyaml pydantic numpy >/dev/null
mkdir -p "$OUT"
for size in 0.5b 1.5b; do
  for quant in Q4_K_M Q8_0; do
    gguf="$EXPORT/ru-guard-$size-v2/gguf/ru-guard-$size-v2-$quant.gguf"
    tag="ru-guard-$size-v2:$(echo "$quant" | tr '[:upper:]' '[:lower:]')"
    sed "s#^FROM .*#FROM $gguf#" "models/Modelfile.$size" > "/tmp/Modelfile.$size.$quant"
    ollama create "$tag" -f "/tmp/Modelfile.$size.$quant"
    python evals/eval_guard.py --model "ollama:$tag" --split test --out "$OUT"
  done
done
cd "$(dirname "$OUT")" && rm -f eval_v2.zip && zip -qr eval_v2.zip "$(basename "$OUT")" && ls -lh eval_v2.zip
