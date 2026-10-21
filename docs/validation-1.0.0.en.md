# GridStudio 1.0.0 validation record

[简体中文](validation-1.0.0.md) | **English**

Validation date: **2026-10-22**. Environment: local Windows 11 x64, Python 3.12.14, PySide6/Qt 6.10.2.

This historical record distinguishes existing pre-release functional regressions from validation of the rebuilt stable package. Remote CI status is available in [repository Actions](https://github.com/ssjjrrr/GridStudio/actions).

## Pre-release functional regression

Run the full test suite on the `offscreen` Qt platform with both `GRIDSTUDIO_REAL_HOVER_SEEK=1` and `GRIDSTUDIO_REAL_HOVER_TRANSPORT=1`.

**Result: 241 passed, 191 subtests passed, 39.82 seconds, no skips.**

Coverage includes real H.264 decoding/seeking, loops/synchronization, cloned transforms, workspace round trips, composition pixels, transparent letterboxing and mouse pass-through, canvas editing, hover playback/volume/seek, panel lifecycle, performance workload constraints, and a subprocess seek-deadlock regression. Both real-hover tests ran in the same process as the rest of this suite.

Reproduction command from the source root in PowerShell:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:GRIDSTUDIO_REAL_HOVER_SEEK = '1'
$env:GRIDSTUDIO_REAL_HOVER_TRANSPORT = '1'
.\.venv\Scripts\python.exe -m pytest tests -q -o faulthandler_timeout=30
```

## Native Windows windows and real playback

On the native `windows` Qt platform, play four 640×360 H.264/AAC test videos and perform eight real clone/delete pairs.

- Existing panels received zero Hide or ParentChange events; their original players and layers remained intact.
- The four existing videos received **20, 21, 20, and 20** valid new decoded frames during the operations.
- A synchronized A/B range of 1000–2000 ms wrapped twice.
- The controller timer stopped on pause, restarted for synchronized playback, and stopped polling when restored to independent native full-video looping.
- Closing the window kept the controller stopped; media-state signals did not restart it.

Also completed **20 layout/focus round trips, totaling 80 transitions**, and **20 synchronized seeks while paused**. All passed. Frame counts describe that observation interval and do not measure playback FPS or maximum decoding capacity.

## Rebuilt portable package

After rebuilding 1.0.0, launch the actual `GridStudio.exe` with native Windows windows and these workspaces:

| Scenario | Video sources | Result |
| --- | ---: | --- |
| Freeform canvas editing | 3 | Valid decoded frames, NoError, exit code 0, screenshot saved |
| Overlap and hover playback controls | 2 | Valid decoded frames, NoError, exit code 0, screenshot saved |
| Synchronized A/B looping | 2 | Valid decoded frames, NoError, exit code 0, screenshot saved |

All three JSON diagnostics reported version `1.0.0`, `capture_saved=true`, and `passed=true`. Every opened source had valid video frames, positive duration, and `NoError`. Screenshots were visually inspected for playback, play/volume controls, aligned A/B markers, and transparent overlapping layers.

The homepage uses a separate non-overlapping four-panel screenshot with three public film files, captured from the same 1.0.0 portable build. All four panels had valid frames, positive durations, and `NoError`; visual inspection confirmed adjacent boundaries without gaps. See [footage sources and credits](https://github.com/ssjjrrr/GridStudio/blob/v1.0.0/docs/preview-sources.md) for sources and cropping details.

Additional checks:

- All eight license files in `licenses/SOURCES.json` matched their byte lengths and SHA-256 hashes.
- Windows EXE `FileVersion` and `ProductVersion` both equaled `1.0.0`, matching the application version.
- Required Qt, Multimedia, and FFmpeg shared libraries were present.
- The package did not contain conflicting `icuuc.dll` or `icudt78.dll` files.

## Scope

Validation applies to the local Windows 11 environment above. **It was not repeated on other computers or Windows 10.** Functional playback inputs were 640×360; the homepage additionally used 1280×720 and 960×540 footage. The 4K performance scenarios use synthetic frames and cannot establish real multi-stream 4K decoding capacity.

Historical samples and query counts are in source `benchmarks/performance.json`, included as `PERFORMANCE.json` in the portable directory. This record does not replace validation of other codecs, devices, resolutions, or long-running sessions. It does not describe the later 1.1.0 cross-platform release.
