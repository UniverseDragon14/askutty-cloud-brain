"""Validated runtime configuration for the Universal Dragon sidecar."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ALLOWED_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
ALLOWED_MODELS = {"gpt-5.6", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _boolean(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True, slots=True)
class DragonConfig:
    """All values needed by the sidecar, with safe localhost defaults."""

    api_key: str | None
    auth_token: str | None
    prompt_path: Path
    repository_scope_path: Path
    telemetry_path: Path
    model: str = "gpt-5.6-terra"
    reasoning_effort: str = "medium"
    bind_host: str = "127.0.0.1"
    port: int = 7798
    capability_mask: int = 7
    max_input_chars: int = 8_000
    max_requests_per_minute: int = 30
    request_timeout_seconds: int = 45
    telemetry_max_age_seconds: int = 30
    safety_identifier: str | None = None
    trust_cloudflare_headers: bool = False

    @property
    def missing_configuration(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.api_key:
            missing.append("OPENAI_API_KEY")
        if not self.auth_token:
            missing.append("ASKUTTY_TOKEN")
        return tuple(missing)

    @property
    def ready(self) -> bool:
        return not self.missing_configuration

    @classmethod
    def from_env(cls, repository_root: Path | None = None) -> "DragonConfig":
        root = repository_root or Path(__file__).resolve().parents[2]
        model = os.getenv("DRAGON_MODEL", "gpt-5.6-terra").strip()
        if model not in ALLOWED_MODELS:
            raise ValueError("DRAGON_MODEL must be a supported GPT-5.6 model")

        reasoning_effort = os.getenv("DRAGON_REASONING_EFFORT", "medium").strip()
        if reasoning_effort not in ALLOWED_REASONING_EFFORTS:
            raise ValueError("DRAGON_REASONING_EFFORT is invalid")

        safety_identifier = os.getenv("DRAGON_SAFETY_IDENTIFIER") or None
        if safety_identifier and not (8 <= len(safety_identifier) <= 64):
            raise ValueError("DRAGON_SAFETY_IDENTIFIER must be 8-64 characters")

        return cls(
            api_key=os.getenv("OPENAI_API_KEY") or None,
            auth_token=os.getenv("ASKUTTY_TOKEN") or None,
            prompt_path=Path(
                os.getenv(
                    "DRAGON_PROMPT_PATH",
                    root / "prompts" / "universal_dragon_system_prompt.txt",
                )
            ),
            repository_scope_path=Path(
                os.getenv(
                    "DRAGON_REPOSITORY_SCOPE_PATH",
                    root / "data" / "repository_scope.json",
                )
            ),
            telemetry_path=Path(
                os.getenv(
                    "DRAGON_TELEMETRY_PATH",
                    "/run/universal-dragon/telemetry.json",
                )
            ),
            model=model,
            reasoning_effort=reasoning_effort,
            bind_host=os.getenv("DRAGON_BIND_HOST", "127.0.0.1"),
            port=_bounded_int("DRAGON_PORT", 7798, 1024, 65535),
            capability_mask=_bounded_int("DRAGON_CAPABILITY_MASK", 7, 0, 63),
            max_input_chars=_bounded_int("DRAGON_MAX_INPUT_CHARS", 8_000, 128, 32_000),
            max_requests_per_minute=_bounded_int(
                "DRAGON_MAX_REQUESTS_PER_MINUTE", 30, 1, 300
            ),
            request_timeout_seconds=_bounded_int(
                "DRAGON_REQUEST_TIMEOUT_SECONDS", 45, 5, 180
            ),
            telemetry_max_age_seconds=_bounded_int(
                "DRAGON_TELEMETRY_MAX_AGE_SECONDS", 30, 1, 3600
            ),
            safety_identifier=safety_identifier,
            trust_cloudflare_headers=_boolean("DRAGON_TRUST_CLOUDFLARE_HEADERS"),
        )

