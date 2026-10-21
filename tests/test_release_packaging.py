"""Exercise actual archive round trips; Unix CI proves links/modes survive."""

import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import zipfile

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from bundle_support import distribution_structure
from build import attach_linux_launcher, ffmpeg_details
from package_release import archive_bundle, zip_files
from verify_bundle import extract_archive


def test_ffmpeg_metadata_probe_loads_real_qt_dependency_group():
    # Exercise native dependency resolution with the actual pinned Qt runtime.
    # In particular, Linux's avutil cannot resolve RAND_bytes on its own: Qt's
    # complete FFmpeg plugin supplies the separate ssl-stub dependency.
    import PySide6
    runtime = Path(PySide6.__file__).resolve().parent
    result = ffmpeg_details(runtime)
    assert (runtime / result["library"]).is_file()
    assert result["version"] == "7.1.2"
    assert "LGPL" in result["license"] and "--enable-gpl" not in result["configuration"]


def test_source_zip_includes_executable_shell_script_and_utf8_names(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "build.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    readme = source / "说明.txt"
    readme.write_text("中文 / English", encoding="utf-8")
    archive = tmp_path / "source.zip"
    zip_files([script, readme], source, archive, "GridStudio-source")
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.read("GridStudio-source/说明.txt").decode("utf-8") == "中文 / English"
        mode = zipped.getinfo("GridStudio-source/build.sh").external_attr >> 16
        assert mode & stat.S_IXUSR


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlink and execute-bit round trip needs a Unix filesystem")
def test_native_archive_keeps_framework_links_and_executable_modes(tmp_path):
    system = "macOS" if sys.platform == "darwin" else "Linux"
    bundle = tmp_path / ("GridStudio.app" if system == "macOS" else "GridStudio")
    runtime = bundle / "Contents" / "Frameworks" if system == "macOS" else bundle / "_internal"
    runtime.mkdir(parents=True)
    executable = bundle / "GridStudio"
    executable.write_text("#!/bin/sh\nprintf 'archive-launch-ok'\n", encoding="utf-8")
    executable.chmod(0o755)
    real = runtime / "real-library"
    real.write_bytes(b"native dependency fixture")
    (runtime / "library-link").symlink_to("real-library")
    (runtime / "current").mkdir()
    (runtime / "Versions").symlink_to("current", target_is_directory=True)
    before = distribution_structure(bundle)
    archive = archive_bundle(bundle, tmp_path, system, "x64")
    extraction_root = tmp_path / "extraction-real"
    extraction_root.mkdir()
    extraction_alias = tmp_path / "extraction-alias"
    extraction_alias.symlink_to(extraction_root, target_is_directory=True)
    # Reproduce /var -> /private/var on macOS: all link containment checks
    # must use the canonical bundle root, without relaxing link validation.
    extracted = extract_archive(archive, extraction_alias / "extract", system)
    assert extracted == extracted.resolve()
    assert distribution_structure(extracted) == before
    for relative in before["symlinks"]:
        assert (extracted / relative).resolve().is_relative_to(extracted)
    assert (extracted / runtime.relative_to(bundle) / "library-link").read_bytes() == real.read_bytes()
    result = subprocess.run([str(extracted / "GridStudio")], check=True, capture_output=True)
    assert result.stdout == b"archive-launch-ok"


@pytest.mark.skipif(sys.platform != "linux", reason="Linux desktop integration")
def test_linux_desktop_installer_launches_path_with_reserved_characters(tmp_path):
    # Exercise the real GIO desktop parser, not a hand-written imitation of it.
    gio = shutil.which("gio")
    if gio is None:
        pytest.skip("gio is required to exercise Linux desktop launch")
    bundle = tmp_path / '视频 path "quote" $dollar %percent `tick` \\slash'
    bundle.mkdir()
    attach_linux_launcher(bundle)
    marker = tmp_path / "launched.txt"
    executable = bundle / "GridStudio"
    executable.write_text('#!/bin/sh\nprintf "%s" "$0" > "$GRIDSTUDIO_LAUNCH_MARKER"\n', encoding="utf-8")
    executable.chmod(0o755)
    env = dict(os.environ, XDG_DATA_HOME=str(tmp_path / "user data"), GRIDSTUDIO_LAUNCH_MARKER=str(marker))
    subprocess.run([str(bundle / "install-desktop-entry.sh")], env=env, check=True)
    desktop = Path(env["XDG_DATA_HOME"]) / "applications" / "io.github.ssjjrrr.GridStudio.desktop"
    assert desktop.is_file()
    result = subprocess.run([gio, "launch", str(desktop)], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, (result.stderr, desktop.read_text(encoding="utf-8"))
    # GIO launches asynchronously; allow the tiny fixture to finish.
    import time
    deadline = time.monotonic() + 5
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert marker.read_text(encoding="utf-8") == str(executable)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux desktop integration")
def test_linux_desktop_installer_rejects_invalid_exec_path_without_writing_entry(tmp_path):
    bundle = tmp_path / "unsupported=path"
    bundle.mkdir()
    attach_linux_launcher(bundle)
    env = dict(os.environ, XDG_DATA_HOME=str(tmp_path / "user data"))
    result = subprocess.run([str(bundle / "install-desktop-entry.sh")], env=env, capture_output=True)
    assert result.returncode != 0
    assert not Path(env["XDG_DATA_HOME"]).exists()
