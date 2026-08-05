"""
Minimal FastAPI app (§20's stack choice) exposing /metrics for
Prometheus scrape and /health for basic liveness. This is packaging,
not new detection logic — the interception layer, detectors, and tier
engine are already fully built and tested; this just makes their
metrics scrapeable per §18/§21.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

# Importing these modules is what REGISTERS the simulacrum_* metric
# families with the default Prometheus registry (Counter/Gauge objects
# are created at import time). Without this import, /metrics would
# only ever show default Python/process metrics — no functional
# endpoint exists yet that would trigger this import as a side effect
# (see docs/BACKLOG.md: real POST /intercept endpoint is separate,
# larger, deliberately-deferred work).
import simulacrum.observability  # noqa: F401

app = FastAPI(title="Simulacrum", version="0.0.1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
