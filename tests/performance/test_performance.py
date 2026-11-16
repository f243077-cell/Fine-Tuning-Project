"""Performance tests against the live stack: latency, window scaling, batches, concurrency, stability.

Budgets are regression budgets, not the PRD targets: about 1.8x the measured service baseline (warm p50 0.91 s,
p95 1.36 s per window on the owner's 4-thread CPU, evals/reports/EVAL_REPORT.md section 5). The PRD NFR-3 target
(1.5B: p95 per window at most 1.0 s) is reported in docs/TESTING.md, not asserted, because it is already known missed.
Start guard-api with RATE_LIMIT=1000/minute so the bursts here are not cut by the rate limiter.
Set PERF_OUT=<file.json> to save every measurement.
"""
import asyncio
import json
import os
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from client.ruguard_client import AsyncGuardClient, GuardClient
from tests.live import (CHUNK_INJ, DEMO_URL, EN_INJ, EN_SAFE, FILLER, GUARD_URL, MIX_INJ, MIX_SAFE, RU_INJ, RU_SAFE,
                        TOOL_INJ, api_key, require)

pytestmark = pytest.mark.performance
require(GUARD_URL, "guard-api")
KEY = api_key()
WINDOW_P50, WINDOW_P95 = 1.7, 2.5  # seconds per warm window (regression budgets)
RESULTS: dict[str, object] = {}


def record(name: str, value: object) -> None:
    """Keep one measurement (written to PERF_OUT at the end)."""
    RESULTS[name] = value


@pytest.fixture(scope="session", autouse=True)
def _dump():
    """Write all measurements when the session ends."""
    yield
    if os.environ.get("PERF_OUT"):
        with open(os.environ["PERF_OUT"], "w", encoding="utf-8") as f:
            json.dump(RESULTS, f, indent=2)


@pytest.fixture(scope="module")
def http():
    """Pooled HTTP client with the key; warms the model once."""
    with httpx.Client(base_url=GUARD_URL, headers={"X-API-Key": KEY}, timeout=120.0) as c:
        c.post("/v1/scan", json={"text": EN_SAFE, "source": "user_input"})
        yield c


def timed(http, text, source="user_input", path="/v1/scan", body=None):
    """Wall time in seconds and the response."""
    t = time.perf_counter()
    r = http.post(path, json=body or {"text": text, "source": source})
    return time.perf_counter() - t, r


def pct(xs, q):
    """Percentile by nearest rank."""
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, round(q / 100 * len(xs)) - 1))]


# --- cheap paths (no model call) ----------------------------------------------------------------------------------

def test_health_p95_under_300ms():
    ts = []
    with httpx.Client(timeout=10) as c:  # one client: httpx.get builds a new SSL context per call (~0.5 s here)
        for _ in range(20):
            t = time.perf_counter(); c.get(f"{GUARD_URL}/health"); ts.append(time.perf_counter() - t)
    record("health_p95_s", pct(ts, 95))
    assert pct(ts, 95) < 0.3


def test_auth_rejection_p95_under_100ms():
    ts = []
    with httpx.Client(timeout=10) as c:
        for _ in range(20):
            t = time.perf_counter(); c.post(f"{GUARD_URL}/v1/scan", json={"text": "x", "source": "user_input"})
            ts.append(time.perf_counter() - t)
    record("auth_401_p95_s", pct(ts, 95))
    assert pct(ts, 95) < 0.1


def test_validation_rejection_p95_under_100ms(http):
    ts = [timed(http, "", "user_input")[0] for _ in range(20)]
    record("validation_422_p95_s", pct(ts, 95))
    assert pct(ts, 95) < 0.1


def test_oversize_text_rejected_under_200ms(http):
    s, r = timed(http, "a" * 12001)
    record("oversize_413_s", s)
    assert r.status_code == 413 and s < 0.2


def test_oversize_body_rejected_under_1s(http):
    s, r = timed(http, "a" * 2_100_000)
    record("body_limit_s", s)
    assert r.status_code == 413 and s < 1.0


def test_stats_under_500ms(http):
    s = time.perf_counter(); r = http.get("/v1/stats"); s = time.perf_counter() - s
    record("stats_s", s)
    assert r.status_code == 200 and s < 0.5


# --- single-window latency per surface and source ------------------------------------------------------------------

CASES = {"en_safe": EN_SAFE, "en_inj": EN_INJ, "ru_pure_safe": RU_SAFE, "ru_pure_inj": RU_INJ,
         "ru_mix_safe": MIX_SAFE, "ru_mix_inj": MIX_INJ}


@pytest.mark.parametrize("name", list(CASES))
def test_warm_single_window_p50(http, name):
    ts = [timed(http, CASES[name])[0] for _ in range(5)]
    record(f"warm_p50_{name}_s", statistics.median(ts))
    assert statistics.median(ts) < WINDOW_P50


@pytest.mark.parametrize("source,text", [("retrieved_chunk", CHUNK_INJ), ("tool_output", TOOL_INJ),
                                         ("retrieved_chunk", EN_SAFE), ("tool_output", RU_SAFE)])
def test_warm_latency_by_source(http, source, text):
    ts = [timed(http, text, source)[0] for _ in range(3)]
    record(f"warm_p50_{source}_{len(text)}_s", statistics.median(ts))
    assert statistics.median(ts) < WINDOW_P50


def test_warm_p95_over_20_calls(http):
    texts = list(CASES.values())
    ts = [timed(http, texts[i % len(texts)])[0] for i in range(20)]
    record("warm_20_p50_s", statistics.median(ts)); record("warm_20_p95_s", pct(ts, 95))
    assert pct(ts, 95) < WINDOW_P95


def test_server_latency_ms_matches_client_time(http):
    s, r = timed(http, RU_SAFE)
    record("server_latency_ms", r.json()["latency_ms"]); record("client_wall_s", s)
    assert r.json()["latency_ms"] <= s * 1000 + 5


def test_server_side_p95_latency(http):
    ms = [http.post("/v1/scan", json={"text": t, "source": "user_input"}).json()["latency_ms"]
          for t in list(CASES.values()) * 2]
    record("server_p95_ms", pct(ms, 95))
    assert pct(ms, 95) < WINDOW_P95 * 1000


# --- multi-window texts -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("repeat", [5, 10, 20, 40])
def test_latency_per_window_stays_within_budget(http, repeat):
    runs = [timed(http, FILLER * repeat) for _ in range(3)]  # median of 3: one CPU run is too noisy
    s, w = statistics.median(t for t, _ in runs), runs[0][1].json()["windows"]
    record(f"multi_{w}win_median_s", s); record(f"multi_{w}win_per_window_s", s / w)
    assert s / w < WINDOW_P95


def test_max_size_text_under_30s(http):
    text = (FILLER * 60)[:12000]
    s, r = timed(http, text)
    record("max_12000_chars_s", s); record("max_12000_chars_windows", r.json()["windows"])
    assert r.status_code == 200 and s < 30


# --- batches ------------------------------------------------------------------------------------------------------

def _batch(n):
    texts = list(CASES.values())
    return {"items": [{"id": str(i), "text": texts[i % len(texts)], "source": "retrieved_chunk"} for i in range(n)]}


@pytest.mark.parametrize("n", [4, 8, 16, 32])
def test_batch_per_item_cost(http, n):
    s, r = timed(http, None, path="/v1/scan/batch", body=_batch(n))
    record(f"batch_{n}_s", s); record(f"batch_{n}_per_item_s", s / n)
    assert r.status_code == 200 and len(r.json()["results"]) == n and s / n < WINDOW_P95


# --- concurrency and stability ------------------------------------------------------------------------------------

@pytest.mark.parametrize("workers", [2, 4, 8])
def test_parallel_clients_no_errors(workers):
    texts = list(CASES.values())

    def one(i):
        with httpx.Client(timeout=120) as c:
            t = time.perf_counter()
            r = c.post(f"{GUARD_URL}/v1/scan", json={"text": texts[i % len(texts)], "source": "user_input"},
                       headers={"X-API-Key": KEY})
            return r.status_code, time.perf_counter() - t

    t0 = time.perf_counter()
    with ThreadPoolExecutor(workers) as ex:
        out = list(ex.map(one, range(workers * 2)))
    wall = time.perf_counter() - t0
    record(f"parallel_{workers}_throughput_per_s", workers * 2 / wall)
    record(f"parallel_{workers}_max_s", max(s for _, s in out))
    assert all(code == 200 for code, _ in out) and max(s for _, s in out) < 30  # under OLLAMA_TIMEOUT


def test_throughput_at_least_half_a_scan_per_second():
    async def run():
        async with AsyncGuardClient(GUARD_URL, KEY) as g:
            t = time.perf_counter()
            await asyncio.gather(*(g.scan(EN_SAFE, "user_input") for _ in range(8)))
            return 8 / (time.perf_counter() - t)
    rate = asyncio.run(run())
    record("async_8_throughput_per_s", rate)
    assert rate > 0.5


def test_no_latency_drift_over_30_sequential_scans(http):
    ts = [timed(http, RU_SAFE)[0] for _ in range(30)]
    first, last = pct(ts[:10], 95), pct(ts[-10:], 95)
    record("drift_first10_p95_s", first); record("drift_last10_p95_s", last)
    assert last <= first * 1.5 + 0.5


def test_sdk_overhead_under_100ms(http):
    raw, sdk = [], []
    with GuardClient(GUARD_URL, KEY) as g:
        for _ in range(8):  # interleaved, so model-time noise hits both sides alike
            raw.append(timed(http, EN_SAFE)[0])
            t = time.perf_counter(); g.scan(EN_SAFE, "user_input"); sdk.append(time.perf_counter() - t)
    record("sdk_minus_raw_median_s", statistics.median(sdk) - statistics.median(raw))
    assert statistics.median(sdk) - statistics.median(raw) < 0.1


def test_fail_closed_fallback_is_fast():
    with GuardClient("http://127.0.0.1:9", KEY, timeout=2.0, retries=1) as g:
        t = time.perf_counter(); r = g.scan(EN_SAFE, "user_input"); s = time.perf_counter() - t
    record("fail_closed_s", s)
    assert r.action == "block" and s < 6


def test_guard_api_memory_under_1500mb():
    try:
        out = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.Name}} {{.MemUsage}}"],
                             capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        pytest.skip("docker not available")
    line = next((x for x in out.splitlines() if "guard-api" in x), None)
    if line is None:
        pytest.skip("guard-api is not running in Docker")
    used = line.split()[1]
    mib = float(used[:-3]) * (1024 if used.endswith("GiB") else 1) if used[-3:] in ("MiB", "GiB") else 0.0
    record("guard_api_mem_mib", mib)
    assert 0 < mib < 1500


def test_demo_health_under_2s():
    try:
        t = time.perf_counter(); r = httpx.get(f"{DEMO_URL}/health", timeout=10); s = time.perf_counter() - t
    except httpx.HTTPError:
        pytest.skip("demo-rag not running")
    record("demo_health_s", s)
    assert r.status_code == 200 and s < 2
