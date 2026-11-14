#!/usr/bin/env bash
# Register a ru-guard GGUF in Ollama (Phase 4).
#   bash scripts/register_model.sh ru-guard-0.5b          # Q4_K_M -> ollama model "ru-guard-0.5b"
#   bash scripts/register_model.sh ru-guard-0.5b q8_0     # Q8_0   -> ollama model "ru-guard-0.5b:q8_0"
# The GGUF files must be in models/ (copied from Drive, see docs/colab/04_train.md).
set -euo pipefail

name="${1:?usage: register_model.sh ru-guard-0.5b|ru-guard-1.5b [q4_k_m|q8_0]}"
quant="${2:-q4_k_m}"
size="${name#ru-guard-}"
here="$(cd "$(dirname "$0")/.." && pwd)"
modelfile="$here/models/Modelfile.$size"
quant_upper="$(echo "$quant" | tr '[:lower:]' '[:upper:]')"
gguf="$here/models/$name-$quant_upper.gguf"

[ -f "$modelfile" ] || { echo "missing $modelfile" >&2; exit 1; }
[ -f "$gguf" ] || { echo "missing $gguf (copy it from Drive first)" >&2; exit 1; }

if [ "$quant" = "q4_k_m" ]; then
  tag="$name"
  ollama create "$tag" -f "$modelfile"
else
  tag="$name:$quant"
  tmp="$here/models/Modelfile.$size.$quant"
  sed "s#^FROM ./$name-Q4_K_M.gguf#FROM ./$name-$quant_upper.gguf#" "$modelfile" > "$tmp"
  ollama create "$tag" -f "$tmp"
  rm -f "$tmp"
fi
echo "registered $tag from $(basename "$gguf")"
