"""QLoRA fine-tuning of Qwen2.5-Instruct as the RU-Guard classifier (Phase 4). Runs on a free Colab/Kaggle T4.

    python -m training.train_qlora --config training/configs/qwen2.5-0.5b.yaml --out /content/drive/MyDrive/ru-guard/runs
    python -m training.train_qlora --config training/configs/qwen2.5-0.5b.yaml --out /tmp/runs --dry-run   # local, CPU

The data is pre-tokenized here with the shared ChatML prompt (training/prompt.py). Labels are -100 on the prompt,
so the loss is on the assistant answer and its stop token only. Checkpoints go to <out>/<run_name>/checkpoints
every epoch, and a rerun of the same command resumes from the latest one.
"""

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import yaml
from pydantic import BaseModel

from training.jsonl import content_sha256, read_rows
from training.prompt import render_completion, render_prompt
from training.schemas import DataRow, Surface
from training.val_metrics import stratified_subset, val_metrics

REPO = Path(__file__).resolve().parents[1]


class LoraConfig(BaseModel):
    """LoRA adapter settings."""
    r: int
    alpha: int
    dropout: float
    target_modules: list[str]


class OptimConfig(BaseModel):
    """Trainer settings."""
    epochs: int
    learning_rate: float
    lr_scheduler: str
    warmup: float
    per_device_batch: int
    grad_accum: int
    weight_decay: float
    optim: str
    fp16: bool
    logging_steps: int
    seed: int


class DataConfig(BaseModel):
    """Which rows to train and validate on."""
    train_path: str
    val_path: str
    include_en: bool = True


class ValGenConfig(BaseModel):
    """Generation-based validation at the end of each epoch."""
    n: int
    batch_size: int
    max_new_tokens: int


class TrainConfig(BaseModel):
    """Settings from training/configs/qwen2.5-*.yaml."""
    run_name: str
    base_model: str
    max_seq_len: int
    load_in_4bit: bool
    lora: LoraConfig
    train: OptimConfig
    data: DataConfig
    val_gen: ValGenConfig


def apply_override(raw: dict, item: str) -> None:
    """Set one dotted key from KEY=VALUE (VALUE parsed as YAML), e.g. lora.r=8 or data.include_en=false."""
    key, sep, value = item.partition("=")
    if not sep:
        raise ValueError(f"override must be KEY=VALUE: {item!r}")
    node = raw
    *parents, leaf = key.split(".")
    for p in parents:
        if not isinstance(node.get(p), dict):
            raise KeyError(f"unknown config section {p!r} in {item!r}")
        node = node[p]
    if leaf not in node:
        raise KeyError(f"unknown config key {key!r}")
    node[leaf] = yaml.safe_load(value)


def load_config(path: Path, overrides: list[str]) -> TrainConfig:
    """Config file plus --set overrides."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    for item in overrides:
        apply_override(raw, item)
    return TrainConfig.model_validate(raw)


def load_split(path: Path, include_en: bool = True) -> list[DataRow]:
    """Rows of one split; fails on any invalid row."""
    rows, errors = read_rows(path)
    if errors:
        raise ValueError(f"{path}: {len(errors)} invalid rows, first: {errors[0]}")
    return [r for r in rows if include_en or r.surface != Surface.EN]


def encode_row(tokenizer, row: DataRow, max_len: int) -> dict | None:
    """input_ids, attention_mask, labels (-100 on the prompt); None if the row does not fit max_len."""
    prompt = tokenizer(render_prompt(row.text, str(row.source)), add_special_tokens=False)["input_ids"]
    answer = tokenizer(render_completion(row.target), add_special_tokens=False)["input_ids"]
    ids = prompt + answer
    if len(ids) > max_len:
        return None
    return {"input_ids": ids, "attention_mask": [1] * len(ids), "labels": [-100] * len(prompt) + answer}


def encode_split(tokenizer, rows: list[DataRow], max_len: int) -> tuple[list[dict], int]:
    """Encoded rows and the number dropped for length."""
    encoded = [encode_row(tokenizer, r, max_len) for r in rows]
    kept = [e for e in encoded if e is not None]
    return kept, len(encoded) - len(kept)


def latest_checkpoint(ckpt_dir: Path) -> Path | None:
    """Newest checkpoint-<step> folder, if any."""
    found = [p for p in ckpt_dir.glob("checkpoint-*") if p.is_dir() and p.name.split("-")[-1].isdigit()]
    return max(found, key=lambda p: int(p.name.split("-")[-1])) if found else None


def git_commit() -> str:
    """Current commit of the repo, or 'unknown'."""
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def package_versions() -> dict[str, str]:
    """Versions of the training stack that is importable here."""
    from importlib.metadata import PackageNotFoundError, version
    out = {"python": platform.python_version()}
    for name in ("torch", "transformers", "trl", "peft", "unsloth", "unsloth_zoo", "bitsandbytes", "datasets"):
        try:
            out[name] = version(name)
        except PackageNotFoundError:
            out[name] = "not installed"
    return out


def write_json(path: Path, data: dict) -> None:
    """Pretty JSON, UTF-8."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_csv(path: Path, row: dict) -> None:
    """Append one row; writes the header for a new file."""
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def generate_raw(model, tokenizer, prompts: list[str], batch_size: int, max_new_tokens: int) -> list[str]:
    """Greedy outputs for ChatML prompts (left padding), decoded without special tokens."""
    import torch
    side, tokenizer.padding_side = tokenizer.padding_side, "left"
    outs: list[str] = []
    try:
        for i in range(0, len(prompts), batch_size):
            batch = tokenizer(prompts[i:i + batch_size], return_tensors="pt", padding=True,
                              add_special_tokens=False).to(model.device)
            with torch.no_grad():
                gen = model.generate(**batch, max_new_tokens=max_new_tokens, do_sample=False,
                                     pad_token_id=tokenizer.pad_token_id)
            new = gen[:, batch["input_ids"].shape[1]:]
            outs.extend(tokenizer.batch_decode(new, skip_special_tokens=True))
    finally:
        tokenizer.padding_side = side
    return outs


def make_val_callback(tokenizer, rows: list[DataRow], cfg: ValGenConfig, log_path: Path):
    """TrainerCallback that runs generation on a fixed val subset at each epoch end and logs to CSV."""
    from transformers import TrainerCallback
    from unsloth import FastLanguageModel
    prompts = [render_prompt(r.text, str(r.source)) for r in rows]
    targets = [r.target for r in rows]

    class ValGenCallback(TrainerCallback):
        """Macro-F1, recall, FPR, invalid rate from real generations (not only loss)."""

        def on_epoch_end(self, args, state, control, model=None, **kwargs):
            FastLanguageModel.for_inference(model)
            raws = generate_raw(model, tokenizer, prompts, cfg.batch_size, cfg.max_new_tokens)
            FastLanguageModel.for_training(model)
            m = val_metrics(targets, raws)
            append_csv(log_path, {"epoch": round(state.epoch or 0, 2), "step": state.global_step, **m})
            print(f"val_gen epoch {state.epoch:.2f}: {json.dumps(m)}", flush=True)
            return control

    return ValGenCallback()


def make_csv_log_callback(log_path: Path):
    """TrainerCallback that writes every trainer log line (loss, lr, eval_loss) to a plain CSV."""
    from transformers import TrainerCallback

    class CsvLogCallback(TrainerCallback):
        """Plain CSV logs; no external trackers."""

        def on_log(self, args, state, control, logs=None, **kwargs):
            if logs:
                append_csv(log_path, {"step": state.global_step, "epoch": round(state.epoch or 0, 4),
                                      "loss": logs.get("loss", ""), "eval_loss": logs.get("eval_loss", ""),
                                      "learning_rate": logs.get("learning_rate", ""),
                                      "grad_norm": logs.get("grad_norm", "")})
            return control

    return CsvLogCallback()


def dry_run(cfg: TrainConfig, train_rows: list[DataRow], val_rows: list[DataRow]) -> int:
    """Tokenize everything and print stats and one example; no GPU, no model weights."""
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(cfg.base_model)
    train, dropped_t = encode_split(tok, train_rows, cfg.max_seq_len)
    val, dropped_v = encode_split(tok, val_rows, cfg.max_seq_len)
    lens = sorted(len(e["input_ids"]) for e in train)
    eff = cfg.train.per_device_batch * cfg.train.grad_accum
    steps = -(-len(train) // eff) * cfg.train.epochs
    ex = train[0]
    trained = tok.decode([t for t, lab in zip(ex["input_ids"], ex["labels"]) if lab != -100])
    print(json.dumps({"run_name": cfg.run_name, "train_rows": len(train), "train_dropped_long": dropped_t,
                      "val_rows": len(val), "val_dropped_long": dropped_v,
                      "tokens_p50": lens[len(lens) // 2], "tokens_max": lens[-1],
                      "effective_batch": eff, "optimizer_steps": steps, "trained_part_of_example": trained},
                     indent=2, ensure_ascii=False))
    return 0


def train(cfg: TrainConfig, train_rows: list[DataRow], val_rows: list[DataRow], run_dir: Path) -> int:
    """Full QLoRA run with Unsloth + TRL SFTTrainer (GPU)."""
    from unsloth import FastLanguageModel  # must be imported before transformers/trl
    from datasets import Dataset
    from transformers import DataCollatorForSeq2Seq
    from trl import SFTConfig, SFTTrainer
    import torch

    start = time.time()
    ckpt_dir = run_dir / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    model, tok = FastLanguageModel.from_pretrained(model_name=cfg.base_model, max_seq_length=cfg.max_seq_len,
                                                   dtype=None, load_in_4bit=cfg.load_in_4bit,
                                                   random_state=cfg.train.seed)
    model = FastLanguageModel.get_peft_model(model, r=cfg.lora.r, lora_alpha=cfg.lora.alpha,
                                             lora_dropout=cfg.lora.dropout, target_modules=cfg.lora.target_modules,
                                             bias="none", use_gradient_checkpointing="unsloth",
                                             random_state=cfg.train.seed)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    train_enc, dropped_t = encode_split(tok, train_rows, cfg.max_seq_len)
    val_enc, dropped_v = encode_split(tok, val_rows, cfg.max_seq_len)
    if dropped_t > 0.01 * len(train_rows):
        raise ValueError(f"{dropped_t} train rows exceed max_seq_len {cfg.max_seq_len} (more than 1%)")
    check = encode_row(tok, train_rows[0], 10**6)
    trained = tok.decode([t for t, lab in zip(check["input_ids"], check["labels"]) if lab != -100])
    if trained != render_completion(train_rows[0].target):
        raise RuntimeError(f"label mask is wrong: trained part is {trained!r}")

    manifest = {"run_name": cfg.run_name, "config": cfg.model_dump(), "git_commit": git_commit(),
                "data": {"train_sha256": content_sha256(REPO / cfg.data.train_path),
                         "val_sha256": content_sha256(REPO / cfg.data.val_path),
                         "train_rows": len(train_enc), "val_rows": len(val_enc),
                         "dropped_long": {"train": dropped_t, "val": dropped_v}},
                "versions": package_versions(),
                "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none",
                "command": " ".join(sys.argv)}
    write_json(run_dir / "run_manifest.json", manifest)

    args = SFTConfig(output_dir=str(ckpt_dir), num_train_epochs=cfg.train.epochs,
                     per_device_train_batch_size=cfg.train.per_device_batch,
                     per_device_eval_batch_size=cfg.train.per_device_batch,
                     gradient_accumulation_steps=cfg.train.grad_accum, learning_rate=cfg.train.learning_rate,
                     lr_scheduler_type=cfg.train.lr_scheduler, warmup_steps=cfg.train.warmup,
                     weight_decay=cfg.train.weight_decay, optim=cfg.train.optim, fp16=cfg.train.fp16, bf16=False,
                     logging_steps=cfg.train.logging_steps, eval_strategy="epoch", save_strategy="epoch",
                     save_total_limit=cfg.train.epochs, seed=cfg.train.seed, data_seed=cfg.train.seed,
                     max_length=cfg.max_seq_len, packing=False, report_to="none")
    val_subset = stratified_subset(val_rows, cfg.val_gen.n, cfg.train.seed)
    trainer = SFTTrainer(model=model, processing_class=tok, args=args,
                         train_dataset=Dataset.from_list(train_enc), eval_dataset=Dataset.from_list(val_enc),
                         data_collator=DataCollatorForSeq2Seq(tok, padding=True, label_pad_token_id=-100),
                         callbacks=[make_csv_log_callback(run_dir / "train_log.csv"),
                                    make_val_callback(tok, val_subset, cfg.val_gen, run_dir / "val_metrics.csv")])
    resume = latest_checkpoint(ckpt_dir)
    print(f"resume from: {resume}" if resume else "fresh run", flush=True)
    result = trainer.train(resume_from_checkpoint=str(resume) if resume else None)

    adapter_dir = run_dir / "adapter"
    model.save_pretrained(str(adapter_dir))
    tok.save_pretrained(str(adapter_dir))
    manifest.update({"train_runtime_seconds": round(time.time() - start, 1),
                     "train_loss": result.training_loss, "global_step": result.global_step,
                     "resumed_from": resume.name if resume else None,
                     "peak_gpu_memory_gb": round(torch.cuda.max_memory_reserved() / 1e9, 2)
                     if torch.cuda.is_available() else None})
    write_json(run_dir / "run_manifest.json", manifest)
    print(f"adapter saved to {adapter_dir}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path(os.environ.get("RUGUARD_RUNS", "runs")),
                    help="runs root (Drive on Colab); the run goes to <out>/<run_name>")
    ap.add_argument("--set", dest="overrides", action="append", default=[], metavar="KEY=VALUE",
                    help="override a config value, e.g. --set lora.r=8 --set run_name=ru-guard-0.5b-r8")
    ap.add_argument("--dry-run", action="store_true", help="tokenize and print stats only (CPU)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config, args.overrides)
    train_rows = load_split(REPO / cfg.data.train_path, cfg.data.include_en)
    val_rows = load_split(REPO / cfg.data.val_path)
    if args.dry_run:
        return dry_run(cfg, train_rows, val_rows)
    return train(cfg, train_rows, val_rows, args.out / cfg.run_name)


if __name__ == "__main__":
    raise SystemExit(main())
