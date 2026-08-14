"""Read and sanitize local telemetry without inventing hardware state."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


NUMERIC_LIMITS = {
    "cpu_percent": (0.0, 100.0),
    "ram_percent": (0.0, 100.0),
    "disk_percent": (0.0, 100.0),
    "temperature_c": (-40.0, 150.0),
    "fan_percent": (0.0, 100.0),
}


def unavailable(reason: str) -> dict[str, object]:
    return {
        "available": False,
        "fresh": False,
        "source": None,
        "observed_at": None,
        "values": {},
        "reason": reason,
    }


def load_runtime_evidence(
    path: Path,
    max_age_seconds: int,
    *,
    now: float | None = None,
) -> dict[str, object]:
    """Load a small, non-symlink JSON snapshot and return only allowlisted facts."""

    try:
        stat_result = path.lstat()
    except FileNotFoundError:
        return unavailable("telemetry_file_missing")
    except OSError:
        return unavailable("telemetry_file_unreadable")

    if path.is_symlink():
        return unavailable("telemetry_symlink_rejected")
    if not path.is_file() or stat_result.st_size > 32_768:
        return unavailable("telemetry_file_invalid")

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return unavailable("telemetry_json_invalid")

    if not isinstance(payload, dict):
        return unavailable("telemetry_payload_invalid")

    values: dict[str, float] = {}
    raw_values = payload.get("values", {})
    if isinstance(raw_values, dict):
        for key, (minimum, maximum) in NUMERIC_LIMITS.items():
            value = raw_values.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric = float(value)
                if minimum <= numeric <= maximum:
                    values[key] = numeric

    source = payload.get("source")
    if not isinstance(source, str) or not source.strip() or len(source) > 120:
        source = "local_telemetry_file"

    observed_at = payload.get("observed_at")
    if not isinstance(observed_at, str) or len(observed_at) > 64:
        observed_at = None

    current_time = time.time() if now is None else now
    age_seconds = max(0.0, current_time - stat_result.st_mtime)
    fresh = age_seconds <= max_age_seconds
    return {
        "available": bool(values),
        "fresh": fresh,
        "source": source,
        "observed_at": observed_at,
        "values": values,
        "reason": None if values else "no_allowlisted_values",
    }

