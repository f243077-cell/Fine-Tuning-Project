"""Policy: map a scan result to an action (Architecture.md section 8)."""

from guard.schemas import Action, ScanResult, Source, Verdict

INJECTION_ACTION = {
    Source.USER_INPUT: Action.BLOCK,
    Source.RETRIEVED_CHUNK: Action.DROP_CHUNK,
    Source.TOOL_OUTPUT: Action.REDACT_TOOL_OUTPUT,
}


def decide(result: ScanResult, source: Source, mode: str = "enforce", fail_mode: str = "closed") -> Action:
    """Action for a scan result.

    injection -> the per-source action; error -> the per-source action when FAIL_MODE=closed, allow when open;
    safe -> allow. MODE=log_only turns every would-be block into log_only.
    """
    if result.verdict == Verdict.SAFE:
        return Action.ALLOW
    if result.verdict == Verdict.ERROR and fail_mode == "open":
        return Action.ALLOW
    if mode == "log_only":
        return Action.LOG_ONLY
    return INJECTION_ACTION[source]
