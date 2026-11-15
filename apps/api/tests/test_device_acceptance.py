"""Offline fixtures for host evidence; never access a real device or credentials."""

import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "device_acceptance", ROOT / "deploy/device_acceptance.py"
)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class DeviceAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.proc = self.root / "proc"
        self.sys = self.root / "sys"
        self.proc.mkdir()
        (self.proc / "123").mkdir()

    def fixture(self):
        (self.proc / "stat").write_text("cpu 100 0 50 800 20 5 5 20 10 0\n", encoding="utf-8")
        (self.proc / "meminfo").write_text(
            "MemTotal: 2048 kB\nMemAvailable: 1024 kB\nSwapTotal: 512 kB\nSwapFree: 256 kB\n",
            encoding="utf-8",
        )
        (self.proc / "123/status").write_text(
            "Name:\ttest\nVmRSS: 128 kB\nVmSize: 1024 kB\n", encoding="utf-8"
        )
        thermal = self.sys / "class/thermal/thermal_zone0"
        thermal.mkdir(parents=True)
        (thermal / "temp").write_text("42300\n", encoding="utf-8")

    def args(self, **changes):
        values = dict(
            seconds=1.0,
            interval=0.5,
            device_id="test_pi",
            pid=123,
            health_url=None,
            http_timeout=1.0,
            ca_file=None,
            output=self.root / "report.json",
        )
        values.update(changes)
        return argparse.Namespace(**values)

    def test_resource_values_and_cpu_delta_exclude_guest_double_count(self):
        self.fixture()
        metrics, previous = evidence.read_metrics(self.proc, self.sys, 123)
        self.assertEqual(previous, {"total_ticks": 1000, "idle_ticks": 820})
        self.assertIsNone(metrics["cpu"]["utilization_percent"])
        self.assertEqual(metrics["memory"]["used_bytes"], 1024 * 1024)
        self.assertEqual(metrics["process"]["rss_bytes"], 128 * 1024)
        self.assertEqual(metrics["temperature"]["sensors"][0]["celsius"], 42.3)
        (self.proc / "stat").write_text("cpu 150 0 50 850 20 5 5 20 10 0\n", encoding="utf-8")
        metrics, _ = evidence.read_metrics(self.proc, self.sys, 123, previous)
        self.assertEqual(metrics["cpu"]["utilization_percent"], 50.0)

    def test_missing_and_corrupt_metrics_are_explicitly_unavailable(self):
        metrics, _ = evidence.read_metrics(self.proc, self.sys, 123)
        self.assertTrue(all(metric["status"] == "unavailable" for metric in metrics.values()))
        self.fixture()
        (self.proc / "stat").write_text("cpu -1 0 0 0", encoding="utf-8")
        (self.proc / "meminfo").write_text("MemTotal: 1 kB\nMemAvailable: 2 kB", encoding="utf-8")
        (self.sys / "class/thermal/thermal_zone0/temp").write_text("nan", encoding="utf-8")
        metrics, _ = evidence.read_metrics(self.proc, self.sys, 123)
        for key in ("cpu", "memory", "temperature"):
            self.assertEqual(metrics[key]["status"], "unavailable")

    def test_counter_reset_is_not_reported_as_utilization(self):
        self.fixture()
        metrics, _ = evidence.read_metrics(
            self.proc, self.sys, 123, {"total_ticks": 2000, "idle_ticks": 1500}
        )
        self.assertIsNone(metrics["cpu"]["utilization_percent"])
        self.assertEqual(metrics["cpu"]["utilization_status"], "counter_reset_or_no_elapsed_ticks")

    def test_http_is_loopback_only_and_credentials_and_redirects_are_rejected(self):
        for url in (
            "https://device.example/health/ready",
            "http://127.0.0.1:5000/health/ready",
            "http://[::1]/health",
        ):
            self.assertEqual(evidence.validate_health_url(url), url)
        for url in (
            "http://device.example/health",
            "http://localhost/health",
            "https://u:p@host/health",
            "https://host/health?token=secret",
            "https://host/health#secret",
            "file:///etc/passwd",
            "https://host:0/health",
            "https://host/\nhealth",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                evidence.validate_health_url(url)
        self.assertIsNone(
            evidence.NoRedirect().redirect_request(None, None, 302, "", {}, "http://example.com")
        )

    def test_verified_tls_probe_does_not_read_or_record_response_body(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        with (
            patch.object(evidence.ssl, "create_default_context") as context,
            patch.object(evidence, "build_opener") as opener,
        ):
            opener.return_value.open.return_value = Response()
            result = evidence.health_probe("https://device.example/health", 2, Path("ca.crt"))
            context.assert_called_once_with(cafile="ca.crt")
            self.assertEqual(result["status"], "ok")
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 2)

    def test_raw_failed_samples_are_retained_without_hardware_success_claim(self):
        self.fixture()
        current = [0.0]

        def sleep(seconds):
            current[0] += seconds

        statuses = iter(("ok", "failed", "ok"))
        report = evidence.collect(
            self.args(health_url="http://127.0.0.1/health"),
            proc_root=self.proc,
            sys_root=self.sys,
            clock=lambda: current[0],
            sleep=sleep,
            probe=lambda *args: {"status": next(statuses)},
            source=lambda: {"digest_sha256": "fixed"},
        )
        saved = json.loads(self.args().output.read_text(encoding="utf-8"))
        self.assertEqual(report, saved)
        self.assertTrue(saved["completed"])
        self.assertEqual(saved["summary"]["sample_count"], 3)
        self.assertEqual(saved["summary"]["health_failures"], 1)
        self.assertEqual(saved["summary"]["hardware_functionality"], "not_tested")
        self.assertNotIn("passed", saved)
        with self.assertRaises(FileExistsError):
            evidence.collect(self.args())

    def test_interruption_preserves_samples_and_marks_incomplete(self):
        def stop(seconds):
            raise KeyboardInterrupt

        report = evidence.collect(
            self.args(),
            proc_root=self.proc,
            sys_root=self.sys,
            clock=lambda: 0.0,
            sleep=stop,
            probe=lambda *args: {"status": "not_requested"},
            source=lambda: {"digest_sha256": "fixed"},
        )
        self.assertFalse(report["completed"])
        self.assertTrue(report["interrupted"])
        self.assertEqual(report["summary"]["sample_count"], 1)
        self.assertEqual(report["summary"]["unavailable_samples"]["memory"], 1)

    def test_invalid_configuration_creates_no_report(self):
        for changes in (
            {"seconds": float("nan")},
            {"seconds": 7201},
            {"interval": 0},
            {"pid": 0},
            {"device_id": "../escape"},
            {"http_timeout": 31},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                evidence.collect(self.args(**changes))
            self.assertFalse(self.args().output.exists())

    def test_source_manifest_hashes_only_code_and_changes_when_worktree_changes(self):
        code = self.root / "apps/device/app.py"
        code.parent.mkdir(parents=True)
        code.write_text("print(1)\n", encoding="utf-8")
        (code.parent / "device.key").write_text("do not collect", encoding="utf-8")
        (code.parent / "instance").mkdir()
        (code.parent / "instance/private.py").write_text("do not collect", encoding="utf-8")
        with patch.object(evidence.subprocess, "run", side_effect=OSError):
            first = evidence.source_evidence(self.root)
            code.write_text("print(2)\n", encoding="utf-8")
            second = evidence.source_evidence(self.root)
        self.assertEqual(set(first["files_sha256"]), {"apps/device/app.py"})
        self.assertIsNone(first["git_head"])
        self.assertNotEqual(first["digest_sha256"], second["digest_sha256"])


if __name__ == "__main__":
    unittest.main()
