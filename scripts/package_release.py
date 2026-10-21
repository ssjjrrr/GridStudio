"""Archive a built portable folder and the shareable source; write checksums.

Run after build.ps1 and verification. This script does not contact GitHub.
"""

import argparse
import hashlib
from pathlib import Path
import sys
import zipfile


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from gridstudio import __version__


def archive(files, root, target, prefix):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(files):
            if path.is_file() and not path.is_symlink():
                output.write(path, str(Path(prefix) / path.relative_to(root)))
    with zipfile.ZipFile(target) as check:
        if check.testzip() is not None:
            raise RuntimeError(f"Archive checksum verification failed: {target.name}")
    print(f"{target.name}: {target.stat().st_size / 1024 ** 2:.1f} MiB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=PROJECT / "dist" / "GridStudio")
    parser.add_argument("--output", type=Path, default=PROJECT / "dist")
    args = parser.parse_args()
    bundle, destination = args.bundle.resolve(), args.output.resolve()
    for required in ("GridStudio.exe", "_internal", "LICENSE", "THIRD_PARTY_NOTICES.txt", "licenses/SOURCES.json"):
        if not (bundle / required).exists():
            parser.error(f"Incomplete portable directory; missing {required}")
    if destination == bundle or destination.is_relative_to(bundle):
        parser.error("Place release archives outside the portable directory")
    destination.mkdir(parents=True, exist_ok=True)
    portable = destination / f"GridStudio-{__version__}-Windows-x64.zip"
    source = destination / f"GridStudio-{__version__}-source.zip"
    archive(bundle.rglob("*"), bundle, portable, "GridStudio")

    # Include project-owned content, never a developer's virtual environment,
    # Git metadata, credentials, build products, or arbitrary workspace files.
    roots = (".github", "assets", "benchmarks", "demo", "docs", "gridstudio", "licenses", "scripts", "tests")
    excluded = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    files = [PROJECT / name for name in (
        ".gitignore", ".gitattributes", "README.md", "README.txt", "CHANGELOG.md",
        "LICENSE", "THIRD_PARTY_NOTICES.txt", "requirements.txt", "requirements-dev.txt",
        "GridStudio.spec", "build.ps1", "run.py")]
    for name in roots:
        files.extend(path for path in (PROJECT / name).rglob("*")
                     if not excluded.intersection(path.relative_to(PROJECT).parts)
                     and path.suffix not in (".pyc", ".prof"))
    archive(files, PROJECT, source, "GridStudio-source")
    checksums = []
    for path in (portable, source):
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        checksums.append(f"{digest}  {path.name}\n")
    manifest = destination / f"GridStudio-{__version__}-SHA256SUMS.txt"
    manifest.write_text("".join(checksums), encoding="ascii")
    print(manifest.name)


if __name__ == "__main__":
    main()
