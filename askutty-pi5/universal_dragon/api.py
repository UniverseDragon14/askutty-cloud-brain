"""Flask HTTP boundary for the Universal Dragon cognitive sidecar."""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from collections import defaultdict, deque
from threading import Lock
from typing import Callable

from flask import Flask, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

from .config import DragonConfig
from .core import DragonProtocolError, DragonUnavailable, UniversalDragonCore
from .policy import capabilities_for_mask
from .telemetry import load_runtime_evidence


LOGGER = logging.getLogger("universal_dragon")
ALLOWED_REQUEST_LANGUAGES = {"auto", "en", "ta", "tanglish"}


class SlidingWindowLimiter:
    """Small in-process limiter suitable for a single-worker Pi sidecar."""

    def __init__(self, limit: int, clock: Callable[[], float]) -> None:
        self.limit = limit
        self.clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, identity: str) -> bool:
        now = self.clock()
        cutoff = now - 60.0
        with self._lock:
            events = self._events[identity]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


def _error(code: str, status: int, request_id: str, message: str):
    return (
        jsonify(
            {
                "ok": False,
                "error": {"code": code, "message": message},
                "request_id": request_id,
            }
        ),
        status,
    )


def create_app(
    config: DragonConfig | None = None,
    *,
    client: object | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Flask:
    config = config or DragonConfig.from_env()
    core = UniversalDragonCore(config, client=client)
    limiter = SlidingWindowLimiter(config.max_requests_per_minute, clock)

    app = Flask(__name__)
    app.config.update(
        JSON_SORT_KEYS=True,
        MAX_CONTENT_LENGTH=max(16_384, config.max_input_chars * 4),
        DRAGON_BIND_HOST=config.bind_host,
        DRAGON_PORT=config.port,
    )

    def request_id() -> str:
        return uuid.uuid4().hex

    def authorized() -> bool:
        supplied = request.headers.get("X-ASKUTTY-TOKEN", "")
        expected = config.auth_token or ""
        return bool(expected) and hmac.compare_digest(supplied, expected)

    def client_identity() -> str:
        raw = request.remote_addr or "unknown"
        if config.trust_cloudflare_headers:
            candidate = request.headers.get("CF-Connecting-IP", "").strip()
            if candidate and len(candidate) <= 64:
                raw = candidate
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @app.after_request
    def harden_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def handle_large_request(_error_object):
        return _error("request_too_large", 413, request_id(), "Request body is too large.")

    @app.errorhandler(404)
    def handle_not_found(_error_object):
        return _error("not_found", 404, request_id(), "Endpoint not found.")

    @app.errorhandler(405)
    def handle_method_not_allowed(_error_object):
        return _error("method_not_allowed", 405, request_id(), "Method not allowed.")

    @app.get("/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "ready": config.ready,
                "service": "UNIVERSAL_DRAGON_NOVA_CORE",
                "mode": "plan_only",
                "model": config.model,
                "missing_configuration": list(config.missing_configuration),
                "truth_boundary": {
                    "hardware_execution": False,
                    "physical_qpu_present": False,
                    "repository_inventory_is_metadata_only": True,
                },
            }
        )

    @app.get("/v1/status")
    def status():
        rid = request_id()
        if not config.auth_token:
            return _error(
                "service_not_configured", 503, rid, "ASKUTTY_TOKEN is not configured."
            )
        if not authorized():
            return _error("unauthorized", 401, rid, "Valid X-ASKUTTY-TOKEN required.")
        evidence = load_runtime_evidence(
            config.telemetry_path, config.telemetry_max_age_seconds
        )
        return jsonify(
            {
                "ok": True,
                "request_id": rid,
                "ready": config.ready,
                "model": config.model,
                "capability_mask": config.capability_mask,
                "capabilities": capabilities_for_mask(config.capability_mask),
                "runtime_evidence": evidence,
                "repository_scope": core.repository_scope,
            }
        )

    @app.post("/v1/respond")
    def respond():
        rid = request_id()
        started = clock()
        if not config.auth_token:
            return _error(
                "service_not_configured", 503, rid, "ASKUTTY_TOKEN is not configured."
            )
        if not authorized():
            return _error("unauthorized", 401, rid, "Valid X-ASKUTTY-TOKEN required.")
        if not limiter.allow(client_identity()):
            return _error("rate_limited", 429, rid, "Request rate exceeded.")
        if not request.is_json:
            return _error("json_required", 415, rid, "Content-Type must be application/json.")

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return _error("invalid_json", 400, rid, "JSON body must be an object.")
        intent = payload.get("intent")
        language = payload.get("language", "auto")
        if not isinstance(intent, str) or not intent.strip():
            return _error("intent_required", 400, rid, "A non-empty intent is required.")
        intent = intent.strip()
        if len(intent) > config.max_input_chars:
            return _error("intent_too_large", 413, rid, "Intent exceeds the configured limit.")
        if language not in ALLOWED_REQUEST_LANGUAGES:
            return _error("language_invalid", 400, rid, "Unsupported language selector.")

        evidence = load_runtime_evidence(
            config.telemetry_path, config.telemetry_max_age_seconds
        )
        try:
            result = core.respond(
                intent=intent,
                requested_language=language,
                runtime_evidence=evidence,
                request_id=rid,
            )
        except DragonUnavailable as exc:
            LOGGER.warning(
                "dragon_request_unavailable request_id=%s error_type=%s",
                rid,
                type(exc).__name__,
            )
            return _error("upstream_unavailable", 503, rid, "Dragon brain is not ready.")
        except DragonProtocolError as exc:
            LOGGER.error(
                "dragon_protocol_error request_id=%s error_type=%s",
                rid,
                type(exc).__name__,
            )
            return _error("model_contract_failed", 502, rid, "Model response failed validation.")
        except Exception as exc:
            LOGGER.exception(
                "dragon_internal_error request_id=%s error_type=%s",
                rid,
                type(exc).__name__,
            )
            return _error("internal_error", 500, rid, "Internal service error.")

        elapsed_ms = round((clock() - started) * 1000)
        LOGGER.info("dragon_request_ok request_id=%s elapsed_ms=%d", rid, elapsed_ms)
        return jsonify({"ok": True, "result": result})

    return app

