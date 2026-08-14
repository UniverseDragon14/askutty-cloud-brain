"""OpenAI Responses API adapter with a server-enforced truth boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import DragonConfig
from .policy import PolicyDecision, assess_intent, capabilities_for_mask


class DragonError(RuntimeError):
    """Base class for errors that are safe to map at the HTTP boundary."""


class DragonUnavailable(DragonError):
    """Configuration or upstream availability prevents a response."""


class DragonProtocolError(DragonError):
    """The model response failed the local contract."""


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "persona_cue": {
            "type": "string",
            "enum": ["none", "eyes_steady", "eyes_amber", "wings_folded", "wings_ready"],
            "description": "A symbolic persona cue, never a physical-state claim.",
        },
        "message": {"type": "string", "minLength": 1, "maxLength": 4000},
        "intent_summary": {"type": "string", "minLength": 1, "maxLength": 500},
        "language": {"type": "string", "enum": ["en", "ta", "tanglish"]},
        "proposed_steps": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
            "maxItems": 8,
        },
        "limitations": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 500},
            "maxItems": 6,
        },
        "rollback_note": {
            "type": ["string", "null"],
            "maxLength": 1000,
        },
    },
    "required": [
        "persona_cue",
        "message",
        "intent_summary",
        "language",
        "proposed_steps",
        "limitations",
        "rollback_note",
    ],
}

_OUTPUT_KEYS = frozenset(OUTPUT_SCHEMA["required"])
_CUES = frozenset(OUTPUT_SCHEMA["properties"]["persona_cue"]["enum"])
_LANGUAGES = frozenset(OUTPUT_SCHEMA["properties"]["language"]["enum"])


def _read_text_file(path: Path, maximum_bytes: int) -> str:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum_bytes:
            raise DragonUnavailable(f"invalid_runtime_file:{path.name}")
        return path.read_text(encoding="utf-8")
    except DragonUnavailable:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise DragonUnavailable(f"unreadable_runtime_file:{path.name}") from exc


def _repository_summary(path: Path) -> dict[str, object]:
    raw = _read_text_file(path, 256_000)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DragonUnavailable("repository_scope_json_invalid") from exc
    if not isinstance(payload, dict):
        raise DragonUnavailable("repository_scope_payload_invalid")

    repositories = payload.get("repositories", [])
    if not isinstance(repositories, list):
        repositories = []
    public_count = sum(
        1 for repo in repositories if isinstance(repo, dict) and repo.get("visibility") == "public"
    )
    private_count = sum(
        1 for repo in repositories if isinstance(repo, dict) and repo.get("visibility") == "private"
    )
    return {
        "inventory_count": len(repositories),
        "public_count": public_count,
        "private_count": private_count,
        "inventory_is_metadata_only": True,
        "default_access": payload.get("default_access", "read_only"),
        "write_allowlist": payload.get("write_allowlist", []),
        "protected_projects": payload.get("protected_projects", []),
    }


def _validate_model_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != _OUTPUT_KEYS:
        raise DragonProtocolError("model_output_shape_invalid")
    if payload.get("persona_cue") not in _CUES:
        raise DragonProtocolError("model_persona_cue_invalid")
    if payload.get("language") not in _LANGUAGES:
        raise DragonProtocolError("model_language_invalid")
    for key in ("message", "intent_summary"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise DragonProtocolError(f"model_{key}_invalid")
    for key, maximum in (("proposed_steps", 8), ("limitations", 6)):
        value = payload.get(key)
        if not isinstance(value, list) or len(value) > maximum:
            raise DragonProtocolError(f"model_{key}_invalid")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise DragonProtocolError(f"model_{key}_invalid")
    rollback_note = payload.get("rollback_note")
    if rollback_note is not None and not isinstance(rollback_note, str):
        raise DragonProtocolError("model_rollback_note_invalid")
    return payload


class UniversalDragonCore:
    """Plan-only cognitive core. All execution claims are added by local code."""

    def __init__(self, config: DragonConfig, client: object | None = None) -> None:
        self.config = config
        self.instructions = _read_text_file(config.prompt_path, 128_000)
        self.repository_scope = _repository_summary(config.repository_scope_path)
        if client is not None:
            self.client = client
        elif config.api_key:
            from openai import OpenAI

            self.client = OpenAI(
                api_key=config.api_key,
                timeout=config.request_timeout_seconds,
                max_retries=2,
            )
        else:
            self.client = None

    def respond(
        self,
        *,
        intent: str,
        requested_language: str,
        runtime_evidence: dict[str, object],
        request_id: str,
    ) -> dict[str, object]:
        if self.client is None or not self.config.api_key:
            raise DragonUnavailable("openai_api_key_not_configured")

        policy: PolicyDecision = assess_intent(intent, self.config.capability_mask)
        context = {
            "USER_INTENT": intent,
            "REQUESTED_LANGUAGE": requested_language,
            "POLICY_DECISION": policy.as_dict(),
            "RUNTIME_EVIDENCE": runtime_evidence,
            "REPOSITORY_SCOPE": self.repository_scope,
            "CAPABILITY_MASK": {
                "value": self.config.capability_mask,
                "enabled": capabilities_for_mask(self.config.capability_mask),
            },
            "EXECUTION_RECEIPT": None,
            "REQUEST_ID": request_id,
        }
        request_kwargs: dict[str, object] = {
            "model": self.config.model,
            "instructions": self.instructions,
            "input": json.dumps(context, ensure_ascii=False, separators=(",", ":")),
            "reasoning": {"effort": self.config.reasoning_effort},
            "text": {
                "verbosity": "low",
                "format": {
                    "type": "json_schema",
                    "name": "universal_dragon_response",
                    "strict": True,
                    "schema": OUTPUT_SCHEMA,
                },
            },
            "max_output_tokens": 1_200,
            "store": False,
        }
        if self.config.safety_identifier:
            request_kwargs["safety_identifier"] = self.config.safety_identifier

        try:
            response = self.client.responses.create(**request_kwargs)
        except Exception as exc:
            raise DragonUnavailable(f"openai_upstream_error:{type(exc).__name__}") from exc

        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise DragonProtocolError("model_returned_no_structured_output")
        try:
            model_payload = _validate_model_payload(json.loads(output_text))
        except json.JSONDecodeError as exc:
            raise DragonProtocolError("model_output_json_invalid") from exc

        model_payload["execution"] = {
            **policy.as_dict(),
            "action_executed": False,
            "execution_receipt": None,
        }
        model_payload["runtime_evidence"] = runtime_evidence
        model_payload["truth_boundary"] = {
            "persona_cue_is_symbolic": True,
            "repository_inventory_is_metadata_only": True,
            "physical_action_executed": False,
            "physical_qpu_present": False,
        }
        model_payload["request_id"] = request_id
        model_payload["model"] = self.config.model
        return model_payload

