"""Check a native distribution, then exercise real decoding in both UI languages.

Pass --archive to extract and verify the exact release archive, including all
symlinks and executable modes. Run on the matching native OS and architecture.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from bundle_support import (
    PROJECT, VERSION, default_bundle, executable_path, native_target, resource_directory,
)


def extract_archive(archive, destination, system):
    if system == "macOS":
        subprocess.run(["ditto", "-x", "-k", str(archive), str(destination)], check=True)
    elif system == "Linux":
        with tarfile.open(archive) as source:
            source.extractall(destination, filter="data")
    else:
        with zipfile.ZipFile(archive) as source:
            source.extractall(destination)
    # macOS TMPDIR often starts with /var, an alias of /private/var. Compare
    # resolved symlink targets against the same canonical extraction root.
    return (destination / ("GridStudio.app" if system == "macOS" else "GridStudio")).resolve()


def verify_native_executable(bundle, system, architecture):
    executable = executable_path(bundle)
    if system == "Windows":
        import pefile
        with pefile.PE(str(executable), fast_load=True) as pe:
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
            assert pe.FILE_HEADER.Machine == 0x8664, "Expected Windows x64 executable"
            for attribute in ("File", "Product"):
                info = pe.VS_FIXEDFILEINFO[0]
                high, low = getattr(info, f"{attribute}VersionMS"), getattr(info, f"{attribute}VersionLS")
                assert (high >> 16, high & 0xffff, low >> 16, low & 0xffff) == (*map(int, VERSION.split(".")), 0)
        for forbidden in ("icuuc.dll", "icudt78.dll"):
            assert not any(bundle.rglob(forbidden)), f"Unexpected shadowed system DLL: {forbidden}"
    elif system == "macOS":
        with (bundle / "Contents" / "Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        assert info["CFBundleShortVersionString"] == VERSION and info["CFBundleVersion"] == VERSION
        assert info["LSMinimumSystemVersion"] == "13.0"
        result = subprocess.run(["lipo", "-archs", str(executable)], capture_output=True, text=True, check=True)
        assert result.stdout.strip() == ("arm64" if architecture == "arm64" else "x86_64"), result.stdout
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
    else:
        header = executable.read_bytes()[:20]
        assert header[:5] == b"\x7fELF\x02" and struct.unpack("<H", header[18:20])[0] == 62, "Expected Linux x86-64 ELF"
    if system != "Windows":
        assert os.access(executable, os.X_OK), f"Not executable after extraction: {executable}"


def verify_files(bundle, system, architecture):
    resources = resource_directory(bundle)
    required = ("README.txt", "README.en.txt", "CHANGELOG.md", "CHANGELOG.en.md", "LICENSE",
                "THIRD_PARTY_NOTICES.txt", "THIRD_PARTY_NOTICES.en.txt", "INTERACTION_PERFORMANCE.txt",
                "INTERACTION_PERFORMANCE.en.txt", "PERFORMANCE.json", "VALIDATION.md",
                "licenses/SOURCES.json", "licenses/runtime-versions.json", "licenses/FFmpeg-BUILD.txt",
                "demo/sample.mp4", "demo/sample-short.mp4", "distribution-manifest.json")
    for relative in required:
        assert (resources / relative).is_file(), f"Missing bundled file: {relative}"
    assert any(bundle.rglob("qtbase_zh_CN.qm")), "Missing Chinese Qt standard-dialog translation"
    patterns = {
        "Windows": ("Qt6Core.dll", "Qt6Multimedia.dll", "avcodec-*.dll", "avformat-*.dll"),
        "Linux": ("libQt6Core.so*", "libQt6Multimedia.so*", "libavcodec.so*", "libavformat.so*"),
        "macOS": ("QtCore", "QtMultimedia", "libavcodec*.dylib", "libavformat*.dylib"),
    }
    for pattern in patterns[system]:
        assert any(path.is_file() for path in bundle.rglob(pattern)), f"Missing runtime: {pattern}"
    manifest = json.loads((resources / "licenses" / "SOURCES.json").read_text(encoding="utf-8"))
    for name, record in manifest.items():
        content = (resources / "licenses" / name).read_bytes()
        assert len(content) == record["bytes"] and hashlib.sha256(content).hexdigest() == record["sha256"], name
    runtime = json.loads((resources / "licenses" / "runtime-versions.json").read_text(encoding="utf-8"))
    assert (runtime["application"], runtime["system"], runtime["architecture"]) == (VERSION, system, architecture)
    assert runtime["python"] == "3.12.14" and runtime["qt"] == "6.10.2"
    assert runtime["ffmpeg"]["version"] == "7.1.2" and "LGPL" in runtime["ffmpeg"]["license"]
    structure = json.loads((resources / "distribution-manifest.json").read_text(encoding="utf-8"))
    for relative, target in structure["symlinks"].items():
        path = bundle / relative
        assert path.is_symlink() and path.readlink().as_posix() == target, f"Symlink was not preserved: {relative}"
        assert path.exists() and path.resolve().is_relative_to(bundle), f"Broken/outside symlink: {relative}"
    if system != "Windows":
        for relative in structure["executable_files"]:
            assert (bundle / relative).stat().st_mode & stat.S_IXUSR, f"Lost execute permission: {relative}"
        assert structure["symlinks"], "Expected PyInstaller POSIX symlinks"
    verify_native_executable(bundle, system, architecture)
    return {"license_hashes_verified": len(manifest), "symlinks_verified": len(structure["symlinks"]),
            "executable_modes_verified": len(structure["executable_files"]), "runtime": runtime}


def verify_smoke(bundle, destination):
    from PySide6.QtGui import QImage
    resources = resource_directory(bundle)
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["QT_MEDIA_BACKEND"] = "ffmpeg"
    native_qpa = {"win32": "windows", "darwin": "cocoa", "linux": "xcb"}[sys.platform]
    environment.setdefault("QT_QPA_PLATFORM", native_qpa)
    # Do not use the developer's persistent language preferences during CI.
    environment["XDG_CONFIG_HOME"] = str(destination / "config")
    cases = (("edit-en", "en", "自由画布与图层.gstudio", ["--edit"], 3),
             ("hover-en", "en", "叠放与悬停进度.gstudio", ["--smoke-hover"], 2),
             ("sync-en", "en", "同步与区间循环.gstudio", [], 2),
             ("edit-zh", "zh_CN", "自由画布与图层.gstudio", ["--edit"], 3))
    reports = []
    for name, language, sample, options, count in cases:
        image = destination / f"portable-{name}.png"
        result = subprocess.run([str(executable_path(bundle)), "--language", language,
                                 "--smoke-test", str(image), *options, str(resources / "demo" / sample)],
                                cwd=bundle, env=environment, timeout=45, capture_output=True,
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        (destination / f"portable-{name}.stdout.log").write_bytes(result.stdout)
        (destination / f"portable-{name}.stderr.log").write_bytes(result.stderr)
        assert result.returncode == 0, f"{name}: exit {result.returncode}: {result.stderr.decode(errors='replace')}"
        report = json.loads(image.with_suffix(".json").read_text(encoding="utf-8"))
        assert report["version"] == VERSION and report["language"] == language, report
        assert report["platform"] == native_qpa, f"Native platform was not exercised: {report}"
        assert report["qt_translation_loaded"] is (language == "zh_CN"), report
        assert report["passed"] and report["capture_saved"], report
        assert len(report["media"]) == count and all(item["frame_valid"] and item["error"] == "NoError"
                                                    and item["duration_ms"] > 0 for item in report["media"]), report
        assert all(Path(item["source"]).name == item["source"] for item in report["media"]), report
        decoded = QImage(str(image))
        assert not decoded.isNull() and decoded.width() >= 600 and decoded.height() >= 400, "Invalid capture"
        reports.append({"case": name, **report})
        print(f"Verified native launch, decoding and {language} UI: {name}", flush=True)
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--bundle", type=Path, default=default_bundle())
    source.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path, default=PROJECT / "artifacts")
    args = parser.parse_args()
    system, architecture = native_target()
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gridstudio-release-") as temporary:
        bundle = extract_archive(args.archive.resolve(), Path(temporary), system) if args.archive else args.bundle.resolve()
        report = verify_files(bundle, system, architecture)
        report.update({"archive": args.archive.name if args.archive else None,
                       "cases": verify_smoke(bundle, destination), "passed": True})
        (destination / "portable-validation.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {system} {architecture}: {destination / 'portable-validation.json'}")


if __name__ == "__main__":
    main()
