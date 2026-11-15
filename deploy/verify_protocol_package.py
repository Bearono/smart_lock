"""Build the shared wheel in isolation and verify its exact importable contents."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def verify(output):
    source = ROOT / "packages/smartlock_protocol"
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="smartlock-wheel-") as directory:
        isolated = Path(directory)
        for name in ("pyproject.toml", "README.md"):
            shutil.copy2(source / name, isolated / name)
        shutil.copytree(
            source / "smartlock_protocol",
            isolated / "smartlock_protocol",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                str(isolated),
                "-w",
                str(isolated / "dist"),
            ],
            check=True,
        )
        (wheel,) = (isolated / "dist").glob("*.whl")
        expected = {
            path.relative_to(source).as_posix()
            for path in (source / "smartlock_protocol").rglob("*.py")
            if "__pycache__" not in path.parts
        }
        with ZipFile(wheel) as bundle:
            members = set(bundle.namelist())
            implementation = {name for name in members if ".dist-info/" not in name}
            if implementation != expected:
                raise ValueError(
                    "Wheel contains missing or unexpected modules: "
                    + str(implementation ^ expected)
                )
        # A new interpreter imports from the wheel, not the source checkout.
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                "import sys; sys.path.insert(0,sys.argv[1]); import smartlock_protocol.v3 as v; "
                "assert v.__file__.startswith(sys.argv[1]); "
                "from smartlock_protocol.command_auth import sign,verify; "
                "body,headers=sign('isolated-test-key','/state',{},now=100); "
                "verify('isolated-test-key','POST','/state',body,headers,now=100)",
                str(wheel),
            ],
            check=True,
        )
        target = output / wheel.name
        shutil.copy2(wheel, target)
        record = {
            "passed": True,
            "wheel": target.name,
            "modules": sorted(expected),
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
        (output / "verification.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(json.dumps(record))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "releases/protocol")
    verify(parser.parse_args().output)
