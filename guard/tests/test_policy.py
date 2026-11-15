"""Policy table tests (Architecture.md section 8)."""

import pytest

from guard.policy import decide
from guard.schemas import Action, AttackType, ScannerError, ScanResult, Source, Verdict

INJ = ScanResult(verdict=Verdict.INJECTION, attack_type=AttackType.OVERRIDE)
ERR = ScanResult(verdict=Verdict.ERROR, scanner_error=ScannerError.TIMEOUT)
SAFE = ScanResult(verdict=Verdict.SAFE)


@pytest.mark.parametrize("source,action", [(Source.USER_INPUT, Action.BLOCK),
                                           (Source.RETRIEVED_CHUNK, Action.DROP_CHUNK),
                                           (Source.TOOL_OUTPUT, Action.REDACT_TOOL_OUTPUT)])
def test_injection_action_per_source(source: Source, action: Action) -> None:
    """Injection maps to the per-source action; fail-closed errors map the same way."""
    assert decide(INJ, source) == action
    assert decide(ERR, source, fail_mode="closed") == action


@pytest.mark.parametrize("source", list(Source))
def test_safe_and_fail_open(source: Source) -> None:
    """Safe is allowed; errors are allowed with FAIL_MODE=open; injection still acts with open."""
    assert decide(SAFE, source) == Action.ALLOW
    assert decide(ERR, source, fail_mode="open") == Action.ALLOW
    assert decide(INJ, source, fail_mode="open") != Action.ALLOW


@pytest.mark.parametrize("source", list(Source))
def test_log_only_never_blocks(source: Source) -> None:
    """MODE=log_only turns every block into log_only."""
    assert decide(INJ, source, mode="log_only") == Action.LOG_ONLY
    assert decide(ERR, source, mode="log_only") == Action.LOG_ONLY
    assert decide(SAFE, source, mode="log_only") == Action.ALLOW
