"""Integration tests: guard-api, client SDK, MCP gateway and demo-rag working together against the live stack.

Run: start the stack (docs/TESTING.md), then `pytest -q tests/integration`. Skipped when guard-api is not running.
"""
import asyncio
import json
import uuid

import httpx
import pytest

from client.ruguard_client import AsyncGuardClient, GuardClient
from client.ruguard_client.client import GuardAuthError
from tests.live import (CHUNK_INJ, DEMO_URL, EN_INJ, EN_SAFE, FILLER, GUARD_URL, MIX_INJ, MIX_SAFE, RU_INJ, RU_SAFE,
                        TOOL_INJ, api_key, require)

pytestmark = pytest.mark.integration
require(GUARD_URL, "guard-api")
KEY = api_key()


@pytest.fixture(scope="module")
def http():
    """Raw HTTP client with the API key."""
    with httpx.Client(base_url=GUARD_URL, headers={"X-API-Key": KEY}, timeout=120.0) as c:
        yield c


@pytest.fixture(scope="module")
def guard():
    """SDK client against the live service."""
    with GuardClient(GUARD_URL, KEY) as g:
        yield g


def scan(http, text, source="user_input", **extra):
    """POST /v1/scan and return (status, body)."""
    r = http.post("/v1/scan", json={"text": text, "source": source, **extra})
    return r.status_code, r.json()


# --- guard-api contract -------------------------------------------------------------------------------------------

def test_health_ok_and_names_deployed_model():
    body = httpx.get(f"{GUARD_URL}/health", timeout=10).json()
    assert body["status"] == "ok" and body["model"] == "ru-guard-1.5b-v2"


def test_scan_without_key_is_401():
    r = httpx.post(f"{GUARD_URL}/v1/scan", json={"text": EN_SAFE, "source": "user_input"}, timeout=10)
    assert r.status_code == 401


def test_scan_with_wrong_key_is_401():
    r = httpx.post(f"{GUARD_URL}/v1/scan", json={"text": EN_SAFE, "source": "user_input"},
                   headers={"X-API-Key": "wrong-key"}, timeout=10)
    assert r.status_code == 401


@pytest.mark.parametrize("body", [{"text": "", "source": "user_input"}, {"text": "hi", "source": "email"},
                                  {"text": "hi"}, {"source": "user_input"}])
def test_bad_bodies_are_422(http, body):
    assert http.post("/v1/scan", json=body).status_code == 422


def test_text_over_max_chars_is_413(http):
    assert http.post("/v1/scan", json={"text": "a" * 12001, "source": "user_input"}).status_code == 413


def test_batch_over_32_items_is_413(http):
    items = [{"id": str(i), "text": EN_SAFE, "source": "user_input"} for i in range(33)]
    assert http.post("/v1/scan/batch", json={"items": items}).status_code == 413


def test_request_id_is_echoed(http):
    rid = uuid.uuid4().hex
    assert scan(http, EN_SAFE, request_id=rid)[1]["request_id"] == rid


def test_request_id_is_generated_when_missing(http):
    rid = scan(http, EN_SAFE)[1]["request_id"]
    assert len(rid) == 32 and int(rid, 16) >= 0


def test_response_has_contract_fields_and_no_text(http):
    status, body = scan(http, EN_SAFE)
    assert status == 200
    assert set(body) >= {"request_id", "verdict", "attack_type", "action", "model", "latency_ms", "windows"}
    assert EN_SAFE not in json.dumps(body)


# --- verdicts on the real model -----------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [EN_INJ, RU_INJ, MIX_INJ], ids=["en", "ru_pure", "ru_mix"])
def test_injection_in_user_input_is_blocked(http, text):
    body = scan(http, text)[1]
    assert body["verdict"] == "injection" and body["action"] == "block" and body["attack_type"]


@pytest.mark.parametrize("text", [EN_SAFE, RU_SAFE, MIX_SAFE], ids=["en", "ru_pure", "ru_mix"])
def test_safe_user_input_is_allowed(http, text):
    body = scan(http, text)[1]
    assert body["verdict"] == "safe" and body["action"] == "allow" and body["attack_type"] is None


def test_poisoned_retrieved_chunk_is_dropped(http):
    assert scan(http, CHUNK_INJ, "retrieved_chunk")[1]["action"] == "drop_chunk"


def test_poisoned_tool_output_is_redacted(http):
    assert scan(http, TOOL_INJ, "tool_output")[1]["action"] == "redact_tool_output"


def test_long_text_is_split_into_windows(http):
    body = scan(http, FILLER * 20)[1]  # about 3,500 characters
    assert body["windows"] >= 3 and body["verdict"] == "safe"


def test_injection_hidden_after_long_safe_text_is_found(http):
    body = scan(http, FILLER * 15 + " " + EN_INJ)[1]
    assert body["windows"] >= 3 and body["verdict"] == "injection"


def test_batch_keeps_order_ids_and_per_source_actions(http):
    items = [{"id": "a", "text": EN_SAFE, "source": "user_input"},
             {"id": "b", "text": CHUNK_INJ, "source": "retrieved_chunk"},
             {"id": "c", "text": TOOL_INJ, "source": "tool_output"}]
    res = http.post("/v1/scan/batch", json={"items": items, "request_id": "batch1"}).json()["results"]
    assert [r["id"] for r in res] == ["a", "b", "c"]
    assert [r["action"] for r in res] == ["allow", "drop_chunk", "redact_tool_output"]
    assert res[0]["request_id"] == "batch1:a"


# --- audit log through /v1/stats ----------------------------------------------------------------------------------

def test_stats_needs_key():
    assert httpx.get(f"{GUARD_URL}/v1/stats", timeout=10).status_code == 401


def test_stats_total_grows_after_a_scan(http):
    before = http.get("/v1/stats").json()["total"]
    scan(http, EN_SAFE)
    assert http.get("/v1/stats").json()["total"] == before + 1


def test_stats_counts_tool_output_source(http):
    before = http.get("/v1/stats").json()["by_source"].get("tool_output", 0)
    scan(http, EN_SAFE, "tool_output")
    assert http.get("/v1/stats").json()["by_source"]["tool_output"] == before + 1


def test_flagged_chunk_goes_to_quarantine(http):
    before = http.get("/v1/stats").json()["quarantined"]
    scan(http, CHUNK_INJ + " Contact: 0300-1234567.", "retrieved_chunk")
    assert http.get("/v1/stats").json()["quarantined"] == before + 1


# --- client SDK ---------------------------------------------------------------------------------------------------

def test_sdk_scan_flags_injection(guard):
    assert guard.scan(RU_INJ, "user_input").flagged


def test_sdk_scan_allows_safe_text(guard):
    assert not guard.scan(RU_SAFE, "user_input").flagged


def test_sdk_health_and_stats(guard):
    assert guard.health().status == "ok" and guard.stats().total > 0


def test_sdk_wrong_key_raises_auth_error():
    with GuardClient(GUARD_URL, "wrong-key") as g, pytest.raises(GuardAuthError):
        g.scan(EN_SAFE, "user_input")


def test_sdk_unreachable_service_fails_closed():
    with GuardClient("http://127.0.0.1:9", KEY, timeout=2.0, retries=0) as g:
        r = g.scan(EN_SAFE, "user_input")
    assert r.scanner_error == "unavailable" and r.action == "block"


def test_async_sdk_scans_concurrently():
    async def run():
        async with AsyncGuardClient(GUARD_URL, KEY) as g:
            return await asyncio.gather(g.scan(EN_INJ, "user_input"), g.scan(EN_SAFE, "user_input"))
    bad, good = asyncio.run(run())
    assert bad.flagged and not good.flagged


# --- MCP gateway with the live guard ------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gateway(guard):
    """Gateway core with the real guard behind it."""
    from gateway.tools import default_gateway
    return default_gateway(guard)


def test_gateway_passes_clean_note(gateway):
    out = gateway.call("get_note", {"id": "note-1"})
    assert not out["redacted"] and out["verdict"] == "safe"


def test_gateway_redacts_poisoned_note(gateway):
    out = gateway.call("get_note", {"id": "note-2"})
    assert out["redacted"] and "PINEAPPLE" not in out["result"]


def test_gateway_refuses_unknown_tool(gateway):
    from gateway.tools import ToolRefused
    with pytest.raises(ToolRefused):
        gateway.call("delete_all_files", {})


def test_gateway_scan_text_tool_returns_verdict(gateway):
    out = gateway.call("scan_text", {"text": EN_INJ, "source": "user_input"})
    assert json.loads(out["result"])["verdict"] == "injection"


# --- demo-rag (reference RAG app) ---------------------------------------------------------------------------------

def _demo_up() -> bool:
    try:
        return httpx.get(f"{DEMO_URL}/health", timeout=5).status_code == 200
    except httpx.HTTPError:
        return False


demo = pytest.mark.skipif(not _demo_up(), reason="demo-rag not running (docker compose --profile demo)")


@demo
def test_demo_health_reports_guard_ok():
    body = httpx.get(f"{DEMO_URL}/health", timeout=30).json()
    assert body["guard_ok"] and body["chat_model_ok"]


@demo
def test_demo_blocks_injected_question_with_guard_on():
    r = httpx.post(f"{DEMO_URL}/chat", json={"question": RU_INJ, "guard": "on"}, timeout=600).json()
    assert r["blocked"] and r["guard"]


@demo
def test_demo_answers_clean_question_with_guard_on():
    r = httpx.post(f"{DEMO_URL}/chat", json={"question": "Lahore mein delivery kitne din mein hoti hai?",
                                             "guard": "on"}, timeout=600).json()
    assert not r["blocked"] and r["answer"]
