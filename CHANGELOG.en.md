# Changelog

[简体中文](CHANGELOG.md) | **English**

## 1.1.0 — Cross-platform and bilingual support

- Add Linux x64 and macOS Apple Silicon and Intel packages alongside the Windows x64 portable build.
- Follow the system language by default. The `Language / 语言` context menu switches between English, Simplified Chinese, and the system default, saving the preference. `--language en / zh_CN` overrides a single launch.
- Add a complete English README, user guide, changelog, development and performance guides, media credits, and third-party notices. Original third-party license texts are unchanged.
- Provide English and Chinese filenames for example workspaces, retaining the same content and relative video paths.
- Queue media-driven UI updates so progress bars refresh after native seek commands return. Player command ordering is preserved, with regression coverage for pending notifications after a panel closes.
- Build and verify all four platform/architecture targets. Validation launches the executable from the final archive and records real decoding results and each platform's runtime library versions.
- Provide ad-hoc signing for macOS, without Apple Developer ID signing or notarization, and a per-user desktop launcher installer for Linux.

## 1.0.0 — First stable release

- Freeform canvas with arbitrary placement, resizing from eight handles, aspect-preserving resizing, precise geometry, and stacking order controls.
- Adjacent or overlapping videos, grid layouts, single-video focus, and clean fullscreen playback.
- Transparent, mouse-transparent letterboxing in freeform fit mode, plus proportional fill/cropping and stretch modes.
- Clone panels while retaining sources, playback positions, crops, rotations, flips, speeds, volumes, and loop/synchronization settings.
- Show titles, play/pause, progress, mute, and volume on mouse activity; hide them after about two seconds. Seek hover timestamps and A/B markers are included.
- Full-video and A/B looping; synchronization by time, with offsets, or by playback percentage; independent synchronization groups.
- Save and restore layouts, canvas composition, stacking order, video paths, and playback settings through .gstudio workspaces.
- Incremental layer updates, an on-demand controller timer, reused query/UI state, and partial repainting preserve playback independence and image quality. Historical measurements are described in the [performance audit](docs/performance-audit.en.md).
- Windows x64 portable package, source archive, SHA-256 checksums, demo workspaces, and local packaging scripts.
- Real-media and pixel/interaction regressions, subprocess seek-deadlock checks, portable decoding diagnostics, and a Windows CI workflow.
