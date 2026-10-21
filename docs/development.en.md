# Development, testing, and builds

[简体中文](development.md) | **English**

Build and verify on the target operating system. Development uses Python 3.12.14 and PySide6/Qt 6.10.2; pytest and PyInstaller versions are pinned in `requirements-dev.txt`. CI targets Windows x64, Ubuntu 22.04 x64, and macOS Apple Silicon and Intel. Platform requirements follow [Qt 6.10](https://doc.qt.io/qt-6.10/supported-platforms.html). Check [Actions](https://github.com/ssjjrrr/GridStudio/actions) and the [release validation record](validation-1.1.0.md) for actual results.

## Set up an environment

Run from the project directory. Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe run.py
```

Linux / macOS terminal:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python run.py
```

For runtime use only, install `requirements.txt`. Below, `python` means your virtual environment's interpreter: `.\.venv\Scripts\python.exe` on Windows or `.venv/bin/python` on Linux/macOS. On macOS, match the Python architecture to the target package. Apple Silicon and Intel are built separately; there is no merged Universal 2 package.

Linux requires a graphical desktop and system graphics/audio libraries. Headless CI also needs Xvfb. Common dependencies on Ubuntu:

```sh
sudo apt-get update
sudo apt-get install libegl1 libgl1 libopengl0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-render-util0 libdbus-1-3 libasound2 libpulse0
```

These names apply to Ubuntu 22.04. Other distributions may use different names; see [Qt's X11 requirements](https://doc.qt.io/qt-6.10/linux-requirements.html). Ubuntu 24.04 names the ALSA package `libasound2t64`; use the package provided by your distribution.

## Run tests

Windows PowerShell:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:QT_MEDIA_BACKEND = 'ffmpeg'
$env:GRIDSTUDIO_LANGUAGE = 'zh_CN'
.\.venv\Scripts\python.exe -m pytest tests -q -o faulthandler_timeout=30
```

Linux / macOS:

```sh
QT_QPA_PLATFORM=offscreen QT_MEDIA_BACKEND=ffmpeg GRIDSTUDIO_LANGUAGE=zh_CN .venv/bin/python -m pytest tests -q -o faulthandler_timeout=30
```

Test commands set `GRIDSTUDIO_LANGUAGE=zh_CN` because shared UI regressions assert Chinese labels. Dedicated language tests exercise both languages. This is a test-process override and does not change saved application preferences.

Tests require the committed `tests/fixtures/sample.mp4` and `sample-short.mp4`. The FFmpeg command-line tool is not required. See [test media](test-media.en.md) for provenance and generation instructions.

The main suite covers models, real playback/seeking/cloning, loops and synchronization, composition pixels, editing gestures, transparent letterboxing, hover controls, player disposal, and language switching. Two real-media hover tests are enabled by environment flags. CI runs them separately to isolate failures. On Windows:

```powershell
$env:GRIDSTUDIO_REAL_HOVER_SEEK = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_hover_controls.py::test_real_video_hover_seek_updates_paused_decoder_frame -q -o faulthandler_timeout=30
Remove-Item Env:GRIDSTUDIO_REAL_HOVER_SEEK
$env:GRIDSTUDIO_REAL_HOVER_TRANSPORT = '1'
.\.venv\Scripts\python.exe -m pytest tests/test_hover_transport.py::test_real_media_buttons_play_pause_and_volume_update_audio -q -o faulthandler_timeout=30
Remove-Item Env:GRIDSTUDIO_REAL_HOVER_TRANSPORT
```

On Linux/macOS, each line sets flags only for that command:

```sh
QT_QPA_PLATFORM=offscreen QT_MEDIA_BACKEND=ffmpeg GRIDSTUDIO_LANGUAGE=zh_CN GRIDSTUDIO_REAL_HOVER_SEEK=1 .venv/bin/python -m pytest tests/test_hover_controls.py::test_real_video_hover_seek_updates_paused_decoder_frame -q -o faulthandler_timeout=30
QT_QPA_PLATFORM=offscreen QT_MEDIA_BACKEND=ffmpeg GRIDSTUDIO_LANGUAGE=zh_CN GRIDSTUDIO_REAL_HOVER_TRANSPORT=1 .venv/bin/python -m pytest tests/test_hover_transport.py::test_real_media_buttons_play_pause_and_volume_update_audio -q -o faulthandler_timeout=30
```

You can also enable both flags and run the entire suite. Each command must exit with code 0. `faulthandler_timeout` prints thread stacks after 30 seconds but does not terminate tests; CI has separate step/job limits, and the native deadlock regression has a subprocess deadline.

### Waiting and timeout diagnostics for multi-video tests

Tests and benchmarks use the wait helpers in [`scripts/qt_test_support.py`](../scripts/qt_test_support.py), continuing to process Qt events and `DeferredDelete`. Do not drive multi-video tests directly with PySide6 6.10.2's `QTest.qWait`: that binding holds the GIL, so deferred deletion can deadlock with QObject connection locks on the audio-rendering thread. The helpers use GIL-releasing `QCoreApplication.processEvents(flags, int)` and `sendPostedEvents`, preserving actual object disposal. Both interfaces are marked `allow-thread="yes"` in the [official 6.10.2 type system](https://github.com/pyside/pyside-setup/blob/v6.10.2/sources/pyside6/PySide6/QtCore/typesystem_core_common.xml#L2777).

The macOS native thread sample from [diagnostic run 39676275048](https://github.com/ssjjrrr/GridStudio/actions/runs/39676275048) shows the main thread processing deferred deletion inside `QTest.qWait`, then waiting on a mutex during `QPropertyAnimation` / `QObject` destruction. The `AudioRenderer` thread follows another `QObject` destructor path through `QAudioOutputWrapper.disconnectNotify` and waits in `PyGILState_Ensure`. This supports the GIL/connection-lock deadlock diagnosis; the sample does not identify the two destructor paths as the same QObject instance.

CI's [`scripts/run_diagnostics.py`](../scripts/run_diagnostics.py) watchdog saves logs and, on macOS, captures a native thread sample when output stalls or the wall-time limit expires, then fails with exit code 124. macOS ARM additionally configures **50 offscreen and 50 Cocoa runs** of the same synchronization, cloning, and disposal regression. This describes the checks, not a passing result; consult the corresponding Actions logs.

### Native seek deadlock regression

```sh
python -m pytest tests/test_seek_deadlock.py -q -o faulthandler_timeout=30
```

A subprocess opens a real video, creates a controlled Qt connection-lock contention window, seeks through the media command path, and checks decoded frames. The parent allows ten seconds. This verifies the constructed lock ordering; it does not reproduce every intermittent hang. Normal CI runs the `fixed` mode only.

## Build natively

Windows:

```powershell
.\build.ps1
```

Linux / macOS:

```sh
./build.sh
```

The wrappers create or reuse `.venv`, install pinned dependencies and PyInstaller, and call `scripts/build.py`. On Windows, select an interpreter with `./build.ps1 -Python <path>`; on Unix, use `PYTHON=/path/to/python3 ./build.sh`. If `.venv` already exists, verify its interpreter version and architecture first. With development dependencies installed:

```sh
python scripts/build.py
```

Windows/Linux output is `dist/GridStudio/`; macOS output is `dist/GridStudio.app`. Documents, demos, and licenses are in the application directory on Windows/Linux and in `Contents/Resources/` on macOS. The application version comes from `gridstudio.__version__`; Windows file/product versions and macOS bundle versions must match it.

The package includes Chinese and English guides, changelogs, third-party notices, `licenses/`, `demo/`, performance records, and validation notes. `licenses/runtime-versions.json` and `licenses/FFmpeg-BUILD.txt` record the libraries actually inspected in that build. License checksums are in `licenses/SOURCES.json`. The source tree's FFmpeg configuration remains a historical Windows reference.

Distribute the complete Windows directory rather than just the EXE. Linux TAR.GZ preserves executable permissions and symbolic links. macOS `.app` bundles are ad-hoc signed; they are not Developer ID signed or notarized by Apple.

## Create local release archives

After testing and building natively:

```sh
python scripts/package_release.py --output dist/release
```

The script selects the build output for the current platform and architecture and reads `gridstudio.__version__`. It creates the corresponding `GridStudio-<version>-Windows-x64.zip`, `-Linux-x64.tar.gz`, `-macOS-arm64.zip`, or `-macOS-x64.zip`, plus a source ZIP and SHA-256 manifest. Use `--skip-source` to avoid duplicate source archives when assembling a multi-platform release.

The source archive includes selected code, documentation, workflows, tests, demos, and licenses, excluding virtual environments, Git metadata, and build caches. macOS ZIP creation uses `ditto` to preserve the application bundle. Packaging only writes local files; it does not contact GitHub or create a release.

## Verify the final archive

Run on the same platform and architecture as the archive, for example:

```sh
python scripts/verify_bundle.py --archive dist/release/GridStudio-1.1.0-Linux-x64.tar.gz --output artifacts
```

On Windows/macOS, pass the corresponding ZIP. If using the same PowerShell session as the tests, first clear the test-only overrides so the verifier selects the native window backend and later launches follow the user preference:

```powershell
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
Remove-Item Env:GRIDSTUDIO_LANGUAGE -ErrorAction SilentlyContinue
```

On Linux/macOS, the test commands above scope their overrides to each command. If you exported `QT_QPA_PLATFORM` yourself, unset it or select `xcb` on Linux / `cocoa` on macOS before verification. The verifier extracts the final archive, checks files, runtime libraries, and license records, then launches its actual executable to capture a PNG and JSON decoding diagnostics. Testing the build directory alone cannot detect archive damage such as lost symlinks, executable permissions, or `.app` structure.

Graphical launch checks need a usable desktop: native windows on Windows, Cocoa on macOS, and an X11 display supplied by Xvfb in headless Linux CI. On a normal desktop, also inspect playback, hover interactions, dragging, and fullscreen visually. Media tests cover seeking, loop, and synchronization semantics in more detail.

## CI

The [workflow](../.github/workflows/ci.yml) runs on pushes, pull requests, and manual dispatches, using `windows-2022`, `ubuntu-22.04`, `macos-15` (Apple Silicon), and `macos-15-intel`. The workflow file is authoritative for runner labels and steps.

Each platform installs dependencies, runs the tests and real-media hover checks, builds natively, packages, and verifies the executable extracted from the final archive. Results and archives are retained as Actions artifacts. CI does not automatically create GitHub releases.

The full regression suite uses `offscreen`. The two isolated real-media hover tests and native interaction checks use Windows, Cocoa, or X11/xcb (with Xvfb on Linux), covering actual seeking and playback controls on each system's window backend.

CI pins `astral-sh/setup-uv` and uv to obtain Python 3.12.14 standalone builds and verifies the interpreter version. Python 3.12.14 is a source-only security release, so it cannot be assumed available through `actions/setup-python` on every platform. Subsequent steps consistently use `.venv`.

References: [Python 3.12.14](https://www.python.org/downloads/release/python-31214/) · [setup-uv](https://github.com/astral-sh/setup-uv) · [uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/)

## Performance measurements

Retained historical measurements use the native Windows Qt platform. These PowerShell examples measure the current implementation:

```powershell
.\.venv\Scripts\python.exe benchmarks\interaction_bench.py --platform windows --output artifacts\interaction-current.json
.\.venv\Scripts\python.exe benchmarks\interaction_bench.py --platform windows --media demo\sample.mp4 --output artifacts\interaction-real.json
.\.venv\Scripts\python.exe benchmarks\workspace_bench.py --platform windows --panes 16 --cycles 20 --output artifacts\workspace-current.json
```

Rerunning the historical comparison requires its separately retained internal source snapshot:

```powershell
$baselineProject = Read-Host 'Internal baseline source root'
.\.venv\Scripts\python.exe benchmarks\playback_query_bench.py --baseline $baselineProject --output artifacts\playback-query-comparison.json
```

Run benchmarks sequentially, at least three times per implementation, and compare medians on the same machine, scale, window, and inputs. Timings are not stable CI thresholds, decoding FPS, or input-to-display latency. These historical values were not remeasured for the cross-platform release; Windows results do not establish Linux/macOS performance. See the [audit](performance-audit.en.md), [benchmark guide](../benchmarks/README.en.txt), and [structured data](../benchmarks/performance.json).
