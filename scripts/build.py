"""Build on the native OS/architecture using an already-installed environment.

Install requirements.txt and PyInstaller 6.20.0 first, or use build.ps1/build.sh.
No cross-compilation: Linux x64, Windows x64 and both Mac CPUs build separately.
"""

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from bundle_support import (
    PROJECT, VERSION, default_bundle, distribution_structure, executable_path,
    native_target, resource_directory,
)


def ffmpeg_details(bundle):
    bundle = bundle.resolve()
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    if sys.platform == "linux":
        # Match the PyInstaller bootloader's dependency search path, before
        # starting a clean process that has not imported Qt/OpenSSL already.
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(filter(None, (
            str(bundle / "_internal"), environment.get("LD_LIBRARY_PATH"))))
    probe = subprocess.run([sys.executable, "-I", str(PROJECT / "scripts" / "probe_ffmpeg.py"),
                            str(bundle)], env=environment, capture_output=True, text=True,
                           encoding="utf-8", timeout=30)
    if probe.returncode:
        raise RuntimeError(f"Cannot query bundled FFmpeg (exit {probe.returncode}):\n{probe.stderr}")
    result = json.loads(probe.stdout)
    # Shipped license/source snapshots must match the actual native library.
    if result["version"] != "7.1.2" or "LGPL" not in result["license"] or "--enable-gpl" in result["configuration"]:
        raise RuntimeError(f"Bundled FFmpeg differs from the reviewed LGPL 7.1.2 source/notice set: {result}")
    return result


def attach_documents(bundle):
    resources = resource_directory(bundle)
    resources.mkdir(parents=True, exist_ok=True)
    documents = ["README.txt", "README.en.txt", "CHANGELOG.md", "CHANGELOG.en.md",
                 "LICENSE", "THIRD_PARTY_NOTICES.txt", "THIRD_PARTY_NOTICES.en.txt"]
    for name in documents:
        shutil.copy2(PROJECT / name, resources / name)
    for name in ("licenses", "demo"):
        shutil.copytree(PROJECT / name, resources / name, dirs_exist_ok=True, symlinks=True)
    for source, destination in (
        ("benchmarks/README.txt", "INTERACTION_PERFORMANCE.txt"),
        ("benchmarks/README.en.txt", "INTERACTION_PERFORMANCE.en.txt"),
        ("benchmarks/performance.json", "PERFORMANCE.json"),
        (f"docs/validation-{VERSION}.md", "VALIDATION.md"),
    ):
        shutil.copy2(PROJECT / source, resources / destination)


def attach_linux_launcher(bundle):
    shutil.copy2(PROJECT / "assets" / "icon.png", bundle / "gridstudio.png")
    installer = bundle / "install-desktop-entry.sh"
    installer.write_text(r'''#!/bin/sh
set -eu
bundle=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# The desktop-entry standard disallows control characters and '=' in Exec.
if printf '%s' "$bundle" | LC_ALL=C grep '[[:cntrl:]=]' >/dev/null; then
    printf '%s\n' 'Use a folder without control characters or = / 请使用不含控制字符或等号的目录' >&2
    exit 1
fi
applications="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$applications"
# Exec has two escaping stages: quoted argv, then desktop-entry string escapes.
# GIO checks argv[0] before expanding %% to %. Use the fixed env executable
# and pass the actual absolute app path as an argument, preserving % in paths.
escaped=$(printf '%s' "$bundle" | sed -e 's/\\/\\\\/g' -e 's/["`$]/\\&/g' -e 's/\\/\\\\/g' -e 's/%/%%/g')
icon=$(printf '%s' "$bundle" | sed 's/\\/\\\\/g')
cat > "$applications/io.github.ssjjrrr.GridStudio.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GridStudio
Comment=Freeform multi-video player
Comment[zh_CN]=自由画布多视频播放器
Exec=/usr/bin/env -- "$escaped/GridStudio" %F
Icon=$icon/gridstudio.png
Terminal=false
Categories=AudioVideo;Player;
EOF
printf '%s\n' "Installed / 已安装: $applications/io.github.ssjjrrr.GridStudio.desktop"
''', encoding="utf-8", newline="\n")
    installer.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=PROJECT / "dist")
    parser.add_argument("--work", type=Path, default=PROJECT / "build" / "temp")
    args = parser.parse_args()
    system, architecture = native_target()
    if sys.version_info[:3] != (3, 12, 14):
        parser.error("Official bundles require Python 3.12.14 to match the included runtime license/source snapshot")
    dependencies = {name: importlib.metadata.version(name) for name in
                    ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "PyInstaller")}
    for name, version in dependencies.items():
        expected = "6.20.0" if name == "PyInstaller" else "6.10.2"
        if version != expected:
            parser.error(f"Expected {name} {expected}, found {version}")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(args.dist.resolve()), "--workpath", str(args.work.resolve()),
                    str(PROJECT / "GridStudio.spec")], cwd=PROJECT, check=True)
    bundle = default_bundle(args.dist.resolve())
    attach_documents(bundle)
    if system == "Linux":
        attach_linux_launcher(bundle)
    ffmpeg = ffmpeg_details(bundle)
    from PySide6.QtCore import qVersion
    record = {"application": VERSION, "system": system, "architecture": architecture,
              "python": platform.python_version(), "qt": qVersion(), "packages": dependencies,
              "ffmpeg": ffmpeg}
    resources = resource_directory(bundle)
    (resources / "licenses" / "runtime-versions.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (resources / "licenses" / "FFmpeg-BUILD.txt").write_text(
        f"Actual bundled FFmpeg / 实际捆绑 FFmpeg: {system} {architecture}\n"
        f"Library / 共享库: {ffmpeg['library']}\nVersion / 版本: {ffmpeg['version']}\n"
        f"License / 许可证: {ffmpeg['license']}\nConfiguration / 构建配置:\n{ffmpeg['configuration']}\n\n"
        "Values queried from this bundle's avutil API, not copied from another platform.\n"
        "以上值读取自本包 avutil API；配置中的路径属于上游构建机器。\n"
        "Source / 源代码: https://github.com/FFmpeg/FFmpeg/tree/n7.1.2\n", encoding="utf-8")
    (resources / "distribution-manifest.json").write_text(json.dumps(
        {"version": VERSION, "system": system, "architecture": architecture,
         **distribution_structure(bundle)}, indent=2) + "\n", encoding="utf-8")
    if system == "macOS":
        # Adding readable documents changes sealed Resources. Re-sign the complete
        # final bundle; this is an ad-hoc signature, not Developer ID/notarization.
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
    print(f"Built {system} {architecture}: {executable_path(bundle)}")


if __name__ == "__main__":
    main()
