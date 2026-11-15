"""Chat model client (Ollama /api/chat), deterministic decoding."""

import httpx

CHAT_OPTIONS = {"temperature": 0, "top_k": 1, "seed": 0, "num_ctx": 4096, "num_predict": 256}


class OllamaChat:
    """Callable chat function over a pooled HTTP client."""

    def __init__(self, url: str, model: str, timeout: float = 180.0) -> None:
        """Create the HTTP client."""
        self.model = model
        self._http = httpx.Client(base_url=url, timeout=timeout)

    def __call__(self, messages: list[dict[str, str]]) -> str:
        """Assistant text for the messages."""
        r = self._http.post("/api/chat", json={"model": self.model, "messages": messages, "stream": False,
                                               "options": CHAT_OPTIONS, "keep_alive": "30m"})
        r.raise_for_status()
        return str(r.json()["message"]["content"])

    def healthy(self) -> bool:
        """True when Ollama lists the chat model."""
        try:
            names = {m["name"] for m in self._http.get("/api/tags", timeout=5).json().get("models", [])}
        except (httpx.HTTPError, ValueError, KeyError):
            return False
        return self.model in names or f"{self.model}:latest" in names
