# Hugging Face Space (Docker SDK) for the public RU-Guard demo (D60, docs/DEPLOY.md).
# The Space holds only this file and README.md: it clones the public repository at REF, so the Space and the
# repository cannot drift. Everything runs in one container on the free CPU tier (2 vCPU, 16 GB).

# --- 1. Flutter web build, calling its own origin (no key in the build) -----------------------------------
FROM debian:bookworm-slim AS web
RUN apt-get update && apt-get install -y --no-install-recommends git curl unzip xz-utils ca-certificates \
    && rm -rf /var/lib/apt/lists/*
ARG REF=main
ARG FLUTTER=3.47.7
RUN git clone --depth 1 --branch "$FLUTTER" https://github.com/flutter/flutter.git /flutter
ENV PATH=/flutter/bin:$PATH
RUN git clone --depth 1 --branch "$REF" https://github.com/f243077-cell/Roman-Urdu-Guard-Model.git /src
WORKDIR /src/flutter_app
RUN flutter config --no-analytics --enable-web && flutter pub get \
    && flutter build web --release --dart-define=GUARD_URL=/guard --dart-define=DEMO_URL=/demo

# --- 2. Services: Ollama + guard-api + demo-rag + proxy -----------------------------------------------------
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git zstd \
    && rm -rf /var/lib/apt/lists/*
ARG OLLAMA_VERSION=0.32.15
RUN curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION="$OLLAMA_VERSION" sh

RUN useradd --create-home --uid 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PYTHONUNBUFFERED=1 \
    OLLAMA_MODELS=/home/user/.ollama/models CHROMA_PATH=/home/user/chroma TIKTOKEN_CACHE_DIR=/home/user/.tiktoken
WORKDIR /home/user/app

ARG REF=main
RUN git clone --depth 1 --branch "$REF" https://github.com/f243077-cell/Roman-Urdu-Guard-Model.git . \
    && pip install --no-cache-dir --user --timeout 120 --retries 10 -r requirements.txt -r requirements-demo.txt

# Guard model from Release model-v1 (hash checked), registered in Ollama together with the chat model.
ARG GGUF=ru-guard-1.5b-v2-Q4_K_M.gguf
ARG GGUF_SHA256=52b5472abc1419f8c43645a733dd4dd9ee9e6e8b1be7de974d61dd988f8022e7
RUN mkdir -p models && curl -fL --retry 5 -o "models/$GGUF" \
      "https://github.com/f243077-cell/Roman-Urdu-Guard-Model/releases/download/model-v1/$GGUF" \
    && echo "$GGUF_SHA256  models/$GGUF" | sha256sum -c - \
    && (ollama serve > /tmp/ollama-build.log 2>&1 &) \
    && for i in $(seq 1 30); do curl -sf http://127.0.0.1:11434/api/version > /dev/null && break; sleep 2; done \
    && bash scripts/register_model.sh ru-guard-1.5b-v2 \
    && rm -f "models/$GGUF"

# Embedding model, tokenizer and the demo index (with the poisoned documents, so the document check has work).
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" \
    && python docker/fetch_embedding_model.py \
    && python -m demo_rag.ingest --guard off

COPY --from=web --chown=user /src/flutter_app/build/web /home/user/app/web
EXPOSE 7860
CMD ["bash", "deploy/start.sh"]
