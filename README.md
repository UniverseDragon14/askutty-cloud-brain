# ASKUTTY Pi5 Cloud Brain

Private Flask dashboard and approval-first command planner for a Raspberry Pi 5.

## Implemented service

**askutty-pi5/server.py** provides:

- CPU, RAM, disk, uptime, and Pi temperature metrics;
- health and status APIs;
- memory/status pages;
- plan, approve, reject, and action-log flows;
- a small fixed command map for disk, CPU, RAM, selected service, Git, and network status;
- a War Room page.

Key routes include **/api/metrics**, **/api/status**, **/api/memory**, **/health**, **/plan**, **/approve**, **/reject**, **/logs**, and **/warroom**.

The test suite in **askutty-pi5/tests/test_server.py** exercises authentication, planning, approval, and service behavior.

## Run locally

~~~bash
export ASKUTTY_TOKEN="create-a-long-random-local-token"
python3 askutty-pi5/server.py
~~~

The current server listens on port **7797**.

Requests to protected operations must send the token in the **X-ASKUTTY-TOKEN** header.

## Approval model

~~~text
request
  -> exact phrase lookup in SAFE_COMMANDS
  -> pending plan
  -> explicit approve or reject
  -> bounded command
  -> action log
~~~

Commands not present in the fixed map are rejected.

## Security boundary

The application currently binds to **0.0.0.0** and some approved commands are executed through shell=True. The fixed map limits input selection, but this is not sufficient for direct Internet exposure.

- Keep it behind a private firewall or bind it to loopback.
- Never expose it through a public tunnel without additional authentication, TLS/origin controls, rate limits, CSRF protection, and route-by-route review.
- Replace shell strings with argument arrays before production use.
- Store ASKUTTY_TOKEN only in the local environment.
- Metrics and status pages expose host information.
- Approval is local application control, not a cryptographic signature.

## Truth boundary

This is a Pi dashboard and allowlisted planner. It is not an unrestricted terminal, autonomous system administrator, or hardware controller.

## Status

Functional private prototype with tests; production hardening is still required.
