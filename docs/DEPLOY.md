# Hosted demo (Hugging Face Space)

One free Hugging Face Space (Docker, CPU basic: 2 vCPU, 16 GB) runs the whole demo in one container (decision D60):

```
browser ──https──> proxy :7860 (deploy/proxy.py) ──> guard-api :8001 ──> Ollama :11434 (ru-guard-1.5b-v2, qwen2.5:1.5b-instruct)
  (Flutter web,                 adds the API key        demo-rag  :8002 ──┘
   same origin)                 rate limits per visitor
```

## How the API key is kept secret

- The web app is built with `GUARD_URL=/guard` and `DEMO_URL=/demo` and **no key**; it calls its own origin, so there is no CORS and nothing secret in the JavaScript (checked: the key is in 0 files of the build).
- `deploy/start.sh` creates a new `GUARD_API_KEY` and `AUDIT_SALT` at every start. They exist only inside the container; guard-api and demo-rag listen on `127.0.0.1` only.
- The proxy adds the key to scans and drops any key a browser sends. It exposes only `/guard/health`, `/guard/v1/scan`, `/demo/health`, `/demo/chat`, `/demo/chat/stream` (no `/v1/stats`, no batch, no API docs).
- Limits per visitor (first `X-Forwarded-For` address): 30 scans and 6 chat questions a minute; at most 2 chat answers run at once (`SCANS_PER_MINUTE`, `CHATS_PER_MINUTE`, `CHAT_CONCURRENCY`). Requests over 64 KB are refused.

## Visitors do not see each other's work

The playground's history is kept in browser memory only (one tab, gone on reload). demo-rag answers each question on its own (no shared conversation). guard-api's audit log stores a keyed hash and the length, never the text; the database is in `/tmp` and is lost when the Space restarts. The only shared numbers, `/v1/stats`, are not reachable from outside.

## Create or update the Space

1. On huggingface.co: New Space, SDK **Docker**, template **Blank**, hardware **CPU basic (free)**, visibility Public.
2. Add the two files from `deploy/space/`: `Dockerfile` and `README.md` (its front matter sets `sdk: docker` and `app_port: 7860`).
3. The Space builds by itself (about 20 to 40 minutes: Flutter SDK, Python packages, Ollama, two 1 GB models). The Dockerfile clones this repository at `REF` (default `main`), so a code change reaches the Space with **Settings, Factory rebuild**.

No secrets need to be set in the Space settings.

## Limits of the free tier

CPU only: a scan takes about 1 s, a chat answer 30 to 90 s, and visitors queue. The Space sleeps after a period without visitors; the first visit after that waits for the start (a few minutes). Disk is not kept between restarts.

## Local check of the same setup

```bash
cd flutter_app && MSYS_NO_PATHCONV=1 flutter build web --release --dart-define=GUARD_URL=/guard --dart-define=DEMO_URL=/demo
cd .. && GUARD_API_KEY=<key of the local guard-api> WEB_DIR=flutter_app/build/web uvicorn deploy.proxy:app --port 7860
```

`MSYS_NO_PATHCONV=1` matters in Git Bash on Windows: without it `/guard` is rewritten to `C:/Program Files/Git/guard`. Checked on 2026-11-17 against the local stack: page loads with "Guard online", a Roman Urdu attack is blocked through `/guard/v1/scan` without a key from the browser, the chat stream arrives through `/demo/chat/stream`, `/guard/v1/stats` returns 404.
