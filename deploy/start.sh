#!/usr/bin/env bash
# Start the hosted demo in one container (D60): Ollama, guard-api and demo-rag on localhost only,
# then the public proxy on :7860. The guard key and audit salt are made fresh at every start and never leave
# the container; the browser talks only to the proxy, which adds the key.
set -euo pipefail
cd "$(dirname "$0")/.."
GUARD_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
AUDIT_SALT="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export GUARD_API_KEY AUDIT_SALT
export OLLAMA_HOST=127.0.0.1:11434 OLLAMA_KEEP_ALIVE=24h OLLAMA_URL=http://127.0.0.1:11434

wait_for() { for _ in $(seq 1 120); do curl -sf "$1" > /dev/null && return 0; sleep 2; done; echo "timeout: $1" >&2; exit 1; }

ollama serve > /tmp/ollama.log 2>&1 &
wait_for http://127.0.0.1:11434/api/version

# Rate limiting per visitor happens in the proxy; inside the container every call comes from 127.0.0.1.
GUARD_MODEL=ru-guard-1.5b-v2 DB_PATH=/tmp/guard.db OTEL_FILE=/tmp/traces.jsonl RATE_LIMIT=100000/minute \
  OLLAMA_KEEP_ALIVE=24h uvicorn guard.app.main:app --host 127.0.0.1 --port 8001 --log-level warning &
wait_for http://127.0.0.1:8001/health

GUARD_URL=http://127.0.0.1:8001 GUARD_ENABLED=true ALLOW_GUARD_TOGGLE=true CHROMA_PATH="$CHROMA_PATH" \
  uvicorn demo_rag.app.main:app --host 127.0.0.1 --port 8002 --log-level warning &
wait_for http://127.0.0.1:8002/health

# Warm both models so the first visitor does not wait for a cold load.
curl -s -X POST http://127.0.0.1:8001/v1/scan -H "X-API-Key: $GUARD_API_KEY" -H "Content-Type: application/json" \
  -d '{"text": "warm up", "source": "user_input"}' > /dev/null || true
curl -s http://127.0.0.1:11434/api/generate -d '{"model": "qwen2.5:1.5b-instruct", "prompt": "hi", "options": {"num_predict": 1}}' > /dev/null || true

exec uvicorn deploy.proxy:app --host 0.0.0.0 --port 7860 --proxy-headers --forwarded-allow-ips='*'
