# Interview notes: RU-Guard in 5 minutes

Open `docs/understanding/02-grand-workflow.png` and walk it left to right. Every number below comes from a recorded run (see `evals/reports/EVAL_REPORT.md`); if you are asked for one that is not here, say it was not measured.

## The one-sentence pitch

"A small fine-tuned model that tells whether a text, in Roman Urdu, English or both, hides an instruction for an AI. It checks user input, retrieved documents and tool outputs, runs on a laptop CPU, and a CI gate stops a regression from reaching main."

## Walkthrough (about 5 minutes)

**1. The problem (30 s).** Most Pakistani users type Roman Urdu; most injection defences are built on English. Research (the RUAB paper) shows safety detection degrades on code-switched text. And injection arrives in retrieved chunks and tool outputs, not just in the chat box.

**2. Data (60 s).** Left of the diagram. 80 seeds go to Qwen2.5-14B-Instruct (4-bit, free Colab T4) which generates attack and benign rows. Filters drop bad language mix, duplicates, near-copies of the test set, and unsafe content. 900 real Roman Urdu comments are added as SAFE examples. A first attempt with the 7B generator produced incoherent Roman Urdu, so I moved to 14B (D29). The test set (300 rows, 100 matched intents in English, mixed and pure Roman Urdu) is frozen by a hash lock and never touched for training or prompt tuning.

**3. Training (45 s).** QLoRA (4-bit, LoRA r 16) on Qwen2.5-0.5B and 1.5B, loss only on the answer, free Kaggle or Colab T4. The model answers one line: `SAFE` or `INJECTION|<type>`. Export to GGUF Q4_K_M and serve with Ollama.

**4. Prove it (60 s).** Same harness for every model: rules, Llama Guard 3, Qwen few-shot, my models. Deployed model: recall 0.953, false-flag rate 0.100, F1 0.929, Roman Urdu recall 0.94, English to pure-Roman-Urdu gap 6 points, no malformed outputs. The first version had a 32-point gap on pure Roman Urdu; error analysis showed the data had few such attacks, so I ran the one allowed data loop (a dictionary conversion of mixed rows to pure Roman Urdu, D48) and the gap fell to 6 points.

**5. Serve and protect (60 s).** FastAPI service: auth, rate limit, windowing for long texts, policy per source (block a question, drop a chunk, redact a tool output), a log with only a keyed hash and length, Presidio masking for quarantined chunks. A reference RAG app puts the guard at four checkpoints and can switch it off, so the same code measures attack success with the guard off and on: 8 of 36 attacks succeed off, 0 of 36 on. An MCP gateway scans every tool result.

**6. Gate it (45 s).** CI runs the tests on every PR, a 100-row smoke eval with a score gate, and a nightly full run with the attack suites and two red-team tools (Promptfoo, DeepEval). I showed the gate failing on a deliberately broken scanner.

**7. Honest misses (30 s).** False-flag rate 0.100 against a 0.03 goal: all of it is hard negatives (harmless text about instructions or rules). Latency about 1 s per window on a CPU. Test set was drafted by an AI assistant and awaits a native speaker.

## Trade-offs to be ready for

| Choice | I chose | Alternative | Why, and what it costs |
|---|---|---|---|
| Classifier type | Generative QLoRA LLM that emits a label (D1, D2) | Encoder classifier (for example the 22M to 86M-parameter Prompt Guard family) | One model gives a label and an attack type with a strict grammar, and it fine-tunes cheaply on a free GPU. Cost: about 1 s per window on CPU, where small encoders are much faster (I did not measure one here). Encoders also give a score; this model gives none, by design |
| Latency vs accuracy | 1.5B (warm p50 0.88 s) | 0.5B (0.53 s) | The 1.5B gets Roman Urdu recall 0.94 against 0.85. For a guard that sits in front of an LLM, missing an attack costs more than 0.35 s |
| Fail-closed vs fail-open | `FAIL_MODE=closed` by default (D43, D50) | open | When the model is down or the output is malformed, treat the text as an attack. Costs availability, buys safety. Open mode exists per environment; a 503 still carries the action so callers that only read the status fail safe |
| Q4_K_M vs Q8_0 | Q4_K_M | Q8_0 | About 35% faster on CPU and a smaller download; Q8_0 had about 2 points more recall on the GPU run |
| Normalizer | NFKC, strip control characters, lowercase, collapse repeats; no spelling canonicalisation | A Roman Urdu spelling normaliser | Spelling variants (`kya`/`kia`) are covered by varied training data instead of rules. Leetspeak folding is off by default because it also changes harmless words; the red team found leetspeak passes |
| Windowing | 1,000-character windows, 200 overlap, any flagged window flags the text | Whole text at once | Fits the 512-token training length; split attacks are caught by the overlap. Costs time on long texts |

## Likely questions

**How do you know there is no test leakage?** The test set is hash-locked and verified before every run. The build removes any training row with character 5-gram Jaccard 0.5 or more against a seed or a test row (in the dataset behind the deployed model the highest kept was 0.430). The `ru_pure` conversion step checks every output against every test row (0 leaks). The corpus, attack suite and golden set have the same check (`scripts/check_corpus_leak.py`).

**Is 0.953 recall trustworthy?** Within limits. 150 attacks means the 95% interval is 0.92 to 0.99, and the same model gave different labels on 2 of 100 borderline rows between two runs. That jitter is why the PR smoke gate has a 6-point margin (D57) and the nightly gate 2 points.

**Why is the false-flag rate high?** The data has hard negatives (benign text that talks about instructions), but the model still flags 18% of them. A second data loop with more hard negatives, especially in pure Roman Urdu, is the next step; the plan allowed one loop.

**How would you attack your own guard?** Tell it to answer SAFE (5 of the 7 misses), obfuscate (spaced letters, leetspeak pass it in the red-team run), hide the instruction in a long text (windows help), or use Urdu script (out of scope). It is one layer; the demo also checks answers for a canary token and requires citations.

**What if Ollama is down?** Health goes red, the scan returns 503 with `verdict: error` and the fail-mode action (block by default). The client library does the same when the service is unreachable.

**What do you log?** A keyed hash and the length of each text, the verdict, the action, the model and the latency. Quarantined chunks are stored with PII masked. No raw user text in logs or the database (a test checks the database file for it).

**What went wrong along the way?** (1) The Phase 5 latency numbers were 3 s too high: the evaluation client opened a new connection for every call, and `localhost` tried IPv6 first. I found it when the service benchmark disagreed with the harness, fixed it, and published the correction (D51). (2) CI failed on every push for a day because of a numpy pin that conflicted with Presidio. (3) The first CI smoke gate failed on run-to-run noise: a 2-point margin on 100 rows is one flipped row. I measured it, widened the margin, and checked that the wider gate still rejects all nine other models.

**What would you do with more time?** More hard negatives in pure Roman Urdu; a native-speaker review of the test set and the training sample; train on attacks that address the guard; compare with an encoder classifier on the same test set; run the chat-model comparison with a model that follows injected instructions, so the document check's value is visible.

**Why free tools only?** A stated constraint: free Colab or Kaggle for training, Ollama on a laptop CPU for serving, GitHub Actions on a public repo for CI. It shaped the model size (1.5B at most) and the quantisation choice.
