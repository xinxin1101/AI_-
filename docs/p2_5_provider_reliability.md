# P2.5 Live Provider & Agent Reliability

P2.5 closes the reliability gap between a deterministic Agent demo and a provider-backed service.

## Scope

- Open-Meteo live weather adapter
- AMap POI 2.0 scenic adapter
- AMap Route Planning 2.0 adapter
- shared timeout / bounded exponential retry / circuit breaker
- provider response contract validation
- deterministic provider contract tests
- intent routing evaluation
- tool-selection accuracy evaluation
- opt-in live provider smoke checks

## Reliability policy

Retries are deliberately narrow:

- retry: transport failures, HTTP 408, 425, 429, and 5xx
- do not blindly retry: ordinary 4xx and AMap business/auth errors (`status=0`)

The circuit breaker is per provider instance. After consecutive final failures it opens and fails fast. After the configured recovery window the next call is allowed as a half-open probe; success closes the circuit, failure re-opens it.

Environment controls:

```env
TOOL_TIMEOUT_SECONDS=15
TOOL_RETRY_ATTEMPTS=2
TOOL_RETRY_BASE_DELAY_SECONDS=0.20
TOOL_RETRY_MAX_DELAY_SECONDS=2.0
TOOL_CIRCUIT_FAILURE_THRESHOLD=3
TOOL_CIRCUIT_RECOVERY_SECONDS=30
```

## Contract tests

`tests/test_p25_provider_contracts.py` validates the provider adapters without depending on external services:

- transient 503 -> retry -> success
- consecutive transient failures -> circuit open
- Open-Meteo geocoding + forecast response shape
- Open-Meteo 16-day window boundary
- AMap POI 2.0 business fields
- AMap `status=0` business error is not blindly retried
- AMap geocoding + Route Planning 2.0 response shape

The tests use `httpx.MockTransport`, so they validate the actual HTTP parameter/response handling while remaining deterministic.

## Intent / Tool routing evaluation

`eval/intent_router_eval.jsonl` contains curated knowledge, weather, scenic-live, route, itinerary, freshness-fallback and ambiguous cases.

Run:

```bash
python -m scripts.eval_agent
python -m scripts.eval_agent --fail-on-threshold
```

Metrics:

- Intent Accuracy
- Tool Selection Accuracy

These are regression metrics for the curated set, not a claim of production accuracy.

## Live smoke

Open-Meteo does not require a key:

```bash
TOOL_MOCK_MODE=false python -m scripts.live_provider_smoke --open-meteo
```

AMap requires a Web Service API key:

```bash
TOOL_MOCK_MODE=false AMAP_API_KEY=... python -m scripts.live_provider_smoke --amap
```

CI keeps live calls out of the acceptance gate. A dedicated live-smoke job runs Open-Meteo as a non-blocking check. The AMap smoke only runs when the repository has an `AMAP_API_KEY` secret.

## Data and safety boundary

Tool responses are still treated as external evidence, not instructions. Agent generation only sees normalized `ToolEvidence`, while input validation and provider access remain enforced in code.
