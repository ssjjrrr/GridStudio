"""Read actual FFmpeg metadata without mixing build-process native libraries."""

import ctypes
import json
import os
from pathlib import Path
import sys


def unique_library(bundle, pattern):
    paths = sorted({path.resolve() for path in bundle.rglob(pattern)})
    if len(paths) != 1 or not paths[0].is_relative_to(bundle):
        raise RuntimeError(f"Expected one bundled {pattern} library, found {paths}")
    return paths[0]


def query(bundle):
    # Query the actual ABI filename linked by Qt's FFmpeg 7.1.2 plugin. The
    # Linux wheel also contains a fully versioned copy (59.39.100), whereas
    # PyInstaller collects the SONAME file used by the runtime loader.
    patterns = {"win32": "avutil-59.dll", "darwin": "libavutil.59.dylib", "linux": "libavutil.so.59"}
    path = unique_library(bundle, patterns[sys.platform])
    handles = []
    try:
        if sys.platform == "win32":
            handles = [os.add_dll_directory(str(parent)) for parent in
                       sorted({path.parent for path in bundle.rglob("*.dll")})]
        elif sys.platform == "linux":
            # Qt patches FFmpeg to use its optional-dependency stubs. In Qt
            # 6.10, RAND_bytes lives in the ssl stub, not the crypto stub that
            # avutil links directly. Load the complete plugin dependency group
            # as Qt does, rather than loading avutil in isolation. Keep it local.
            plugin = ctypes.CDLL(str(unique_library(bundle, "libffmpegmediaplugin.so")),
                                 mode=ctypes.RTLD_LOCAL)
        library = ctypes.CDLL(str(path))
        result = {"library": path.relative_to(bundle).as_posix()}
        for key, name in (("version", "av_version_info"), ("license", "avutil_license"),
                          ("configuration", "avutil_configuration")):
            function = getattr(library, name)
            function.argtypes, function.restype = [], ctypes.c_char_p
            result[key] = function().decode("utf-8")
        return result
    finally:
        for handle in handles:
            handle.close()


if __name__ == "__main__":
    print(json.dumps(query(Path(sys.argv[1]).resolve()), ensure_ascii=False))
