"""Deterministic intent classification and capability gating."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import IntFlag


class Capability(IntFlag):
    READ_STATUS = 1
    READ_MEMORY = 2
    PLAN = 4
    HARDWARE_CONTROL = 8
    NETWORK_WRITE = 16
    SYSTEM_CHANGE = 32


CAPABILITY_NAMES = {
    Capability.READ_STATUS: "read_status",
    Capability.READ_MEMORY: "read_memory",
    Capability.PLAN: "plan",
    Capability.HARDWARE_CONTROL: "hardware_control",
    Capability.NETWORK_WRITE: "network_write",
    Capability.SYSTEM_CHANGE: "system_change",
}

_SYSTEM_CHANGE = re.compile(
    r"\b(delete|remove|rm\s|reboot|shutdown|sudo|install|upgrade|deploy|publish|merge|push|chmod|chown)\b",
    re.IGNORECASE,
)
_HARDWARE = re.compile(
    r"\b(gpio|motor|servo|fan|relay|esp32|actuate|physical\s+control|turn\s+(?:on|off))\b",
    re.IGNORECASE,
)
_NETWORK_WRITE = re.compile(
    r"\b(send|post|upload|webhook|email|message|dns|cloudflare|publish)\b",
    re.IGNORECASE,
)
_MEMORY = re.compile(r"\b(memory|remember|recall|history|repo(?:sitory)?)\b", re.IGNORECASE)
_STATUS = re.compile(r"\b(status|health|temperature|cpu|ram|disk|uptime)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    category: str
    mode: str
    required_capability: str
    capability_available: bool
    signed_approval_required: bool
    action_execution_allowed: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def capabilities_for_mask(mask: int) -> list[str]:
    return [name for capability, name in CAPABILITY_NAMES.items() if mask & capability]


def assess_intent(intent: str, mask: int) -> PolicyDecision:
    """Classify intent without calling a model; this function never executes."""

    if _SYSTEM_CHANGE.search(intent):
        required = Capability.SYSTEM_CHANGE
        category = "system_change"
    elif _HARDWARE.search(intent):
        required = Capability.HARDWARE_CONTROL
        category = "hardware_control"
    elif _NETWORK_WRITE.search(intent):
        required = Capability.NETWORK_WRITE
        category = "network_write"
    elif _MEMORY.search(intent):
        required = Capability.READ_MEMORY
        category = "memory_read"
    elif _STATUS.search(intent):
        required = Capability.READ_STATUS
        category = "status_read"
    else:
        required = Capability.PLAN
        category = "answer_or_plan"

    available = bool(mask & required)
    high_risk = required in {
        Capability.HARDWARE_CONTROL,
        Capability.NETWORK_WRITE,
        Capability.SYSTEM_CHANGE,
    }
    if high_risk:
        mode = "requires_approval" if available else "blocked"
        reason = (
            "Capability is registered, but this cognitive service is plan-only and "
            "requires an Ed25519-signed downstream approval."
            if available
            else "Required capability is not enabled in the runtime mask."
        )
    elif available:
        mode = "answer" if required in {Capability.READ_STATUS, Capability.READ_MEMORY} else "plan_only"
        reason = "Read or planning capability is available; no physical action will run."
    else:
        mode = "blocked"
        reason = "Required capability is not enabled in the runtime mask."

    return PolicyDecision(
        category=category,
        mode=mode,
        required_capability=CAPABILITY_NAMES[required],
        capability_available=available,
        signed_approval_required=high_risk,
        action_execution_allowed=False,
        reason=reason,
    )

