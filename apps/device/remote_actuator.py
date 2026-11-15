"""Explicit adapter to an authenticated, simulated lock. No physical claims."""

from pathlib import Path
from urllib.parse import urlsplit

import requests
from smartlock_protocol.command_auth import sign


class RemoteSimulatedActuator:
    configured = True
    execution_mode = "SIMULATED"

    def __init__(self, endpoint, secret_file, ca_bundle, session=None):
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError("Simulated actuator requires an explicit HTTPS origin")
        self.endpoint = endpoint.rstrip("/")
        self.secret = Path(secret_file).read_text().strip()
        if len(self.secret.encode()) < 32:
            raise ValueError("Simulated actuator secret is too short")
        if not ca_bundle or not Path(ca_bundle).is_file():
            raise ValueError("A trusted CA file is required")
        self.ca_bundle = str(ca_bundle)
        self.http = session or requests.Session()
        self.http.trust_env = False

    def _post(self, path, payload):
        body, headers = sign(self.secret, path, payload)
        response = self.http.post(
            self.endpoint + path,
            data=body,
            headers=headers,
            verify=self.ca_bundle,
            timeout=(2, 3),
            allow_redirects=False,
        )
        if response.status_code != 200 or len(response.content) > 4096:
            raise RuntimeError("Simulated actuator did not return a bounded success response")
        value = response.json()
        if not isinstance(value, dict) or value.get("execution_mode") != "SIMULATED":
            raise ValueError("Invalid simulated actuator response")
        return value

    def execute_command(self, command):
        value = self._post("/commands", command)
        if value.get("id") != command["id"] or value.get("status") not in ("executed", "failed"):
            raise ValueError("Simulated command receipt mismatch")

    def set_state(self, target):
        raise ValueError("Simulated actuation requires a bounded command identity")

    def read_state(self):
        state = self._post("/state", {}).get("reported_status")
        if state not in ("LOCKED", "UNLOCKED", "UNKNOWN"):
            raise ValueError("Invalid simulated feedback")
        return state


def configured_actuator(environ):
    from command_executor import UnavailableActuator

    mode = environ.get("SMART_LOCK_ACTUATOR", "unavailable")
    if mode == "unavailable":
        return UnavailableActuator()
    if mode != "remote-simulator" or environ.get("SMART_LOCK_ALLOW_SIMULATED_ACTUATOR") != "true":
        raise ValueError("Unknown actuator or simulation was not explicitly enabled")
    return RemoteSimulatedActuator(
        environ["SMART_LOCK_SIMULATOR_URL"],
        environ["SMART_LOCK_SIMULATOR_SECRET_FILE"],
        environ["SMART_LOCK_CA_BUNDLE"],
    )
