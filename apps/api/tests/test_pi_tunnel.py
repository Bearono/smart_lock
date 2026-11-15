"""Validate network selection without starting SSH or touching host credentials."""

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "pi_tunnel_test", Path(__file__).resolve().parents[3] / "deploy/pi_tunnel.py"
)
tunnel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tunnel)


class PiTunnelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.identity = Path(self.tmp.name) / "key with spaces"
        self.identity.touch()
        self.args = [
            "pi_tunnel.py",
            "--host",
            "192.0.2.2",
            "--user",
            "operator",
            "--identity",
            str(self.identity),
        ]

    def test_selected_interface_preserves_host_verification_and_loopback_forwarding(self):
        with (
            patch("sys.argv", self.args + ["--bind-address", "192.0.2.1"]),
            patch.object(tunnel.subprocess, "call", return_value=0) as call,
        ):
            with self.assertRaises(SystemExit) as done:
                tunnel.main()
        self.assertEqual(done.exception.code, 0)
        args = call.call_args.args[0]
        self.assertEqual(args[args.index("-b") + 1], "192.0.2.1")
        self.assertEqual(args[args.index("-i") + 1], str(self.identity))
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertIn("ConnectTimeout=10", args)
        self.assertIn("127.0.0.1:15443:127.0.0.1:5443", args)
        self.assertIn("127.0.0.1:18443:127.0.0.1:8443", args)
        self.assertEqual(args[-1], "operator@192.0.2.2")

    def test_invalid_bind_addresses_never_launch_ssh(self):
        for address in ("-Fconfig", "localhost", "0.0.0.0", "224.0.0.1", "192.0.2.1;command"):
            with (
                self.subTest(address=address),
                patch("sys.argv", self.args + ["--bind-address=" + address]),
                patch.object(tunnel.subprocess, "call") as call,
                patch("sys.stderr"),
            ):
                with self.assertRaises(SystemExit) as error:
                    tunnel.main()
                self.assertEqual(error.exception.code, 2)
                call.assert_not_called()

    def test_simulator_forwarding_requires_explicit_option_and_stays_on_loopback(self):
        for option in ([], ["--lock-simulator"]):
            with (
                patch("sys.argv", self.args + option),
                patch.object(tunnel.subprocess, "call", return_value=0) as call,
            ):
                with self.assertRaises(SystemExit):
                    tunnel.main()
            self.assertEqual(
                "127.0.0.1:19443:127.0.0.1:19443" in call.call_args.args[0], bool(option)
            )
