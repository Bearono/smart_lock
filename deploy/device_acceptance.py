"""Bounded, read-only host evidence collection; never opens a camera or controls services."""

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import platform
import re
import ssl
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = ("apps/device", "packages/smartlock_protocol/smartlock_protocol")
SOURCE_FILES = (
    "deploy/device_acceptance.py",
    "deploy/pi_native.py",
    "deploy/course_benchmark.py",
    "deploy/protocol_benchmark.py",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def unavailable(reason):
    return {"status": "unavailable", "reason": reason}


def read_small(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        content = handle.read(65537)
    if len(content) > 65536:
        raise ValueError("metric_file_too_large")
    return content


def memory_values(content):
    values = {}
    for line in content.splitlines():
        match = re.fullmatch(r"([A-Za-z_()]+):\s+(\d+)\s+kB", line.strip())
        if match:
            values[match[1]] = int(match[2]) * 1024
    return values


def read_metrics(proc_root, sys_root, pid, previous_cpu=None):
    """Read Linux counters, retaining explicit missing/invalid results on other hosts."""
    proc_root, sys_root = Path(proc_root), Path(sys_root)
    result = {}
    current_cpu = None
    try:
        line = read_small(proc_root / "stat").splitlines()[0].split()
        if line[0] != "cpu" or len(line) < 5:
            raise ValueError("invalid_cpu_counters")
        counters = [int(value) for value in line[1:]]
        if any(value < 0 for value in counters):
            raise ValueError("invalid_cpu_counters")
        # guest/guest_nice are already included in user/nice; never count them twice.
        total = sum(counters[:8])
        idle = counters[3] + (counters[4] if len(counters) > 4 else 0)
        current_cpu = {"total_ticks": total, "idle_ticks": idle}
        cpu = {
            "status": "available",
            **current_cpu,
            "utilization_percent": None,
            "utilization_status": "requires_previous_sample",
        }
        if previous_cpu is not None:
            elapsed = total - previous_cpu["total_ticks"]
            inactive = idle - previous_cpu["idle_ticks"]
            if elapsed > 0 and 0 <= inactive <= elapsed:
                cpu.update(
                    utilization_percent=round(100 * (elapsed - inactive) / elapsed, 3),
                    utilization_status="available",
                )
            else:
                cpu["utilization_status"] = "counter_reset_or_no_elapsed_ticks"
        result["cpu"] = cpu
    except (OSError, ValueError, IndexError, UnicodeError):
        result["cpu"] = unavailable("proc_stat_missing_or_invalid")
    try:
        values = memory_values(read_small(proc_root / "meminfo"))
        total, available = values["MemTotal"], values["MemAvailable"]
        if not 0 <= available <= total or total == 0:
            raise ValueError("invalid_memory_values")
        result["memory"] = {
            "status": "available",
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": total - available,
            "swap_total_bytes": values.get("SwapTotal"),
            "swap_free_bytes": values.get("SwapFree"),
        }
    except (OSError, ValueError, KeyError, UnicodeError):
        result["memory"] = unavailable("proc_meminfo_missing_or_invalid")
    try:
        values = memory_values(read_small(proc_root / str(pid) / "status"))
        result["process"] = {
            "status": "available",
            "pid": pid,
            "rss_bytes": values["VmRSS"],
            "virtual_bytes": values.get("VmSize"),
        }
    except (OSError, ValueError, KeyError, UnicodeError):
        result["process"] = {"pid": pid, **unavailable("process_status_missing_or_invalid")}
    temperatures, failures = [], []
    for zone in sorted((sys_root / "class" / "thermal").glob("thermal_zone*")):
        try:
            value = int(read_small(zone / "temp").strip()) / 1000
            if not -50 <= value <= 200:
                raise ValueError("invalid_temperature")
            temperatures.append({"zone": zone.name, "celsius": value})
        except (OSError, ValueError, UnicodeError):
            failures.append({"zone": zone.name, "reason": "temperature_missing_or_invalid"})
    result["temperature"] = (
        {
            "status": "partial" if failures else "available",
            "sensors": temperatures,
            "failures": failures,
        }
        if temperatures
        else {**unavailable("no_readable_thermal_sensor"), "failures": failures}
    )
    return result, current_cpu


def validate_health_url(url):
    if url is None:
        return None
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid health URL") from exc
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(character.isspace() for character in url)
        or "\\" in url
    ):
        raise ValueError("Health URL must have no credentials, query, fragment or whitespace")
    if port is not None and port == 0:
        raise ValueError("Invalid health URL port")
    if parsed.scheme == "http":
        try:
            loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise ValueError(
                "HTTP is allowed only for a literal loopback IP; use verified HTTPS otherwise"
            )
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        return None


def health_probe(url, timeout, ca_file=None):
    """Status-only GET: verified TLS, no redirects, cookies, proxy credentials or body logging."""
    if url is None:
        return {"status": "not_requested"}
    validate_health_url(url)
    context = ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context), NoRedirect())
    started = time.monotonic()
    try:
        with opener.open(
            Request(url, method="GET", headers={"User-Agent": "SmartLock-Evidence/1"}),
            timeout=timeout,
        ) as response:
            status_code = response.status
        outcome = {"status": "ok" if status_code == 200 else "failed", "http_status": status_code}
    except HTTPError as exc:
        outcome = {"status": "failed", "http_status": exc.code, "reason": "http_status_not_200"}
        exc.close()
    except (URLError, OSError, ValueError):
        outcome = {"status": "failed", "reason": "connection_tls_or_timeout_error"}
    outcome["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
    return outcome


def source_evidence(root=ROOT):
    """Hash an explicit code allowlist, excluding keys, models, photos and runtime state."""
    root = Path(root)
    paths = [root / name for name in SOURCE_FILES]
    for directory in SOURCE_PATHS:
        paths.extend((root / directory).rglob("*.py"))
        paths.extend((root / directory).glob("requirements*.txt"))
    hashes, skipped = {}, []
    for path in sorted(set(paths)):
        name = path.relative_to(root).as_posix()
        if any(
            part in ("venv", "__pycache__", "data", "outputs", "models", "instance", "build")
            or part.startswith(".venv")
            for part in path.relative_to(root).parts
        ):
            continue
        if (
            not path.is_file()
            or path.is_symlink()
            or not path.resolve().is_relative_to(root.resolve())
        ):
            skipped.append(name)
            continue
        try:
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            skipped.append(name)
    try:
        git = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5
        )
        head = (
            git.stdout.strip()
            if git.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", git.stdout.strip())
            else None
        )
    except (OSError, subprocess.SubprocessError):
        head = None
    return {
        "git_head": head,
        "scope": "device code and selected evidence/deployment tools only",
        "files_sha256": hashes,
        "unavailable_files": skipped,
        "digest_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
    }


def save_report(output, report):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix="." + output.name + ".",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(report, handle, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def collect(
    args,
    *,
    proc_root=Path("/proc"),
    sys_root=Path("/sys"),
    clock=time.monotonic,
    sleep=time.sleep,
    probe=health_probe,
    source=source_evidence,
):
    validate_health_url(args.health_url)
    if (
        not all(math.isfinite(value) for value in (args.seconds, args.interval, args.http_timeout))
        or not 1 <= args.seconds <= 7200
        or not 0.1 <= args.interval <= 60
        or not 0.1 <= args.http_timeout <= 30
        or args.pid <= 0
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.device_id)
    ):
        raise ValueError("Invalid duration, interval, timeout, process ID or device ID")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8"):
        pass
    report = {
        "schema_version": 1,
        "started_at": utc_now(),
        "device_id": args.device_id,
        "scope": "read-only host resources and optional HTTP readiness; no camera, biometric or actuation test",
        "environment": {
            "system": platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "process_id": args.pid,
        },
        "configuration": {
            "duration_seconds": args.seconds,
            "interval_seconds": args.interval,
            "http_timeout_seconds": args.http_timeout,
            "health_url": args.health_url,
            "tls_verification": True,
            "redirects": False,
        },
        "source_start": source(),
        "completed": False,
        "samples": [],
    }
    started, previous = clock(), None
    save_report(output, report)
    try:
        while True:
            metrics, previous = read_metrics(proc_root, sys_root, args.pid, previous)
            row = {
                "timestamp": utc_now(),
                "elapsed_seconds": round(clock() - started, 3),
                **metrics,
                "health": probe(args.health_url, args.http_timeout, args.ca_file),
            }
            report["samples"].append(row)
            elapsed = clock() - started
            report["elapsed_seconds"] = round(elapsed, 3)
            save_report(output, report)
            if elapsed >= args.seconds:
                report["completed"] = True
                break
            sleep(min(args.interval, args.seconds - elapsed))
    except KeyboardInterrupt:
        report["interrupted"] = True
    finally:
        report["finished_at"] = utc_now()
        report["source_end"] = source()
        report["source_unchanged"] = (
            report["source_start"]["digest_sha256"] == report["source_end"]["digest_sha256"]
        )
        report["summary"] = {
            "sample_count": len(report["samples"]),
            "health_failures": sum(
                row["health"]["status"] == "failed" for row in report["samples"]
            ),
            "unavailable_samples": {
                name: sum(row[name]["status"] != "available" for row in report["samples"])
                for name in ("cpu", "memory", "process", "temperature")
            },
            "hardware_functionality": "not_tested",
            "biometric_accuracy": "not_tested",
        }
        save_report(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--device-id", required=True)
    parser.add_argument(
        "--pid",
        type=int,
        default=os.getpid(),
        help="Process to observe; defaults to this collector",
    )
    parser.add_argument(
        "--health-url", help="Optional unauthenticated status-only URL; no redirect or proxy use"
    )
    parser.add_argument("--http-timeout", type=float, default=5)
    parser.add_argument("--ca-file", type=Path, help="Optional trusted public CA PEM for HTTPS")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = collect(args)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Evidence collection could not start or save ({type(exc).__name__}).\n")
    print(
        f"Evidence saved: {args.output}; completed={report['completed']}; "
        f"samples={report['summary']['sample_count']}; hardware=not_tested"
    )
    return (
        0
        if report["completed"]
        and report["source_unchanged"]
        and not report["summary"]["health_failures"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
