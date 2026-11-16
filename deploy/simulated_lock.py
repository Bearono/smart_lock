"""Initialize or inspect the explicit ARM simulator; no unlock authorization bypass."""

import argparse
import json
from pathlib import Path
import secrets
import sys
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("init", "status", "fault", "panel"))
    parser.add_argument("--url", default="https://localhost:19443")
    parser.add_argument("--fault", choices=("normal", "jammed", "feedback_lost"))
    args = parser.parse_args()
    key = ROOT / "instance/lock-sim/simulator_key"
    if args.operation == "init":
        key.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            with key.open("x") as stream:
                stream.write(secrets.token_hex(32))
            # Private host directory, readable by the container's unprivileged UID.
            key.chmod(0o444)
        except FileExistsError:
            if len(key.read_text().strip().encode()) < 32:
                raise ValueError("Existing simulator key is invalid; it was not replaced")
        print("Independent simulator key is ready. Start compose.lock-sim.yaml explicitly.")
        return
    sys.path.insert(0, str(ROOT / "apps/device"))
    from remote_actuator import RemoteSimulatedActuator

    client = RemoteSimulatedActuator(args.url, key, ROOT / "deploy/tls/ca.crt")
    if args.operation == "panel":
        # Verify the service before granting this browser read-only access.
        client._post("/state", {})
        sys.path.insert(0, str(ROOT / "apps/lock_sim"))
        from viewer import viewer_token

        endpoint = client.endpoint + "/panel"
        if not webbrowser.open(endpoint + "#token=" + viewer_token(key.read_text().strip())):
            raise RuntimeError("No browser available; run this command on the viewing computer")
        print("Read-only simulator panel opened at " + endpoint)
        return
    if args.operation == "fault":
        if not args.fault:
            parser.error("--fault is required for fault injection")
        value = client._post("/fault", {"fault": args.fault})
    else:
        value = client._post("/state", {})
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
