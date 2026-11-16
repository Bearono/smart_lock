"""Exercise a fresh, explicitly simulated service over verified TLS; leave it locked."""

import argparse
import json
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import urlsplit

import requests
from smartlock_protocol.command_auth import sign

ROOT = Path(__file__).resolve().parents[1]


def verify(endpoint, key_path, ca_path):
    if urlsplit(endpoint).scheme != "https":
        raise ValueError("Verified HTTPS is required")
    secret = key_path.read_text().strip()
    http = requests.Session()
    http.trust_env = False
    checks = {}

    def send(path, body, headers):
        return http.post(
            endpoint + path,
            data=body,
            headers=headers,
            verify=str(ca_path),
            timeout=5,
            allow_redirects=False,
        )

    def post(path, payload, code=200):
        response = send(path, *sign(secret, path, payload))
        if response.status_code != code:
            raise AssertionError(f"{path} returned {response.status_code}, expected {code}")
        return response.json()

    def command(target):
        return {
            "id": secrets.token_hex(16),
            "target_status": target,
            "expires_at": time.time() + 30,
        }

    sys.path.insert(0, str(ROOT / "apps/lock_sim"))
    from viewer import viewer_token

    viewer_headers = {"Authorization": "Bearer " + viewer_token(secret)}

    def panel_state(headers=viewer_headers):
        return http.get(endpoint + "/panel/state", headers=headers, verify=str(ca_path), timeout=5)

    health = http.get(endpoint + "/health/ready", verify=str(ca_path), timeout=5).json()
    if health.get("architecture") != "aarch64" or health.get("execution_mode") != "SIMULATED":
        raise ValueError("This check requires the actual ARM64 simulator")
    initial = post("/state", {})
    if initial.get("command_count") != 0 or initial.get("fault") != "normal":
        raise ValueError("Use a fresh simulator volume; refusing to disturb an active demo")
    for path in ("/panel", "/static/panel.css", "/static/panel.js"):
        response = http.get(endpoint + path, verify=str(ca_path), timeout=5)
        assert response.status_code == 200 and response.content
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert panel_state({}).status_code == 401
    assert panel_state().json()["commands"] == []
    assert send("/commands", b"{}", viewer_headers).status_code == 401
    checks["panel_is_read_only_and_viewer_credentials_cannot_control_lock"] = True
    try:
        packet = command("UNLOCKED")
        body, headers = sign(secret, "/commands", packet)
        assert send("/commands", body, {}).status_code == 401
        assert send("/commands", body + b" ", headers).status_code == 401
        checks["unsigned_and_modified_requests_rejected"] = True
        first = send("/commands", body, headers)
        assert first.status_code == 200 and first.json()["reported_status"] == "UNLOCKED"
        assert send("/commands", body, headers).status_code == 409
        assert post("/commands", packet) == first.json()
        assert post("/state", {})["command_count"] == 1
        snapshot = panel_state().json()
        assert snapshot["reported_status"] == "UNLOCKED"
        assert snapshot["commands"][0]["id"] == packet["id"]
        assert snapshot["commands"][0]["status"] == "executed"
        assert snapshot["commands"][0]["executed_at"] is not None
        checks["panel_reflects_actual_execution_once"] = True
        checks["request_replay_rejected_and_command_retry_idempotent"] = True
        post("/commands", {**packet, "target_status": "LOCKED"}, 400)
        post("/commands", {**command("LOCKED"), "expires_at": time.time() - 1}, 400)
        checks["changed_identity_and_expired_commands_rejected"] = True
        post("/fault", {"fault": "jammed"})
        jammed = post("/commands", command("LOCKED"))
        assert (jammed["status"], jammed["reported_status"]) == ("failed", "UNLOCKED")
        checks["jammed_bolt_does_not_report_success"] = True
        post("/fault", {"fault": "feedback_lost"})
        missing = post("/commands", command("LOCKED"))
        assert (missing["status"], missing["reported_status"]) == ("failed", "UNKNOWN")
        assert panel_state().json()["reported_status"] == "UNKNOWN"
        assert panel_state().json()["commands"][0]["reported_status"] == "UNKNOWN"
        checks["missing_feedback_is_unknown"] = True
    finally:
        post("/fault", {"fault": "normal"})
        post("/commands", command("LOCKED"))
    final = post("/state", {})
    assert final["reported_status"] == "LOCKED" and final["execution_mode"] == "SIMULATED"
    return {
        "passed": True,
        "architecture": health["architecture"],
        "checks": checks,
        "final_state": final,
        "scope": "ARM simulator HTTPS interface; no user MFA or camera capture",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://localhost:19443")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify(args.url, ROOT / "instance/lock-sim/simulator_key", ROOT / "deploy/tls/ca.crt")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
