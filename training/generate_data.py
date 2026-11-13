"""Generate synthetic rows with Qwen2.5-7B-Instruct (4-bit) on Colab; resumable JSONL shards per cell.

Run on Colab (see docs/colab/02_generate.md):
    python -m training.generate_data --config training/configs/generate.yaml --out <drive dir>
Local smoke test without a model:
    python -m training.generate_data --config training/configs/generate.yaml --out <dir> --dry-run
"""

import argparse
import hashlib
import json
import logging
import math
import os
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from training.gen_prompts import GENERATOR_SYSTEM, build_user_prompt
from training.jsonl import read_rows
from training.schemas import AttackType, DataRow, Source, Surface

log = logging.getLogger("generate_data")

Messages = list[dict[str, str]]
GenerateFn = Callable[[list[Messages], list[int]], list[str]]


class GenerateConfig(BaseModel):
    """Settings from training/configs/generate.yaml."""

    backend: str = "vllm"
    vllm_model: str = "Qwen/Qwen2.5-7B-Instruct-AWQ"
    vllm_quantization: str | None = "awq"
    vllm_enforce_eager: bool = False
    hf_model: str = "Qwen/Qwen2.5-7B-Instruct"
    hf_batch_size: int = 6
    max_model_len: int = 4096
    gpu_memory_utilization: float = 0.90
    seed: int = 1234
    temperature: float = 0.9
    top_p: float = 0.95
    max_new_tokens: int = 1024
    items_per_call: int = 5
    shots: int = 3
    batch_prompts: int = 64
    max_attempt_factor: float = 3.0
    raw_total: int = 6600
    injection_share: float = 0.5
    hard_negative_share_of_safe: float = 0.5
    surface_share: dict[str, float]
    source_share: dict[str, float]
    seeds_path: str = "data/seeds/seeds.jsonl"


@dataclass(frozen=True)
class Cell:
    """One generation cell (label x attack_type x surface x source x hard_negative) and its target."""

    label: str
    attack_type: str | None
    surface: str
    source: str
    hard_negative: bool
    target: int

    @property
    def key(self) -> str:
        """Stable cell name used for shard files and row ids."""
        kind = self.attack_type if self.label == "INJECTION" else ("hn" if self.hard_negative else "plain")
        prefix = "inj" if self.label == "INJECTION" else "safe"
        return f"{prefix}-{kind}-{self.surface}-{self.source}"


def load_config(path: Path) -> GenerateConfig:
    """Read and validate the yaml config."""
    return GenerateConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def allocate(total: int, shares: dict[str, float]) -> dict[str, int]:
    """Split total by shares with largest-remainder rounding (sums exactly to total)."""
    norm = sum(shares.values())
    raw = {k: total * v / norm for k, v in shares.items()}
    out = {k: math.floor(v) for k, v in raw.items()}
    rest = total - sum(out.values())
    for k in sorted(raw, key=lambda k: (raw[k] - out[k], k), reverse=True)[:rest]:
        out[k] += 1
    return out


def _split_surface_source(total: int, cfg: GenerateConfig) -> dict[tuple[str, str], int]:
    """Allocate a count across surface x source cells."""
    shares = {f"{su}|{so}": cfg.surface_share[su] * cfg.source_share[so]
              for su in cfg.surface_share for so in cfg.source_share}
    return {tuple(k.split("|")): v for k, v in allocate(total, shares).items()}  # type: ignore[misc]


def plan_cells(cfg: GenerateConfig) -> list[Cell]:
    """All cells with target counts summing to cfg.raw_total."""
    for name, shares in (("surface_share", cfg.surface_share), ("source_share", cfg.source_share)):
        valid = {s.value for s in (Surface if name == "surface_share" else Source)}
        if set(shares) != valid:
            raise ValueError(f"{name} keys must be exactly {sorted(valid)}")
    inj_total = round(cfg.raw_total * cfg.injection_share)
    cells: list[Cell] = []
    per_attack = allocate(inj_total, {a.value: 1.0 for a in AttackType})
    for attack, n in per_attack.items():
        for (su, so), k in _split_surface_source(n, cfg).items():
            cells.append(Cell("INJECTION", attack, su, so, False, k))
    safe = allocate(cfg.raw_total - inj_total, {"hn": cfg.hard_negative_share_of_safe,
                                                 "plain": 1 - cfg.hard_negative_share_of_safe})
    for kind, n in safe.items():
        for (su, so), k in _split_surface_source(n, cfg).items():
            cells.append(Cell("SAFE", None, su, so, kind == "hn", k))
    return [c for c in cells if c.target > 0]


def cell_seed(base: int, key: str, attempt: int) -> int:
    """Deterministic per-call seed from the base seed, cell key, and attempt number."""
    digest = hashlib.sha256(f"{base}|{key}|{attempt}".encode()).hexdigest()
    return int(digest[:8], 16)


def pick_examples(cell: Cell, seeds: list[DataRow], k: int, rng: random.Random) -> list[DataRow]:
    """Few-shot seeds of the same category; same language and source first, order randomized."""
    if cell.label == "INJECTION":
        pool = [r for r in seeds if r.label == "INJECTION" and r.attack_type == cell.attack_type]
    else:
        pool = [r for r in seeds if r.label == "SAFE" and r.hard_negative == cell.hard_negative]
    pool = pool[:]
    rng.shuffle(pool)
    # Same language family first (en vs Roman Urdu), then same source; ties stay random.
    pool.sort(key=lambda r: ((r.surface == "en") != (cell.surface == "en"), r.source != cell.source))
    picked = pool[:k]
    rng.shuffle(picked)
    return picked


def build_prompt(cell: Cell, seeds: list[DataRow], cfg: GenerateConfig, attempt: int) -> tuple[Messages, int]:
    """Chat messages and sampling seed for one generation call."""
    s = cell_seed(cfg.seed, cell.key, attempt)
    rng = random.Random(s)
    user = build_user_prompt(
        label=cell.label, attack_type=cell.attack_type, surface=cell.surface, source=cell.source,
        hard_negative=cell.hard_negative, examples=pick_examples(cell, seeds, cfg.shots, rng),
        n=cfg.items_per_call, rng=rng,
    )
    return [{"role": "system", "content": GENERATOR_SYSTEM}, {"role": "user", "content": user}], s


def _item_text(item: object) -> str:
    """Turn one parsed item into text (objects become compact JSON, as tool outputs)."""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, (dict, list)):
        return json.dumps(item, ensure_ascii=False)
    return ""


def parse_items(raw: str) -> list[str]:
    """Extract generated examples from model output: a JSON array, else bullet/numbered lines."""
    items: list[str] = []
    start, end = raw.find("["), raw.rfind("]")
    if start != -1 and end > start:
        try:
            parsed = json.loads(raw[start:end + 1])
            if isinstance(parsed, list):
                items = [_item_text(x) for x in parsed]
        except json.JSONDecodeError:
            items = []
    if not items:
        for line in raw.splitlines():
            line = line.strip().lstrip("-*0123456789.) ").strip().strip('",')
            if len(line) > 10 and not line.startswith(("```", "[", "]")):
                items.append(line)
    seen: set[str] = set()
    out = []
    for t in items:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def count_lines(path: Path) -> int:
    """Number of non-empty lines in a shard (0 if missing)."""
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def append_rows(path: Path, rows: list[DataRow]) -> None:
    """Append rows to a shard and flush to disk (safe against Colab disconnects)."""
    with path.open("a", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r.model_dump(mode="json"), ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def make_rows(cell: Cell, texts: list[str], start_idx: int) -> list[DataRow]:
    """Validated synthetic rows for one cell; invalid items are skipped."""
    rows = []
    for i, text in enumerate(texts):
        try:
            rows.append(DataRow(
                id=f"syn-{cell.key}-{start_idx + len(rows):05d}", text=text, source=cell.source,
                label=cell.label, attack_type=cell.attack_type, surface=cell.surface,
                origin="synthetic", hard_negative=cell.hard_negative,
            ))
        except ValidationError:
            log.warning("skipped invalid item %d for %s", i, cell.key)
    return rows


def _load_state(path: Path) -> dict[str, int]:
    """Attempts already made per cell (for resume)."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_state(path: Path, attempts: dict[str, int]) -> None:
    """Write attempts per cell atomically."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(attempts, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def run(cfg: GenerateConfig, seeds: list[DataRow], generate: GenerateFn, out_dir: Path,
        max_calls: int | None = None) -> dict[str, int]:
    """Generate until every cell reaches its target (or its attempt cap); return counts per cell."""
    shard_dir = out_dir / "shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    cells = plan_cells(cfg)
    counts = {c.key: count_lines(shard_dir / f"{c.key}.jsonl") for c in cells}
    state_path = out_dir / "state.json"
    attempts = _load_state(state_path)
    calls = 0
    while True:
        batch: list[tuple[Cell, int]] = []
        for c in cells:
            cap = math.ceil(c.target / cfg.items_per_call * cfg.max_attempt_factor)
            need = math.ceil(max(0, c.target - counts[c.key]) / cfg.items_per_call)
            room = cap - attempts.get(c.key, 0)
            for _ in range(min(need, room)):
                batch.append((c, attempts.get(c.key, 0)))
                attempts[c.key] = attempts.get(c.key, 0) + 1
                if len(batch) >= cfg.batch_prompts:
                    break
            if len(batch) >= cfg.batch_prompts:
                break
        if max_calls is not None:
            batch = batch[: max(0, max_calls - calls)]
        if not batch:
            break
        prompts, seeds_list = zip(*(build_prompt(c, seeds, cfg, a) for c, a in batch))
        outputs = generate(list(prompts), list(seeds_list))
        for (c, _), raw in zip(batch, outputs):
            texts = parse_items(raw)[: max(0, c.target - counts[c.key])]
            rows = make_rows(c, texts, counts[c.key])
            append_rows(shard_dir / f"{c.key}.jsonl", rows)
            counts[c.key] += len(rows)
        calls += len(batch)
        _save_state(state_path, attempts)
        log.info("calls %d, rows %d / %d", calls, sum(counts.values()), cfg.raw_total)
    short = {c.key: counts[c.key] for c in cells if counts[c.key] < c.target}
    if short:
        log.warning("cells below target: %s", short)
    return counts


def make_vllm_backend(cfg: GenerateConfig) -> GenerateFn:
    """vLLM backend (AWQ 4-bit checkpoint)."""
    from vllm import LLM, SamplingParams

    llm = LLM(model=cfg.vllm_model, quantization=cfg.vllm_quantization, dtype="half", seed=cfg.seed,
              gpu_memory_utilization=cfg.gpu_memory_utilization, enforce_eager=cfg.vllm_enforce_eager,
              max_model_len=cfg.max_model_len)

    def generate(prompts: list[Messages], seeds: list[int]) -> list[str]:
        """Sample one completion per prompt."""
        params = [SamplingParams(temperature=cfg.temperature, top_p=cfg.top_p,
                                 max_tokens=cfg.max_new_tokens, seed=s) for s in seeds]
        outs = llm.chat(prompts, sampling_params=params, use_tqdm=False)
        return [o.outputs[0].text for o in outs]

    return generate


def make_hf_backend(cfg: GenerateConfig) -> GenerateFn:
    """Transformers + bitsandbytes 4-bit NF4 fallback backend."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tok = AutoTokenizer.from_pretrained(cfg.hf_model)
    tok.padding_side = "left"
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                             bnb_4bit_compute_dtype=torch.float16)
    model = AutoModelForCausalLM.from_pretrained(cfg.hf_model, quantization_config=bnb, device_map="auto",
                                                 dtype=torch.float16)
    model.eval()

    def generate(prompts: list[Messages], seeds: list[int]) -> list[str]:
        """Sample one completion per prompt in small batches."""
        outs: list[str] = []
        for i in range(0, len(prompts), cfg.hf_batch_size):
            chunk = prompts[i:i + cfg.hf_batch_size]
            texts = [tok.apply_chat_template(m, tokenize=False, add_generation_prompt=True) for m in chunk]
            enc = tok(texts, return_tensors="pt", padding=True).to(model.device)
            torch.manual_seed(seeds[i])
            with torch.no_grad():
                out = model.generate(**enc, do_sample=True, temperature=cfg.temperature, top_p=cfg.top_p,
                                     max_new_tokens=cfg.max_new_tokens, pad_token_id=tok.pad_token_id)
            outs.extend(tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True))
        return outs

    return generate


def library_versions() -> dict[str, str]:
    """Versions of the generation stack, recorded in the manifest so they can be pinned."""
    import importlib.metadata as md

    out = {}
    for name in ("vllm", "transformers", "torch", "bitsandbytes", "accelerate", "pydantic", "PyYAML"):
        try:
            out[name] = md.version(name)
        except md.PackageNotFoundError:
            out[name] = "not installed"
    return out


def write_manifest(out_dir: Path, cfg: GenerateConfig, config_path: Path, counts: dict[str, int],
                   started: float, backend: str) -> None:
    """Record what produced the shards (config hash, model, versions, counts)."""
    manifest = {
        "backend": backend,
        "model": cfg.vllm_model if backend == "vllm" else cfg.hf_model,
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "config": cfg.model_dump(),
        "versions": library_versions(),
        "started_unix": int(started),
        "finished_unix": int(time.time()),
        "rows_total": sum(counts.values()),
        "rows_per_cell": counts,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")


def dry_run(cfg: GenerateConfig, seeds: list[DataRow], out_dir: Path, n: int) -> Path:
    """Write the first n prompts (one per cell) to a preview file; no model needed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "prompts_preview.txt"
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for cell in plan_cells(cfg)[:: max(1, len(plan_cells(cfg)) // max(1, n))][:n]:
            messages, s = build_prompt(cell, seeds, cfg, 0)
            f.write(f"===== {cell.key} (target {cell.target}, seed {s})\n{messages[1]['content']}\n\n")
    return path


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="output directory (Drive on Colab)")
    ap.add_argument("--backend", choices=["vllm", "hf"], help="override the config backend")
    ap.add_argument("--max-calls", type=int, help="stop after this many generation calls (smoke test)")
    ap.add_argument("--dry-run", action="store_true", help="write prompt previews only, no model")
    ap.add_argument("--preview", type=int, default=8, help="prompts to preview with --dry-run")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config(args.config)
    seeds, errors = read_rows(Path(cfg.seeds_path))
    if errors:
        log.error("seed file has errors: %s", errors[:3])
        return 1
    cells = plan_cells(cfg)
    log.info("%d cells, %d target rows", len(cells), sum(c.target for c in cells))
    if args.dry_run:
        log.info("wrote %s", dry_run(cfg, seeds, args.out, args.preview))
        return 0
    backend = args.backend or cfg.backend
    started = time.time()
    generate = make_vllm_backend(cfg) if backend == "vllm" else make_hf_backend(cfg)
    counts = run(cfg, seeds, generate, args.out, args.max_calls)
    write_manifest(args.out, cfg, args.config, counts, started, backend)
    log.info("done: %d rows in %s", sum(counts.values()), args.out / "shards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
