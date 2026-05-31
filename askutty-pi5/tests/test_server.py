import importlib.util
import json
import sys
import types
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "server.py"
FAKE_TOKEN = "test-token"


@pytest.fixture()
def server_module(monkeypatch, tmp_path):
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setenv("ASKUTTY_TOKEN", FAKE_TOKEN)
    monkeypatch.chdir(tmp_path)

    module_name = f"server_under_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None

    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    def fake_check_output(cmd, *args, **kwargs):
        if cmd == ["uptime", "-p"]:
            return b"up 1 hour"
        if cmd == ["vcgencmd", "measure_temp"]:
            return b"temp=42.5'C\n"
        if cmd == ["date"]:
            return b"Sun May 31 12:00:00 +04 2026\n"
        if cmd == "df -h /":
            return (
                b"Filesystem Size Used Avail Use% Mounted on\n"
                b"/dev/root 100G 20G 80G 20% /\n"
            )
        if cmd == "uptime":
            return b"12:00:00 up 1 hour, 1 user, load average: 0.00, 0.01, 0.05\n"
        if cmd == "free -h":
            return b"Mem: 8Gi 2Gi 6Gi\n"
        if cmd == "systemctl is-active askutty-pi5.service":
            return b"active\n"
        if cmd == "git status":
            return b"On branch main\nnothing to commit\n"
        if cmd == "systemctl is-active nova-war-room":
            return b"inactive\n"
        if cmd == "hostname -I":
            return b"192.0.2.10\n"
        raise AssertionError(f"Unexpected check_output command: {cmd!r}")

    monkeypatch.setattr(module.subprocess, "check_output", fake_check_output)
    monkeypatch.setattr(module.psutil, "cpu_percent", lambda: 12.5)
    monkeypatch.setattr(
        module.psutil, "virtual_memory", lambda: types.SimpleNamespace(percent=34.0)
    )
    monkeypatch.setattr(
        module.psutil,
        "disk_usage",
        lambda path: types.SimpleNamespace(percent=56.0),
    )
    module.app.config.update(TESTING=True)
    return module


@pytest.fixture()
def client(server_module):
    return server_module.app.test_client()


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value))


def auth_headers():
    return {"X-ASKUTTY-TOKEN": FAKE_TOKEN}


def test_import_creates_temp_memory_and_action_log(server_module, tmp_path):
    assert read_json(tmp_path / "memory.json") == {"entries": []}
    assert read_json(tmp_path / "action_log.json") == []


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "OK"


def test_api_metrics_returns_mocked_values(client):
    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert response.get_json() == {
        "cpu": 12.5,
        "ram": 34.0,
        "temp": "42.5",
        "disk": 56.0,
    }


def test_api_status_returns_mocked_values(client):
    response = client.get("/api/status")

    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["version"] == "0.6"
    assert data["uptime"] == "up 1 hour"
    assert data["cpu"] == 12.5
    assert data["ram"] == 34.0
    assert data["temp"] == "42.5"
    assert data["disk"] == 56.0


def test_protected_operator_routes_reject_missing_or_wrong_token(client):
    missing = client.get("/plan", query_string={"q": "disk check"})
    wrong = client.get(
        "/plan",
        query_string={"q": "disk check", "token": "wrong-token"},
    )

    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert "Token required" in missing.get_data(as_text=True)
    assert "Token required" in wrong.get_data(as_text=True)


def test_protected_operator_routes_accept_header_token(client, tmp_path, monkeypatch, server_module):
    monkeypatch.setattr(server_module.time, "time", lambda: 1234567890)

    response = client.get(
        "/plan",
        query_string={"q": "disk check"},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert "PLAN CREATED" in response.get_data(as_text=True)
    logs = read_json(tmp_path / "action_log.json")
    assert logs == [
        {
            "id": "1234567890",
            "user_request": "disk check",
            "command": "df -h /",
            "risk_level": "Low",
            "explanation": "Safe read-only command to check disk check.",
            "status": "pending",
            "timestamp": logs[0]["timestamp"],
        }
    ]


def test_protected_operator_routes_accept_query_token(client):
    response = client.get("/logs", query_string={"token": FAKE_TOKEN})

    assert response.status_code == 200
    assert "ACTION LOGS" in response.get_data(as_text=True)


def test_ask_without_query_returns_message(client):
    response = client.get("/ask")

    assert response.status_code == 200
    assert "No input received." in response.get_data(as_text=True)


def test_ask_remember_writes_memory_and_search_finds_it(client, tmp_path):
    remember = client.get("/ask", query_string={"q": "remember launch checklist"})

    assert remember.status_code == 200
    assert "MEMORIZED: launch checklist" in remember.get_data(as_text=True)
    memory = read_json(tmp_path / "memory.json")
    assert memory["entries"] == [
        {
            "query": "remember launch checklist",
            "memo": "launch checklist",
            "timestamp": "Sun May 31 12:00:00 +04 2026",
        }
    ]

    search = client.get("/ask", query_string={"q": "search memory launch"})

    assert search.status_code == 200
    search_text = search.get_data(as_text=True)
    assert "SEARCH RESULTS FOR" in search_text
    assert "launch" in search_text
    assert "launch checklist" in search_text


def test_ask_unknown_input_is_logged(client, tmp_path):
    response = client.get("/ask", query_string={"q": "capture this note"})

    assert response.status_code == 200
    assert "INPUT LOGGED: capture this note" in response.get_data(as_text=True)
    memory = read_json(tmp_path / "memory.json")
    assert memory["entries"] == [
        {
            "query": "capture this note",
            "timestamp": "Sun May 31 12:00:00 +04 2026",
        }
    ]


def test_ask_forget_last_removes_last_memory_entry(client, tmp_path):
    write_json(
        tmp_path / "memory.json",
        {
            "entries": [
                {"query": "first", "timestamp": "older"},
                {"query": "second", "timestamp": "newer"},
            ]
        },
    )

    response = client.get("/ask", query_string={"q": "forget last"})

    assert response.status_code == 200
    assert "FORGOTTEN: second" in response.get_data(as_text=True)
    assert read_json(tmp_path / "memory.json") == {
        "entries": [{"query": "first", "timestamp": "older"}]
    }


def test_safe_operator_plan_rejects_unknown_request(client, tmp_path):
    response = client.get(
        "/plan",
        query_string={"q": "inventory check", "token": FAKE_TOKEN},
    )

    assert response.status_code == 200
    assert "UNKNOWN REQUEST. No safe plan available." in response.get_data(as_text=True)
    assert read_json(tmp_path / "action_log.json") == []


@pytest.mark.parametrize(
    "query",
    [
        "rm -rf /tmp/example",
        "sudo reboot",
        "curl http://example.test",
        "show token",
        "show key",
    ],
)
def test_safe_operator_plan_blocks_sensitive_or_destructive_patterns(
    client, tmp_path, query
):
    response = client.get(
        "/plan",
        query_string={"q": query, "token": FAKE_TOKEN},
    )

    assert response.status_code == 200
    assert "BLOCKED: Destructive or sensitive command pattern detected." in (
        response.get_data(as_text=True)
    )
    assert read_json(tmp_path / "action_log.json") == []


def test_safe_operator_approve_executes_pending_plan(client, tmp_path):
    write_json(
        tmp_path / "action_log.json",
        [
            {
                "id": "plan-1",
                "user_request": "disk check",
                "command": "df -h /",
                "risk_level": "Low",
                "explanation": "Safe read-only command to check disk check.",
                "status": "pending",
                "timestamp": "2026-05-31 12:00:00",
            }
        ],
    )

    response = client.get(
        "/approve",
        query_string={"id": "plan-1", "token": FAKE_TOKEN},
    )

    assert response.status_code == 200
    assert "EXECUTED: df -h /" in response.get_data(as_text=True)
    logs = read_json(tmp_path / "action_log.json")
    assert logs[0]["status"] == "approved"
    assert "Filesystem" in logs[0]["output"]
    assert "executed_at" in logs[0]


def test_safe_operator_approve_rejects_non_pending_plan(client, tmp_path):
    write_json(
        tmp_path / "action_log.json",
        [
            {
                "id": "plan-1",
                "user_request": "disk check",
                "command": "df -h /",
                "risk_level": "Low",
                "explanation": "Safe read-only command to check disk check.",
                "status": "approved",
                "timestamp": "2026-05-31 12:00:00",
            }
        ],
    )

    response = client.get(
        "/approve",
        query_string={"id": "plan-1", "token": FAKE_TOKEN},
    )

    assert response.status_code == 200
    assert "Plan already approved." in response.get_data(as_text=True)


def test_safe_operator_approve_latest_executes_newest_pending_plan(client, tmp_path):
    write_json(
        tmp_path / "action_log.json",
        [
            {
                "id": "old",
                "user_request": "disk check",
                "command": "df -h /",
                "risk_level": "Low",
                "explanation": "Safe read-only command to check disk check.",
                "status": "pending",
                "timestamp": "2026-05-31 12:00:00",
            },
            {
                "id": "new",
                "user_request": "ram status",
                "command": "free -h",
                "risk_level": "Low",
                "explanation": "Safe read-only command to check ram status.",
                "status": "pending",
                "timestamp": "2026-05-31 12:01:00",
            },
        ],
    )

    response = client.get("/approve_latest", query_string={"token": FAKE_TOKEN})

    assert response.status_code == 200
    assert "EXECUTED LATEST: free -h" in response.get_data(as_text=True)
    logs = read_json(tmp_path / "action_log.json")
    assert logs[0]["status"] == "pending"
    assert logs[1]["status"] == "approved"
    assert "Mem:" in logs[1]["output"]


def test_safe_operator_reject_marks_plan_rejected(client, tmp_path):
    write_json(
        tmp_path / "action_log.json",
        [
            {
                "id": "plan-1",
                "user_request": "disk check",
                "command": "df -h /",
                "risk_level": "Low",
                "explanation": "Safe read-only command to check disk check.",
                "status": "pending",
                "timestamp": "2026-05-31 12:00:00",
            }
        ],
    )

    response = client.get(
        "/reject",
        query_string={"id": "plan-1", "token": FAKE_TOKEN},
    )

    assert response.status_code == 200
    assert "PLAN plan-1 REJECTED." in response.get_data(as_text=True)
    logs = read_json(tmp_path / "action_log.json")
    assert logs[0]["status"] == "rejected"
