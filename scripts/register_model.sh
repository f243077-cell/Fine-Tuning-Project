#!/usr/bin/env bash
# Register a ru-guard GGUF in Ollama (Phase 4 onward).
#   bash scripts/register_model.sh ru-guard-0.5b             # Q4_K_M -> ollama model "ru-guard-0.5b"
#   bash scripts/register_model.sh ru-guard-0.5b q8_0        # Q8_0   -> ollama model "ru-guard-0.5b:q8_0"
#   bash scripts/register_model.sh ru-guard-1.5b-v2 q8_0     # data-v2 model (Phase 5) -> "ru-guard-1.5b-v2:q8_0"
#   REGISTER_TARGET=docker bash scripts/register_model.sh ru-guard-1.5b-v2   # inside the compose "ollama" container
# The GGUF files must be in models/ as <name>-<QUANT>.gguf. The template comes from models/Modelfile.<size>.
# In docker mode, models/ is mounted read-only at /models in the container (docker-compose.yml).
# It also pulls the demo chat model (CHAT_MODEL, default qwen2.5:1.5b-instruct) unless SKIP_CHAT_MODEL=1.
set -euo pipefail

name="${1:?usage: register_model.sh ru-guard-<size>[-vN] [q4_k_m|q8_0]}"
quant="${2:-q4_k_m}"
target="${REGISTER_TARGET:-local}"
size="${name#ru-guard-}"
size="${size%%-v*}"
# pwd -W (Git Bash on Windows) gives C:/...; docker.exe misreads /c/... when MSYS_NO_PATHCONV=1. Linux: plain pwd.
here="$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd))"
modelfile="$here/models/Modelfile.$size"
quant_upper="$(echo "$quant" | tr '[:lower:]' '[:upper:]')"
gguf="$here/models/$name-$quant_upper.gguf"

[ -f "$modelfile" ] || { echo "missing $modelfile" >&2; exit 1; }
[ -f "$gguf" ] || { echo "missing $gguf (copy it from Drive first)" >&2; exit 1; }

tag="$name"
[ "$quant" = "q4_k_m" ] || tag="$name:$quant"
tmp="$here/models/Modelfile.$name.$quant.tmp"
trap 'rm -f "$tmp"' EXIT
case "$target" in
  local)
    sed "s#^FROM .*#FROM ./$name-$quant_upper.gguf#" "$modelfile" > "$tmp"
    ollama create "$tag" -f "$tmp" < /dev/null
    ;;
  docker)
    sed "s#^FROM .*#FROM /models/$name-$quant_upper.gguf#" "$modelfile" > "$tmp"
    # Git Bash on Windows would rewrite /models/... into a Windows path without this.
    MSYS_NO_PATHCONV=1 docker compose -f "$here/docker-compose.yml" exec -T ollama \
      ollama create "$tag" -f "/models/$(basename "$tmp")" < /dev/null
    ;;
  *) echo "REGISTER_TARGET must be local or docker, got $target" >&2; exit 1 ;;
esac
echo "registered $tag from $(basename "$gguf") ($target)"

chat_model="${CHAT_MODEL:-qwen2.5:1.5b-instruct}"
if [ "${SKIP_CHAT_MODEL:-0}" != "1" ]; then
  # Up to 3 tries: the Ollama registry sometimes answers 503 after the download (nightly run 2, 2026-11-17).
  for try in 1 2 3; do
    if [ "$target" = "docker" ]; then
      docker compose -f "$here/docker-compose.yml" exec -T ollama ollama pull "$chat_model" < /dev/null && break
    else
      ollama pull "$chat_model" < /dev/null && break
    fi
    [ "$try" = 3 ] && { echo "could not pull $chat_model after 3 tries" >&2; exit 1; }
    echo "pull failed (try $try), retrying in 20 s" >&2; sleep 20
  done
  echo "pulled chat model $chat_model ($target)"
fi
