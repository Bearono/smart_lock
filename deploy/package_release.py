"""Build an allowlisted source delivery bundle without databases or credentials."""

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    "workspace.toml",
    "manage.py",
    "requirements-dev.txt",
    "pyproject.toml",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "compose.yaml",
    "compose.device.yaml",
    "compose.tls.yaml",
    ".dockerignore",
    "apps/api/config.py",
    "apps/api/run.py",
    "apps/api/requirements.txt",
    "apps/api/requirements.lock",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "apps/web/index.html",
    "apps/web/vite.config.mjs",
    "apps/web/eslint.config.mjs",
    "apps/web/README.md",
    "apps/web/tsconfig.json",
    "apps/web/.prettierrc.json",
    "apps/web/.prettierignore",
    "apps/web/.gitignore",
    "compose.device.tls.yaml",
    "apps/device/requirements.pi.txt",
    "packages/smartlock_protocol/pyproject.toml",
    "apps/android/.gitignore",
    "apps/android/settings.gradle",
    "apps/android/build.gradle",
    "apps/android/gradle.properties",
    "apps/android/app/build.gradle",
    "apps/android/build_sdk.py",
    "apps/android/test_jvm.py",
    "apps/android/README.md",
    "compose.lock-sim.yaml",
    "apps/lock_sim/requirements.txt",
    "apps/api/README.md",
    "apps/device/README.md",
    "apps/device/requirements.txt",
    "apps/lock_sim/README.md",
    "packages/smartlock_protocol/README.md",
)
TREES = {
    "apps/api/app": {".py"},
    "apps/api/tests": {".py", ".md", ".sh", ".ps1", ".json"},
    "apps/web/src": {".js", ".ts", ".vue", ".css", ".webp"},
    "apps/web/public": {".ico", ".svg", ".webp"},
    "packages/smartlock_protocol/smartlock_protocol": {".py"},
    "apps/device/tests": {".py"},
    "apps/lock_sim": {".py"},
    "apps/web/tests": {".cjs"},
    "docs": {".md", ".mmd"},
    ".github": {".yml", ".yaml", ".md"},
    "apps/android/app/src": {".java", ".xml"},
    "deploy/device_console": {".html", ".css", ".js"},
}


def collect_files():
    files = {ROOT / name for name in FILES}
    for directory, extensions in TREES.items():
        files.update(
            path
            for path in (ROOT / directory).rglob("*")
            if path.is_file()
            and path.suffix in extensions
            and not {"build", "__pycache__", "results"}
            & set(path.relative_to(ROOT / directory).parts)
        )
    for directory in ("apps/device", "apps/device/cv/code"):
        files.update((ROOT / directory).glob("*.py"))
    files.update(
        path
        for path in (ROOT / "deploy").iterdir()
        if path.is_file() and path.suffix in {".py", ".md", ".conf", ".Dockerfile"}
    )
    for path in files:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"Invalid release source: {path}")
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    return sorted(files)


def source_hashes():
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in collect_files()
    }


def package(archive, evidence=None):
    files = collect_files()
    evidence = Path(evidence).resolve() if evidence is not None else ROOT / "releases/verification"
    report = json.loads((evidence / "verification.json").read_text(encoding="utf-8"))
    if report.get("passed") is not True or report.get("source_hashes") != source_hashes():
        raise ValueError("Run deploy/verify.py after the last source change before packaging")
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": "software-source-release",
        "excluded": [
            "secrets",
            "databases",
            "personal face templates",
            "CV models",
            "dependencies",
            "build outputs",
        ],
        "files": {},
    }
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            name = path.relative_to(ROOT).as_posix()
            content = path.read_bytes()
            manifest["files"][name] = hashlib.sha256(content).hexdigest()
            if manifest["files"][name] != report["source_hashes"].get(name):
                raise ValueError(f"Source changed during packaging: {name}")
            bundle.writestr(name, content)
        for path in sorted(evidence.iterdir()):
            if path.is_file() and path.suffix in {".log", ".json"}:
                content = path.read_bytes()
                name = "verification/" + path.name
                manifest["files"][name] = hashlib.sha256(content).hexdigest()
                bundle.writestr(name, content)
        bundle.writestr("RELEASE_MANIFEST.json", json.dumps(manifest, indent=2))
    # Read back every file and compare bytes to the manifest before delivery.
    with zipfile.ZipFile(archive) as bundle:
        for name, digest in manifest["files"].items():
            if hashlib.sha256(bundle.read(name)).hexdigest() != digest:
                raise ValueError(f"Release checksum mismatch: {name}")
    with archive.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        f"{digest}  {archive.name}\n", encoding="ascii"
    )
    print(f"{archive}: {len(files)} files, SHA-256 {digest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--verification",
        type=Path,
        default=ROOT / "releases/verification",
        help="Evidence directory from the matching verify.py run",
    )
    args = parser.parse_args()
    package(args.archive.resolve(), args.verification)
