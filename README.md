# RU-Guard: Roman Urdu Prompt-Injection Guard

A small Qwen2.5 model, fine-tuned with QLoRA, that detects prompt injection in Roman Urdu, English, and mixed text. It runs as a local FastAPI service (`guard-api`) backed by Ollama.

Status: Phase 0 (scaffold). The full README (results, quickstart, limitations) is written in Phase 10.

- What and why: [PRD.md](PRD.md)
- How it works: [Architecture.md](Architecture.md)
- Build plan: [phases.md](phases.md)
- Diagrams: [docs/understanding/](docs/understanding/README.md)

## Dev quickstart

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
uvicorn guard.app.main:app --port 8001 --reload
```
