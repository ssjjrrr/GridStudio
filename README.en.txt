GridStudio 1.1.0 · Freeform video player
======================================
English guide; 简体中文：README.txt
Project: https://github.com/ssjjrrr/GridStudio
Downloads: https://github.com/ssjjrrr/GridStudio/releases/tag/v1.1.0

Move, resize, clone, and overlap multiple videos. After about two seconds of mouse inactivity,
only the videos remain visible. English and Simplified Chinese are supported.
The interface follows the system language by default. Right-click Language / 语言 to choose
English, 简体中文, or System default / 跟随系统. Menu choices are saved.
Command-line --language en / --language zh_CN overrides the language for that run only.

Platforms and launch
--------------------
Windows 10 1809+ / Windows 11 x64:
  Extract all of GridStudio-1.1.0-Windows-x64.zip and run GridStudio.exe.
  Keep the entire directory, including _internal, licenses, and demo. Do not copy just the EXE.

Linux x86_64, with Ubuntu 22.04+ as the supported baseline:
  tar -xzf GridStudio-1.1.0-Linux-x64.tar.gz
  ./GridStudio/GridStudio
  Keep the directory and symbolic links intact. A graphical desktop is required.
  Run install-desktop-entry.sh in the application directory to add a launcher for your user.
  On Ubuntu 22.04, install missing graphics/audio dependencies with:
    sudo apt-get update
    sudo apt-get install libegl1 libgl1 libopengl0 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxcb-render-util0 libdbus-1-3 libasound2 libpulse0
  On Ubuntu 24.04, replace libasound2 with libasound2t64. Other distributions may use different names.
  If the native Wayland plugin has problems, try this in a desktop with XWayland enabled:
    QT_QPA_PLATFORM=xcb ./GridStudio/GridStudio
  Other distributions have not all been tested; x86_64 architecture alone does not guarantee compatibility.

macOS 13+, Apple Silicon / Intel:
  Choose macOS-arm64.zip / macOS-x64.zip respectively. Extract and drag GridStudio.app to Applications.
  Keep the complete .app. Architectures are built separately; this is not a Universal 2 application.
  Builds are ad-hoc signed, not Developer ID signed or notarized by Apple.
  If macOS reports an unidentified developer or missing notarization, confirm the source, then use System Settings → Privacy & Security
  → Open Anyway. Apple's instructions: https://support.apple.com/102445

All release packages include Python, Qt, and media libraries; no separate Python or VLC is needed.
Source and SHA-256 files are on the same release page. Linux system libraries and graphics drivers
are still supplied by the operating system.

Getting started
---------------
1. Drop local videos onto the window. Playback starts muted by default.
2. Press Tab to edit. Drag inside a video to move it; drag an edge or corner to resize.
   Hold Shift to preserve the panel's current aspect ratio. Exact position and size are also in the menu.
3. Right-click Layers to bring a video to front, send it to back, move it one step, or select a covered panel.
   Selecting a panel does not change its stacking order.
4. Right-click for cloning, fit modes, cropping, rotation, speed, loops, and synchronization.
5. Press Tab or Esc to return to clean playback; F11 toggles fullscreen.
6. Use Workspace → Save to save a .gstudio workspace.

Positions and sizes are stored relative to the canvas, preserving the composition when the window changes.
A clone appears slightly offset and on top; you can move and resize it independently.
Layout can switch to a grid. Drag dividers to resize the grid; press Tab to show titles, then drag a title
to swap panels. Windowed mode keeps the system title bar; fullscreen hides it.

Moving the mouse reveals the title, seek bar, play/pause, mute, and volume for about two seconds.
Hovering over the seek bar shows the time; click or drag to seek. A/B markers show the loop range.
Controls stay visible while dragging sliders or holding a button, then restart the hide timer.
Raising the volume unmutes the video. Volume and mute affect only that video; playback, seeking,
and looping follow the current synchronization group.

Fit modes and transforms
------------------------
Right-click Picture → Fit mode to choose:
  Keep aspect ratio (show all): the default; show the whole video or cropped region without distortion.
  Fill (crop edges): fill the panel at the original aspect ratio, hiding excess edges.
  Stretch (no crop): show the entire image filling the panel, distorting it if aspect ratios differ.
Apply the current fit mode to all panels from the same menu. Tab does not change the fit mode.
The freeform canvas has no fixed dividers, selection outline, or resize handles during clean playback.
Letterboxing created by the fit mode reveals videos below and lets mouse input pass through.
With no underlying video, it reveals the canvas background. Black pixels encoded in the file remain opaque;
use cropping to remove baked-in black bars. Grid and single-video focus modes keep normal letterboxing.

A clone keeps the source, position in the video, fit mode, crop, rotation, flips, speed, volume, playback state,
loop, and synchronization group. Ungrouped clones play independently. Transforms never modify the original file.
To crop, drag out the region to keep; release to apply, or press Esc to cancel.

Loops and synchronization
-------------------------
The Loop menu enables/disables looping or selects a full-video loop, which is the default.
Press [ to set point A at the current time, move later in the video, and press ] to set B.
Set A/B loop range accepts precise times in seconds. L temporarily disables/re-enables looping while keeping
markers; Clear A/B markers restores the full range. Loop settings are linked within a synchronization group.

Ctrl+G or Synchronize → Sync all by time aligns all videos to the current panel's time.
Percentage synchronization aligns videos of different durations to the same percentage and scales their speeds
so they reach the end together. Synchronization with time offsets preserves existing time differences.
You can assign only selected videos to a group (1–4), or remove a panel from its group. Groups are independent.
Play/pause, seeking, skip, speed, and loops are linked within a group; a clone joins the original's group.
Synchronization periodically corrects drift, suitable for comparison but not hardware-level frame locking.

Workspaces and examples
-----------------------
.gstudio stores canvas/grid mode, panel positions and sizes, stacking order, grid proportions, paths, and playback.
It does not embed video files. Move the videos with the workspace or use Replace current video to relocate them.
On Windows/Linux, demo is in the application directory. On macOS it is in
GridStudio.app/Contents/Resources/demo (Finder: right-click the app → Show Package Contents).
Open an example through Workspace → Open:
  free-canvas-and-layers.gstudio / 自由画布与图层.gstudio
  overlap-and-hover-controls.gstudio / 叠放与悬停进度.gstudio
  fit-modes.gstudio / 显示方式对比.gstudio
  synchronized-ab-loop.gstudio / 同步与区间循环.gstudio
  percentage-sync.gstudio / 百分比同步.gstudio
  four-video-comparison.gstudio / 四画面对比.gstudio
English and Chinese filenames provide the same examples. Keep sample.mp4 and sample-short.mp4 beside them.

Keyboard shortcuts
------------------
Use Command (⌘) instead of Ctrl on macOS. Some keyboards require Fn+F11.
Tab                   Edit canvas / clean playback
F11                   Fullscreen
Ctrl+O                Add videos
Ctrl+Shift+O          Open workspace
Ctrl+S                Save workspace
Ctrl+D                Clone current panel
Ctrl+[ / ]            Move one layer backward / forward
Ctrl+Shift+[ / ]      Send to back / bring to front
Shift+arrow key       Move by one pixel while editing
Ctrl+W                Close current panel
Ctrl+Q                Quit
Space / M             Play or pause / mute
L                     Toggle looping, retaining markers
[ / ]                 Set loop point A / B
Ctrl+G                Synchronize all videos to the current panel
← / →                 Seek backward / forward five seconds
R / C                 Rotate 90° clockwise / crop
F or double-click     Focus current panel / return to layout
Esc                   Cancel crop / return to layout / leave fullscreen / hide editing UI

Compatibility and performance
-----------------------------
Qt Multimedia uses FFmpeg. MP4 and MKV name containers; playback also depends on codecs and the device.
Supported formats differ from VLC/GridPlayer. Each panel has its own decoder, including clones.
Up to 64 panels are allowed. Smoothness depends on resolution, frame rate, codecs, hardware, and concurrency.
INTERACTION_PERFORMANCE.txt, INTERACTION_PERFORMANCE.en.txt, and PERFORMANCE.json retain Windows measurements
from before the first release; those values were not remeasured for this cross-platform release.
Synthetic-frame UI timings cannot establish real 4K decoding capacity or Linux/macOS performance.

Run and build from source
-------------------------
Use Python 3.12.14. In the source directory, Windows PowerShell:
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  .\.venv\Scripts\python.exe run.py
Linux/macOS:
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python run.py

After installing requirements-dev.txt, set GRIDSTUDIO_LANGUAGE=zh_CN for the test process, then run:
  python -m pytest tests -q -o faulthandler_timeout=30
Here, python means the virtual environment's interpreter. Two real-media hover tests use extra environment flags;
see source docs/development.en.md (简体中文：docs/development.md) for complete commands and platform dependencies.
Build natively with ./build.ps1 on Windows or ./build.sh on Linux/macOS.
With dependencies already installed: python scripts/build.py
Create local archives: python scripts/package_release.py --output dist/release
Verify a final archive: python scripts/verify_bundle.py --archive <archive-path> --output artifacts
These scripts do not upload files or create a GitHub release automatically.

Licenses
--------
Original application code is MIT licensed; see LICENSE.
Dependencies are documented in THIRD_PARTY_NOTICES.en.txt / THIRD_PARTY_NOTICES.txt and licenses.
licenses/runtime-versions.json and FFmpeg-BUILD.txt describe the actual release package's runtime libraries.
Original license texts are not translated or rewritten. GridPlayer inspired the multi-video workflow;
its source code is not included.
