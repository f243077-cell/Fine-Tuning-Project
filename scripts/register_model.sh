#!/usr/bin/env bash
# Register a ru-guard GGUF in Ollama (Phase 4 onward).
#   bash scripts/register_model.sh ru-guard-0.5b             # Q4_K_M -> ollama model "ru-guard-0.5b"
#   bash scripts/register_model.sh ru-guard-0.5b q8_0        # Q8_0   -> ollama model "ru-guard-0.5b:q8_0"
#   bash scripts/register_model.sh ru-guard-1.5b-v2 q8_0     # data-v2 model (Phase 5) -> "ru-guard-1.5b-v2:q8_0"
# The GGUF files must be in models/ as <name>-<QUANT>.gguf. The template comes from models/Modelfile.<size>.
set -euo pipefail

name="${1:?usage: register_model.sh ru-guard-<size>[-vN] [q4_k_m|q8_0]}"
quant="${2:-q4_k_m}"
size="${name#ru-guard-}"
size="${size%%-v*}"
here="$(cd "$(dirname "$0")/.." && pwd)"
modelfile="$here/models/Modelfile.$size"
quant_upper="$(echo "$quant" | tr '[:lower:]' '[:upper:]')"
gguf="$here/models/$name-$quant_upper.gguf"

[ -f "$modelfile" ] || { echo "missing $modelfile" >&2; exit 1; }
[ -f "$gguf" ] || { echo "missing $gguf (copy it from Drive first)" >&2; exit 1; }

tag="$name"
[ "$quant" = "q4_k_m" ] || tag="$name:$quant"
tmp="$here/models/Modelfile.$name.$quant.tmp"
sed "s#^FROM .*#FROM ./$name-$quant_upper.gguf#" "$modelfile" > "$tmp"
ollama create "$tag" -f "$tmp" < /dev/null
rm -f "$tmp"
echo "registered $tag from $(basename "$gguf")"
