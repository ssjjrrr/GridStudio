# Test media

[简体中文](test-media.md) | **English**

`tests/fixtures/sample.mp4` and `sample-short.mp4` are synthetic videos generated for this project to test real decoding, seeking, loops, and synchronization. Files with the same names in `demo/` are copies. They contain no film clips or user videos. Original test material is distributed under the repository's MIT license; encoding/decoding tools retain their own licenses.

| File | Duration | Video | Audio |
| --- | --- | --- | --- |
| `sample.mp4` | 12 seconds | 640×360, 24 fps, H.264 | AAC |
| `sample-short.mp4` | 6 seconds | 640×360, 24 fps, H.264 | AAC |

Regressions depend on durations and codecs, not a fixed byte hash. Existing tests do not need a command-line FFmpeg installation; PySide6's Qt Multimedia libraries provide decoding.

## Generate equivalent media

Use FFmpeg's `testsrc2` and `sine` synthetic sources to create media with the same specifications. These commands produce **equivalent test content**, not guaranteed byte-for-byte reproductions of the committed MP4 files. Encoder versions and options affect file sizes, images, and timestamps. Run all media regressions again after replacing inputs.

Place an `ffmpeg` build with libx264 and AAC encoding on PATH. From the project root in PowerShell, create an ignored output directory. `-n` prevents overwriting an existing file:

```powershell
New-Item -ItemType Directory -Path artifacts\media -Force | Out-Null

ffmpeg -nostdin -n -f lavfi -i 'testsrc2=size=640x360:rate=24:duration=12' -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=12' -map 0:v:0 -map 1:a:0 -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -c:a aac -b:a 128k -t 12 -movflags +faststart artifacts\media\sample.mp4

ffmpeg -nostdin -n -f lavfi -i 'testsrc2=size=640x360:rate=24:duration=6' -f lavfi -i 'sine=frequency=440:sample_rate=48000:duration=6' -map 0:v:0 -map 1:a:0 -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -c:a aac -b:a 128k -t 6 -movflags +faststart artifacts\media\sample-short.mp4
```

On Linux/macOS, create the directory with `mkdir -p artifacts/media`, then run the same FFmpeg commands with output paths `artifacts/media/sample.mp4` and `artifacts/media/sample-short.mp4`. These commands only generate test material; they are not required to build or run the player.

When replacing committed samples, keep the copies under `tests/fixtures/` and `demo/` identical, and recheck all `.gstudio` examples, real-media tests, and media benchmarks. Demo workspaces use relative paths; keep their MP4 files beside them when moving them. English and Chinese workspace filenames reference the same sample files.

Options are based on FFmpeg's official [synthetic-source filter documentation](https://github.com/FFmpeg/FFmpeg/blob/n7.1.2/doc/filters.texi) and [encoder documentation](https://github.com/FFmpeg/FFmpeg/blob/n7.1.2/doc/encoders.texi). The external `ffmpeg` executable used to generate media is not bundled by the player build scripts.
