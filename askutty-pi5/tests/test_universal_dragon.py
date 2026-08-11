import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from universal_dragon.api import create_app
from universal_dragon.config import DragonConfig
from universal_dragon.telemetry import load_runtime_evidence


VALID_MODEL_PAYLOAD = {
    "persona_cue": "eyes_steady",
    "message": "All reported systems are within the supplied evidence boundary.",
    "intent_summary": "Read the current status.",
    "language": "en",
    "proposed_steps": [],
    "limitations": ["No live hardware action was executed."],
    "rollback_note": None,
}


class FakeResponses:
    def __init__(self, payload=None):
        self.payload = VALID_MODEL_PAYLOAD if payload is None else payload
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.payload, str):
            output_text = self.payload
        else:
            output_text = json.dumps(self.payload)
        return SimpleNamespace(output_text=output_text)


class FakeClient:
    def __init__(self, payload=None):
        self.responses = FakeResponses(payload)


def make_config(
    tmp_path,
    *,
    api_key="test-api-key-not-real",
    auth_token="test-auth-token",
    capability_mask=7,
    rate_limit=30,
):
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text("Follow the truth boundary.", encoding="utf-8")
    scope_path = tmp_path / "repository_scope.json"
    scope_path.write_text(
        json.dumps(
            {
                "default_access": "read_only",
                "write_allowlist": ["UniverseDragon14/askutty-cloud-brain"],
                "protected_projects": ["QBIT NOVA C", "novakutty.universaldragon.com"],
                "repositories": [
                    {"name": "public-one", "visibility": "public"},
                    {"name": "private-one", "visibility": "private"},
                ],
            }
        ),
        encoding="utf-8",
    )
    return DragonConfig(
        api_key=api_key,
        auth_token=auth_token,
        prompt_path=prompt_path,
        repository_scope_path=scope_path,
        telemetry_path=tmp_path / "telemetry.json",
        capability_mask=capability_mask,
        max_requests_per_minute=rate_limit,
        safety_identifier="aslam-test-identifier",
    )


def auth_headers():
    return {"X-ASKUTTY-TOKEN": "test-auth-token"}


def test_health_reports_missing_key_without_revealing_a_value(tmp_path):
    config = make_config(tmp_path, api_key=None)
    app = create_app(config, client=FakeClient())

    response = app.test_client().get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["ready"] is False
    assert payload["missing_configuration"] == ["OPENAI_API_KEY"]
    assert "test-api-key" not in response.get_data(as_text=True)


def test_respond_rejects_missing_and_wrong_auth(tmp_path):
    app = create_app(make_config(tmp_path), client=FakeClient())
    client = app.test_client()

    missing = client.post("/v1/respond", json={"intent": "status"})
    wrong = client.post(
        "/v1/respond",
        json={"intent": "status"},
        headers={"X-ASKUTTY-TOKEN": "wrong"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_respond_uses_responses_api_structured_output_and_store_false(tmp_path):
    fake = FakeClient()
    app = create_app(make_config(tmp_path), client=fake)

    response = app.test_client().post(
        "/v1/respond",
        json={"intent": "Pi status sollu", "language": "tanglish"},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    result = response.get_json()["result"]
    assert result["execution"]["action_executed"] is False
    assert result["execution"]["mode"] == "answer"
    assert result["truth_boundary"] == {
        "persona_cue_is_symbolic": True,
        "physical_action_executed": False,
        "physical_qpu_present": False,
        "repository_inventory_is_metadata_only": True,
    }

    assert len(fake.responses.calls) == 1
    call = fake.responses.calls[0]
    assert call["model"] == "gpt-5.6-terra"
    assert call["store"] is False
    assert call["reasoning"] == {"effort": "medium"}
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["strict"] is True
    assert call["safety_identifier"] == "aslam-test-identifier"
    sent_context = json.loads(call["input"])
    assert sent_context["EXECUTION_RECEIPT"] is None
    assert sent_context["REPOSITORY_SCOPE"]["inventory_is_metadata_only"] is True


@pytest.mark.parametrize(
    ("capability_mask", "expected_mode", "available"),
    [(7, "blocked", False), (15, "requires_approval", True)],
)
def test_hardware_intent_never_executes(capability_mask, expected_mode, available, tmp_path):
    fake = FakeClient()
    app = create_app(
        make_config(tmp_path, capability_mask=capability_mask),
        client=fake,
    )

    response = app.test_client().post(
        "/v1/respond",
        json={"intent": "Turn on the GPIO motor"},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    execution = response.get_json()["result"]["execution"]
    assert execution["mode"] == expected_mode
    assert execution["required_capability"] == "hardware_control"
    assert execution["capability_available"] is available
    assert execution["signed_approval_required"] is True
    assert execution["action_executed"] is False


def test_invalid_model_contract_returns_safe_502(tmp_path):
    fake = FakeClient({"message": "missing required fields"})
    app = create_app(make_config(tmp_path), client=fake)

    response = app.test_client().post(
        "/v1/respond",
        json={"intent": "status"},
        headers=auth_headers(),
    )

    assert response.status_code == 502
    assert response.get_json()["error"]["code"] == "model_contract_failed"
    assert "missing required fields" not in response.get_data(as_text=True)


def test_rate_limit_is_enforced_before_second_model_call(tmp_path):
    fake = FakeClient()
    app = create_app(
        make_config(tmp_path, rate_limit=1),
        client=fake,
        clock=lambda: 100.0,
    )
    client = app.test_client()

    first = client.post("/v1/respond", json={"intent": "status"}, headers=auth_headers())
    second = client.post("/v1/respond", json={"intent": "status"}, headers=auth_headers())

    assert first.status_code == 200
    assert second.status_code == 429
    assert len(fake.responses.calls) == 1


def test_telemetry_accepts_only_allowlisted_fresh_numeric_values(tmp_path):
    telemetry_path = tmp_path / "telemetry.json"
    telemetry_path.write_text(
        json.dumps(
            {
                "source": "pi5-local-probe",
                "observed_at": "2026-08-12T01:00:00+04:00",
                "values": {
                    "temperature_c": 48.5,
                    "cpu_percent": 12,
                    "fan_percent": 101,
                    "secret": "must-not-pass",
                },
            }
        ),
        encoding="utf-8",
    )
    now = telemetry_path.stat().st_mtime + 2

    evidence = load_runtime_evidence(telemetry_path, 30, now=now)

    assert evidence["available"] is True
    assert evidence["fresh"] is True
    assert evidence["source"] == "pi5-local-probe"
    assert evidence["values"] == {"cpu_percent": 12.0, "temperature_c": 48.5}
    assert "secret" not in json.dumps(evidence)


def test_status_requires_auth_and_returns_metadata_only_scope(tmp_path):
    app = create_app(make_config(tmp_path), client=FakeClient())
    client = app.test_client()

    assert client.get("/v1/status").status_code == 401
    response = client.get("/v1/status", headers=auth_headers())

    assert response.status_code == 200
    scope = response.get_json()["repository_scope"]
    assert scope["inventory_count"] == 2
    assert scope["public_count"] == 1
    assert scope["private_count"] == 1
    assert scope["inventory_is_metadata_only"] is True

