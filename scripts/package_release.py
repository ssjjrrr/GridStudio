"""Archive a native bundle and shareable source; write SHA-256 checksums.

Windows uses ZIP, Linux uses tar.gz, and macOS uses ditto ZIP so .app symlinks
and executable modes survive extraction. This script does not contact GitHub.
"""

import argparse
import hashlib
from pathlib import Path
import stat
import subprocess
import tarfile
import zipfile

from bundle_support import PROJECT, VERSION, default_bundle, executable_path, native_target, resource_directory


def zip_files(files, root, target, prefix):
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(files):
            if path.is_file() and not path.is_symlink():
                info = zipfile.ZipInfo.from_file(path, f"{prefix}/{path.relative_to(root).as_posix()}")
                # Source archives created on Windows must retain runnable Unix
                # build scripts. Runtime Unix bundles use native archive tools.
                info.create_system = 3
                permissions = 0o755 if path.suffix == ".sh" else (path.stat().st_mode & 0o777 or 0o644)
                info.external_attr = (stat.S_IFREG | permissions) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                output.writestr(info, path.read_bytes())
    verify_zip(target)


def verify_zip(target):
    with zipfile.ZipFile(target) as check:
        if check.testzip() is not None:
            raise RuntimeError(f"Archive checksum verification failed: {target.name}")


def archive_bundle(bundle, destination, system, architecture):
    suffix = ".tar.gz" if system == "Linux" else ".zip"
    target = destination / f"GridStudio-{VERSION}-{system}-{architecture}{suffix}"
    if system == "macOS":
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                        str(bundle), str(target)], check=True)
        verify_zip(target)
    elif system == "Linux":
        with tarfile.open(target, "w:gz", dereference=False) as output:
            output.add(bundle, arcname="GridStudio")
        with tarfile.open(target) as check:
            # Read each member completely to detect archive truncation/errors.
            for member in check:
                if member.isfile():
                    with check.extractfile(member) as contents:
                        while contents.read(1024 * 1024):
                            pass
    else:
        zip_files(bundle.rglob("*"), bundle, target, "GridStudio")
    return target


def archive_source(destination):
    roots = (".github", "assets", "benchmarks", "demo", "docs", "gridstudio", "licenses", "scripts", "tests")
    excluded = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    files = [PROJECT / name for name in (
        ".gitignore", ".gitattributes", "README.md", "README.en.md", "README.txt", "README.en.txt",
        "CHANGELOG.md", "CHANGELOG.en.md", "LICENSE", "THIRD_PARTY_NOTICES.txt", "THIRD_PARTY_NOTICES.en.txt",
        "requirements.txt", "requirements-dev.txt", "GridStudio.spec", "build.ps1", "build.sh", "run.py")]
    for name in roots:
        files.extend(path for path in (PROJECT / name).rglob("*")
                     if not excluded.intersection(path.relative_to(PROJECT).parts)
                     and path.suffix not in (".pyc", ".prof"))
    target = destination / f"GridStudio-{VERSION}-source.zip"
    zip_files(files, PROJECT, target, "GridStudio-source")
    return target


def write_checksums(paths, target):
    lines = []
    for path in paths:
        with path.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        lines.append(f"{digest}  {path.name}\n")
    target.write_text("".join(lines), encoding="ascii")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=default_bundle())
    parser.add_argument("--output", type=Path, default=PROJECT / "dist" / "release")
    parser.add_argument("--skip-source", action="store_true", help="Only archive this native runtime")
    args = parser.parse_args()
    system, architecture = native_target()
    bundle, destination = args.bundle.resolve(), args.output.resolve()
    resources = resource_directory(bundle)
    for required in ("LICENSE", "THIRD_PARTY_NOTICES.txt", "THIRD_PARTY_NOTICES.en.txt",
                     "licenses/SOURCES.json", "licenses/runtime-versions.json", "distribution-manifest.json"):
        if not (resources / required).is_file():
            parser.error(f"Incomplete portable directory; missing {required}")
    if not executable_path(bundle).is_file():
        parser.error(f"Missing native executable: {executable_path(bundle)}")
    if destination == bundle or destination.is_relative_to(bundle):
        parser.error("Place release archives outside the portable directory")
    destination.mkdir(parents=True, exist_ok=True)
    paths = [archive_bundle(bundle, destination, system, architecture)]
    if not args.skip_source:
        paths.append(archive_source(destination))
    # Per-target manifests never overwrite one another in the release matrix.
    manifest = destination / f"GridStudio-{VERSION}-{system}-{architecture}-SHA256SUMS.txt"
    write_checksums(paths, manifest)
    for path in (*paths, manifest):
        print(f"{path.name}: {path.stat().st_size / 1024 ** 2:.1f} MiB")


if __name__ == "__main__":
    main()
