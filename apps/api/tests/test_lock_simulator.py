"""Authentication, persistent state and fault behavior of the separate lock service."""

from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from smartlock_protocol.command_auth import sign

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/lock_sim"))
spec = importlib.util.spec_from_file_location("lock_sim_service", ROOT / "apps/lock_sim/service.py")
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class LockSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "lock.db"
        self.secret, self.now = "simulator-independent-test-key-1234567890", 1000
        self.app = service.create_app(
            self.secret, self.path, allow_faults=True, clock=lambda: self.now
        )
        self.client = self.app.test_client()

    def post(self, path, payload):
        body, headers = sign(self.secret, path, payload, now=self.now)
        return self.client.post(path, data=body, headers=headers)

    def command(self, identity="a", target="UNLOCKED"):
        return dict(id=identity * 32, target_status=target, expires_at=self.now + 30)

    def display(self, client=None):
        return (client or self.client).get(
            "/panel/state", headers={"Authorization": f"Bearer {service.viewer_token(self.secret)}"}
        )

    def test_display_credentials_are_read_only_and_responses_are_private(self):
        token = service.viewer_token(self.secret)
        self.assertEqual(len(token), 64)
        self.assertNotEqual(token, self.secret)
        self.assertNotEqual(token, service.viewer_token(self.secret + "rotated"))
        for authorization in ("", "Bearer invalid", f"Bearer {self.secret}"):
            response = self.client.get("/panel/state", headers={"Authorization": authorization})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
        response = self.display()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["reported_status"], "LOCKED")
        self.assertEqual(response.json["execution_mode"], "SIMULATED")
        self.assertEqual(response.json["commands"], [])
        self.assertEqual(response.json["observed_at"], self.now)
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        for path, payload in (
            ("/commands", self.command()),
            ("/fault", {"fault": "jammed"}),
            ("/state", {}),
        ):
            self.assertEqual(
                self.client.post(
                    path, json=payload, headers={"Authorization": f"Bearer {token}"}
                ).status_code,
                401,
            )
            body, headers = sign(token, path, payload, now=self.now)
            self.assertEqual(self.client.post(path, data=body, headers=headers).status_code, 401)
        self.assertEqual(self.post("/state", {}).json["command_count"], 0)

    def test_display_document_and_assets_are_public_without_exposing_state(self):
        assets = Path(self.directory.name) / "static"
        assets.mkdir()
        (assets / "panel.html").write_text("<!doctype html><title>Lock display</title>")
        (assets / "panel.css").write_text("body { color: black; }")
        self.app.static_folder = assets
        for path in ("/panel", "/static/panel.css"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(self.secret, response.get_data(as_text=True))
            self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
            response.close()
        self.assertEqual(self.client.get("/panel/state").status_code, 401)
        self.assertEqual(self.client.get("/static/../lock.db").status_code, 404)

    def test_display_history_is_bounded_ordered_and_unchanged_by_replay_or_restart(self):
        for index in range(10):
            self.now = 1000 + index
            command = self.command(str(index), "UNLOCKED" if index % 2 else "LOCKED")
            self.assertEqual(self.post("/commands", command).status_code, 200)
        before = self.display().json
        self.assertEqual(before["command_count"], 10)
        self.assertEqual(len(before["commands"]), 8)
        self.assertEqual(
            [item["id"] for item in before["commands"]], [str(i) * 32 for i in range(9, 1, -1)]
        )
        self.assertEqual(
            [item["executed_at"] for item in before["commands"]], list(range(1009, 1001, -1))
        )
        self.assertEqual(before["commands"][0]["target_status"], "UNLOCKED")
        self.assertEqual(before["commands"][0]["reported_status"], "UNLOCKED")
        self.assertEqual(before["commands"][0]["status"], "executed")
        self.now += 1
        self.assertEqual(self.post("/commands", command).status_code, 200)
        restarted = service.create_app(self.secret, self.path, clock=lambda: self.now).test_client()
        after = self.display(restarted).json
        self.assertEqual(before["commands"], after["commands"])
        self.assertEqual(after["command_count"], 10)
        self.assertEqual(after["observed_at"], self.now)
        self.assertEqual(
            set(self.post("/state", {}).json),
            {"reported_status", "execution_mode", "fault", "command_count"},
        )

    def test_display_distinguishes_jammed_and_missing_feedback_from_success(self):
        self.post("/fault", {"fault": "jammed"})
        self.post("/commands", self.command())
        jammed = self.display().json
        self.assertEqual((jammed["reported_status"], jammed["fault"]), ("LOCKED", "jammed"))
        self.assertEqual(jammed["commands"][0]["status"], "failed")
        self.post("/fault", {"fault": "feedback_lost"})
        self.post("/commands", self.command("b"))
        lost = self.display().json
        self.assertEqual(lost["reported_status"], "UNKNOWN")
        self.assertEqual(lost["commands"][0]["reported_status"], "UNKNOWN")
        self.assertEqual(lost["commands"][0]["status"], "failed")
        self.post("/fault", {"fault": "normal"})
        restored = self.display().json
        self.assertEqual(restored["reported_status"], "UNLOCKED")
        self.assertEqual(restored["commands"], lost["commands"])

    def test_display_preserves_execution_order_when_system_clock_moves_backwards(self):
        for identity, timestamp in (("a", 1000), ("b", 1001), ("c", 990)):
            self.now = timestamp
            self.assertEqual(self.post("/commands", self.command(identity)).status_code, 200)
        commands = self.display().json["commands"]
        self.assertEqual([item["id"] for item in commands], [identity * 32 for identity in "cba"])
        self.assertEqual([item["executed_at"] for item in commands], [990, 1001, 1000])

    def test_legacy_database_migration_keeps_state_and_does_not_invent_timestamps(self):
        legacy = Path(self.directory.name) / "legacy.db"
        with closing(sqlite3.connect(legacy)) as db, db:
            db.execute(
                "CREATE TABLE commands (id TEXT PRIMARY KEY,target TEXT,expires REAL,observed TEXT)"
            )
            db.execute(
                "INSERT INTO commands VALUES (?,?,?,?)", ("a" * 32, "UNLOCKED", 1030, "UNLOCKED")
            )
            db.execute("CREATE TABLE bolt (id INTEGER PRIMARY KEY,state TEXT,fault TEXT)")
            db.execute("INSERT INTO bolt VALUES (1,'UNLOCKED','normal')")
        migrated = service.create_app(self.secret, legacy, clock=lambda: self.now).test_client()
        snapshot = self.display(migrated).json
        self.assertEqual(snapshot["reported_status"], "UNLOCKED")
        self.assertEqual(snapshot["command_count"], 1)
        self.assertIsNone(snapshot["commands"][0]["executed_at"])
        body, headers = sign(self.secret, "/commands", self.command(), now=self.now)
        self.assertEqual(migrated.post("/commands", data=body, headers=headers).status_code, 200)
        self.assertIsNone(self.display(migrated).json["commands"][0]["executed_at"])
        self.now += 1
        body, headers = sign(self.secret, "/commands", self.command("b", "LOCKED"), now=self.now)
        self.assertEqual(migrated.post("/commands", data=body, headers=headers).status_code, 200)
        restarted = service.create_app(self.secret, legacy, clock=lambda: self.now).test_client()
        snapshot = self.display(restarted).json
        self.assertEqual(snapshot["reported_status"], "LOCKED")
        self.assertEqual(snapshot["commands"][0]["executed_at"], self.now)
        self.assertIsNone(snapshot["commands"][1]["executed_at"])

    def test_health_is_explicitly_simulated_and_control_requires_authentication(self):
        self.assertEqual(self.client.get("/health/ready").json["execution_mode"], "SIMULATED")
        self.assertEqual(self.client.post("/commands", json=self.command()).status_code, 401)
        body, headers = sign(self.secret, "/commands", self.command(), now=self.now)
        self.assertEqual(self.client.post("/state", data=body, headers=headers).status_code, 401)
        self.assertEqual(
            self.client.post("/commands", data=body + b" ", headers=headers).status_code, 401
        )
        self.assertEqual(self.client.post("/commands", data=body, headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/commands", data=body, headers=headers).status_code, 409)

    def test_duplicate_commands_survive_restart_without_reexecution(self):
        command = self.command()
        first = self.post("/commands", command)
        self.assertEqual(first.json["reported_status"], "UNLOCKED")
        self.assertEqual(first.json["execution_mode"], "SIMULATED")
        self.post("/commands", self.command("b", "LOCKED"))
        restarted = service.create_app(self.secret, self.path, clock=lambda: self.now).test_client()
        body, headers = sign(self.secret, "/commands", command, now=self.now)
        self.assertEqual(restarted.post("/commands", data=body, headers=headers).json, first.json)
        self.assertEqual(self.post("/state", {}).json["reported_status"], "LOCKED")
        self.assertEqual(self.post("/state", {}).json["command_count"], 2)
        command["target_status"] = "LOCKED"
        self.assertEqual(self.post("/commands", command).status_code, 400)

    def test_expired_oversized_and_malformed_commands_cannot_change_state(self):
        for change in (
            {"expires_at": 999},
            {"expires_at": 1061},
            {"expires_at": True},
            {"id": "../escape"},
            {"target_status": "OPEN"},
        ):
            self.assertEqual(self.post("/commands", {**self.command(), **change}).status_code, 400)
        body, headers = sign(self.secret, "/commands", self.command(), now=900)
        self.assertEqual(self.client.post("/commands", data=body, headers=headers).status_code, 401)
        self.assertEqual(self.post("/commands", {"padding": "x" * 5000}).status_code, 413)
        self.assertEqual(self.post("/state", {}).json["command_count"], 0)

    def test_fault_injection_reports_mismatch_or_unknown_and_is_explicitly_enabled(self):
        self.assertEqual(self.post("/fault", {"fault": "jammed"}).status_code, 200)
        result = self.post("/commands", self.command()).json
        self.assertEqual((result["status"], result["reported_status"]), ("failed", "LOCKED"))
        self.post("/fault", {"fault": "feedback_lost"})
        result = self.post("/commands", self.command("b")).json
        self.assertEqual((result["status"], result["reported_status"]), ("failed", "UNKNOWN"))
        self.post("/fault", {"fault": "normal"})
        self.assertEqual(self.post("/state", {}).json["reported_status"], "UNLOCKED")
        restricted = service.create_app(
            self.secret, self.path, clock=lambda: self.now
        ).test_client()
        body, headers = sign(self.secret, "/fault", {"fault": "jammed"}, now=self.now)
        self.assertEqual(restricted.post("/fault", data=body, headers=headers).status_code, 403)

    def test_device_adapter_carries_original_identity_and_persists_simulation_receipt(self):
        sys.path.insert(0, str(ROOT / "apps/device"))
        from remote_actuator import RemoteSimulatedActuator
        from command_executor import CommandExecutor, UnavailableActuator

        app = service.create_app(self.secret, self.path)
        client, test = app.test_client(), self
        key, ca = (Path(self.directory.name) / name for name in ("secret", "ca.crt"))
        key.write_text(self.secret)
        ca.write_text("test transport does not open a TLS connection")

        class HTTPFixture:
            def post(self, url, *, data, headers, verify, timeout, allow_redirects):
                test.assertEqual(verify, str(ca))
                test.assertEqual(timeout, (2, 3))
                test.assertIs(allow_redirects, False)
                response = client.post(
                    url.removeprefix("https://lock.test"), data=data, headers=headers
                )
                return SimpleNamespace(
                    status_code=response.status_code, content=response.data, json=response.get_json
                )

        actuator = RemoteSimulatedActuator("https://lock.test", key, ca, session=HTTPFixture())
        transport = Mock()
        transport.sync_lock.return_value = {
            "command": {**self.command(), "expires_at": time.time() + 30}
        }
        transport.acknowledge_command.side_effect = [TimeoutError(), None]
        journal = Path(self.directory.name) / "executions.db"
        CommandExecutor(transport, actuator, journal).run_once()
        self.assertEqual(actuator.read_state(), "UNLOCKED")
        transport.sync_lock.return_value = {"command": None}
        CommandExecutor(transport, UnavailableActuator(), journal).run_once()
        transport.acknowledge_command.assert_called_with(
            "a" * 32, "executed", "UNLOCKED", failure_reason=None, execution_mode="SIMULATED"
        )
        with self.assertRaises(ValueError):
            actuator.set_state("LOCKED")
        with self.assertRaises(ValueError):
            RemoteSimulatedActuator("http://lock.test", key, ca)

    def test_command_expiring_while_waiting_for_state_lock_is_not_executed(self):
        store = service.StateStore(self.path)
        ticks = iter((1000, 1031))
        store.clock = lambda: next(ticks)
        with self.assertRaisesRegex(ValueError, "expired while waiting"):
            store.execute(self.command())
        self.assertEqual(store.read()["reported_status"], "LOCKED")


if __name__ == "__main__":
    unittest.main()
