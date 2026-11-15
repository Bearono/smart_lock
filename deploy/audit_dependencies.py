"""Query OSV for public pinned runtime package versions; never inspect secrets or data."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import requests

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "apps/api/requirements.lock",
    "apps/device/requirements.pi.txt",
    "deploy/device.Dockerfile",
)


def audit(output):
    packages = {}
    for name in SOURCES:
        for package, version in re.findall(
            r"([A-Za-z0-9_-]+)==([A-Za-z0-9.+]+)", (ROOT / name).read_text(encoding="utf-8")
        ):
            packages.setdefault((package, version), []).append(name)
    pairs = sorted(packages)
    response = requests.post(
        "https://api.osv.dev/v1/querybatch",
        timeout=45,
        json={
            "queries": [
                {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
                for name, version in pairs
            ]
        },
    )
    response.raise_for_status()
    rows = response.json()["results"]
    if len(rows) != len(pairs):
        raise ValueError("Incomplete vulnerability database response")
    results = [
        {
            "package": name,
            "version": version,
            "sources": packages[(name, version)],
            "advisories": sorted({item["id"] for item in row.get("vulns", [])}),
        }
        for (name, version), row in zip(pairs, rows)
    ]
    report = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Pinned backend and device Python packages; excludes OS packages, native camera stack and unpinned transitive dependencies",
        "provider": "https://osv.dev",
        "results": results,
        "passed": not any(item["advisories"] for item in results),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "packages": len(results),
                "passed": report["passed"],
                "findings": [item for item in results if item["advisories"]],
            }
        )
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(audit(parser.parse_args().output.resolve()))
