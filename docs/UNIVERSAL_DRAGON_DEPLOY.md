# Universal Dragon NOVA Core v1

This slice adds a production-safe cognitive sidecar to the private ASKUTTY Cloud
Brain repository. It does not replace the existing ASKUTTY service and does not
modify QBIT NOVA C or the novakutty.universaldragon.com Devpost project.

## Architecture

```text
Huawei / trusted client
        |
        | X-ASKUTTY-TOKEN
        v
Cloudflare Tunnel (optional, not configured by this PR)
        |
        v
127.0.0.1:7798  Universal Dragon sidecar
        |        - deterministic capability gate
        |        - local telemetry allowlist
        |        - no hardware execution
        v
OpenAI Responses API (GPT-5.6 family)
```

The service uses the Responses API with `instructions`, Structured Outputs via
`text.format`, `store=false`, bounded input/output, timeout/retry controls, and an
optional privacy-preserving `safety_identifier`.

Official references:

- https://developers.openai.com/api/docs/guides/latest-model
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/deployment-checklist

## Truth boundary

- Persona body cues are explicitly symbolic.
- The 75-repository catalog is metadata only; it is not proof that code was read.
- Runtime values come only from the allowlisted local telemetry file.
- The sidecar never executes hardware, shell, network-write, or system-change
  actions.
- High-risk intent returns `requires_approval` or `blocked` and always reports
  `action_executed=false`.
- A future executor must independently verify an Ed25519 approval envelope and
  return an execution receipt before any action may be described as completed.

## Endpoints

| Endpoint | Authentication | Purpose |
| --- | --- | --- |
| `GET /health` | None | Process readiness and safe truth-boundary flags |
| `GET /v1/status` | `X-ASKUTTY-TOKEN` | Capability, repository-scope, and telemetry status |
| `POST /v1/respond` | `X-ASKUTTY-TOKEN` | Structured NOVA response and plan-only decision |

Example request body:

```json
{
  "intent": "Pi status sollu",
  "language": "tanglish"
}
```

## Pi 5 install after merge

Keep the current ASKUTTY and Novakutty services running. Install this as a separate
sidecar only after reviewing and merging the draft PR.

```bash
cd /home/aslam/askutty-cloud-brain
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

install -d -m 700 /home/aslam/.config/universal-dragon
install -m 600 /dev/null /home/aslam/.config/universal-dragon/dragon.env
```

Store real values only in
`/home/aslam/.config/universal-dragon/dragon.env`. Never paste them into chat,
commit them, or put them in a command that may enter shell history.

Required variables:

```text
OPENAI_API_KEY          required; provision securely
ASKUTTY_TOKEN           required; long random local secret
DRAGON_SAFETY_IDENTIFIER  recommended; privacy-preserving stable identifier
```

Install the reviewed unit:

```bash
sudo install -m 0644 \
  askutty-pi5/universal-dragon.service \
  /etc/systemd/system/universal-dragon.service
sudo systemctl daemon-reload
sudo systemctl enable --now universal-dragon.service
curl --silent --show-error http://127.0.0.1:7798/health
```

Expected health state is `ok=true` and `ready=true`. If `ready=false`, fix only the
listed missing configuration; do not weaken authentication.

## Cloudflare handoff

No DNS or tunnel route is changed by this PR. After the local health and authenticated
contract tests pass, a new hostname may be routed to `http://127.0.0.1:7798`.
Do not reuse or modify the existing `novakutty.universaldragon.com` route.

Recommended candidate: `dragon.universaldragon.com`. Confirm the hostname before
changing Cloudflare.

## Rollback

The existing ASKUTTY runtime is independent, so rollback is isolated:

```bash
sudo systemctl disable --now universal-dragon.service
sudo systemctl status askutty-pi5.service --no-pager
```

This stops only the new sidecar. It does not touch ASKUTTY, Novakutty, QBIT NOVA,
Cloudflare, ESP32 nodes, or GitHub repository data.
