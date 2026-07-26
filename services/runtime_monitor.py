"""Cross-service health, heartbeat, and guarded restart integration."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import requests

_local_heartbeats: dict[str, dict] = {}
HEARTBEAT_TTL_SECONDS = int(os.getenv("SERVICE_HEARTBEAT_TTL_SECONDS", "120"))


def _redis():
    try:
        import redis
        url = os.getenv("REDIS_URL", "").strip()
        return redis.from_url(url, decode_responses=True) if url else None
    except Exception:
        return None


def record_heartbeat(service: str, metadata: dict | None = None) -> None:
    payload = {
        "service": service,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "epoch": time.time(),
        "pid": os.getpid(),
        "metadata": metadata or {},
    }
    _local_heartbeats[service] = payload
    client = _redis()
    if client:
        try:
            client.setex(
                f"smartflow:heartbeat:{service}",
                HEARTBEAT_TTL_SECONDS,
                json.dumps(payload),
            )
        except Exception:
            pass


def redis_health() -> dict:
    client = _redis()
    if not client:
        return {"configured": False, "healthy": False, "detail": "REDIS_URL not configured"}
    try:
        started = time.perf_counter()
        client.ping()
        return {
            "configured": True,
            "healthy": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:
        return {"configured": True, "healthy": False, "detail": str(exc)[:200]}


def service_heartbeats(services=("api", "ai-worker", "scheduler")) -> list[dict]:
    client = _redis()
    now = time.time()
    rows = []
    for service in services:
        payload = None
        if client:
            try:
                raw = client.get(f"smartflow:heartbeat:{service}")
                payload = json.loads(raw) if raw else None
            except Exception:
                payload = None
        payload = payload or _local_heartbeats.get(service)
        age = now - float(payload.get("epoch", 0)) if payload else None
        rows.append({
            "service": service,
            "healthy": age is not None and age <= HEARTBEAT_TTL_SECONDS,
            "age_seconds": round(age, 1) if age is not None else None,
            "last_seen": payload.get("timestamp") if payload else None,
            "pid": payload.get("pid") if payload else None,
            "metadata": payload.get("metadata", {}) if payload else {},
        })
    return rows


def system_resources() -> dict:
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory = psutil.virtual_memory()
        return {
            "available": True,
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "ram_percent": memory.percent,
            "ram_used_mb": round(memory.used / 1024 / 1024, 1),
            "ram_total_mb": round(memory.total / 1024 / 1024, 1),
            "process_rss_mb": round(process.memory_info().rss / 1024 / 1024, 1),
            "process_threads": process.num_threads(),
        }
    except Exception as exc:
        return {"available": False, "detail": str(exc)[:200]}


def request_restart(service: str, requested_by: int) -> dict:
    webhook = os.getenv("SYSTEM_RESTART_WEBHOOK", "").strip()
    if not webhook:
        return {
            "ok": False,
            "status": 503,
            "error": "SYSTEM_RESTART_WEBHOOK is not configured",
        }
    response = requests.post(
        webhook,
        json={"service": service, "requested_by": requested_by, "source": "smartflow-admin"},
        timeout=15,
    )
    return {
        "ok": response.ok,
        "status": 202 if response.ok else 502,
        "provider_status": response.status_code,
    }
