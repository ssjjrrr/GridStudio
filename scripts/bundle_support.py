"""Platform paths shared by native build, archive and verification commands."""

from pathlib import Path
import platform
import runpy
import stat
import sys

PROJECT = Path(__file__).resolve().parents[1]
VERSION = runpy.run_path(str(PROJECT / "gridstudio" / "__init__.py"))["__version__"]


def native_target():
    system = {"win32": "Windows", "linux": "Linux", "darwin": "macOS"}.get(sys.platform)
    machine = platform.machine().lower()
    architecture = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if not system or not architecture or (system != "macOS" and architecture != "x64"):
        raise RuntimeError(f"Unsupported native build target: {sys.platform}/{machine}")
    return system, architecture


def default_bundle(dist=None):
    return (dist or PROJECT / "dist") / ("GridStudio.app" if sys.platform == "darwin" else "GridStudio")


def resource_directory(bundle):
    return bundle / "Contents" / "Resources" if bundle.suffix == ".app" else bundle


def executable_path(bundle):
    if bundle.suffix == ".app":
        return bundle / "Contents" / "MacOS" / "GridStudio"
    return bundle / ("GridStudio.exe" if sys.platform == "win32" else "GridStudio")


def distribution_structure(bundle):
    """Record the links and executable modes that ZIP/tar must preserve."""
    links, executable_files = {}, []
    for path in sorted(bundle.rglob("*")):
        relative = path.relative_to(bundle).as_posix()
        if path.is_symlink():
            if not path.resolve().is_relative_to(bundle.resolve()) or not path.exists():
                raise RuntimeError(f"Broken or external bundle symlink: {relative}")
            links[relative] = path.readlink().as_posix()
        elif path.is_file() and path.stat().st_mode & stat.S_IXUSR:
            executable_files.append(relative)
    return {"symlinks": links, "executable_files": executable_files}
