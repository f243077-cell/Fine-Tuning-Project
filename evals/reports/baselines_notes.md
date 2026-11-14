## Findings

1. **No baseline is usable as a guard.** Every baseline misses badly on recall, on FPR, or on both. The only run with FPR under 3% is `rules` (FPR 0.020), and it catches 28% of attacks (recall 0.280).
2. **Qwen zero-shot cannot follow the output format.** 40% of its outputs are invalid. The most common are `INJECTION|<attack_type>` (60, the placeholder copied from the prompt), `INJECTION|<tool_abuse>` (47), and a bare `INJECTION` (10). It never emits a valid `INJECTION|<type>` label. All of its recall (0.453) and all 52 of its false flags come from fail-closed scoring of invalid output (D43). Scored fail-open, the same predictions give recall 0.000 and FPR 0.000.
3. **Qwen few-shot learns the format but over-flags.** Invalid output falls to 1% and recall is 0.927 [0.88, 0.96]. FPR is 0.647 [0.58, 0.72]. 83 of its 97 false flags say `tool_abuse`. On `retrieved_chunk` and `tool_output` SAFE rows it flags 87% and 90%, so it treats almost any passage or tool output as an attack. Its attack-type macro-F1 is 0.266.
4. **Llama Guard 3 1B is the most balanced model baseline, but it does a different job.** It targets content-safety categories (S1 to S13), not injection. It still catches exfiltration (0.733) and tool abuse (0.667), which read as harmful requests. It misses override (0.167) and prompt leak (0.233). FPR is 0.127. It gives no attack type.
5. **Roman Urdu is harder for the rules and zero-shot.** Rules recall drops from 0.340 on `en` to 0.160 on `ru_pure`, and Qwen zero-shot drops from 0.580 to 0.320. Few-shot and Llama Guard show no clear surface gap (the CIs overlap).
6. **Hard negatives:** rules FPR rises from 0.000 on plain SAFE rows to 0.036 on hard negatives, and zero-shot from 0.197 to 0.464. Few-shot flags plain SAFE more than hard negatives (0.758 vs 0.560), which fits blanket over-flagging rather than keyword matching.

## Against the PRD section 13 targets

The targets are for the fine-tuned model, so baselines do not need to meet them. These numbers set the bar.

| Target | Best baseline value | Note |
|---|---|---|
| Recall on `ru_mix` + `ru_pure` >= 0.90 at FPR <= 3% | rules: recall 0.250 at FPR 0.010 (the only run under 3% FPR) | Few-shot reaches 0.940 recall, but at 0.620 FPR. |
| Beat the best baseline on recall at matched FPR | rules: recall 0.280 at FPR 0.020 | The baselines give a label, not a score, so no threshold sweep is possible. "Matched FPR" means the fine-tuned model's FPR must be no higher than the baseline it is compared with. |
| Recall drop `en` to `ru_pure` <= 10 points | Few-shot: +6 points (0.900 to 0.960). Llama Guard: -8 points | |
| Invalid-output rate <= 1% | Few-shot 0.010; zero-shot 0.400 | Fine-tuning must keep the format. |

The `ru_mix` + `ru_pure` recall and FPR above, and the fail-open numbers in finding 2, are point estimates. They are computed from the same `predictions.jsonl` files and have no CI.

**Proposal (not applied; needs owner approval):** keep all targets. One caveat: the test set has 150 SAFE rows, so FPR <= 3% allows at most 4 false flags. Even when the point estimate meets 3%, the upper end of its 95% CI will be about 6%. I propose judging the FPR target on the point estimate and reporting the CI next to it. The text of PRD section 13 is unchanged.

## Caveats

- Llama Guard is scored as a binary flag (`unsafe` = INJECTION). Its attack-type macro-F1 of 0.000 is a scoring artifact, not a measurement.
- Few-shot uses 8 seed examples (5 attacks, 3 SAFE), all in `ru_mix`, and no test rows. Its bias toward `tool_abuse` may come from the shot order. This was not tuned, by design: the test set must not be used for prompt tuning.
- Latency is CPU-only on the owner's laptop through Ollama 0.32.15. p50 is about 3.4 to 4.2 s per text. The 10 s first call is model load.
- The few-shot run first stopped at row 198 because the Ollama server shut down (`httpx.ConnectError`). It was re-run from the start on 2026-11-14, and the numbers above come from that complete run.
- Guardrails AI and NeMo Guardrails (stretch) were not run.
