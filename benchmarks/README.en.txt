GridStudio performance measurements
==================================
English; 简体中文：README.txt

This directory retains measurements from before the 1.0.0 stable release. The pre-release candidate's
layer-management and playback-control implementation matched the relevant stable implementation.
Later releases retain these historical records; the cross-platform release did not remeasure them.
They do not establish Linux/macOS performance. Original values and measured source hashes are retained.
Early implementation, internal baseline, and pre-release candidate refer to internal source snapshots,
not public release versions.

Layer management and control work: internal baseline → pre-release candidate
--------------------------------------------------------------------------
Environment: Windows 11 x64, Qt/PySide6 6.10.2, 1280×720 logical pixels, 125% display scaling.
Native Windows Qt platform; baseline and candidate ran sequentially three times each. Times below are medians.
Structured samples, counts, and source hashes are in benchmarks/performance.json. Packages also include
PERFORMANCE.json (inside Contents/Resources on macOS).

Scenario / metric                                     Baseline → candidate
16 layers, 20 clone/delete pairs, total time           5132.2 → 497.9 ms (-90.3%)
ParentChange events on existing layers                 1280 → 0
Hide / Show events on existing layers                  640 each → 0 each
Select the same panel 1000 times                       10.00 → 1.25 ms
Controller wakes in a 300 ms full-loop idle observation 13/13/15 → 0/0/0 (three runs)

Layer operations use 16 synthetic 640×360 frames, excluding decoder startup and decoding costs.
Timing includes ordinary event/paint-queue processing, without per-step screenshots. Existing panels,
players, and playback positions are retained. Idle observations use synthetic input and duration doubles;
controller wakes are counted, not whole-system CPU utilization or energy consumption.

With four synthetic 3840×2160 layers, perform 120 canvas moves and 120 resizes:
  Median total move time:   165.5 → 155.4 ms.
  Median total resize time: 235.7 → 224.7 ms.
Final positions and sizes match. These small differences are comparable to run variation and are not
presented as a substantial speedup. None of these synthetic-frame figures measures 4K decoding, playback
FPS, display presentation latency, or maximum concurrent videos.

Deterministic playback-control counts (Python player doubles, no real decoding):
  64 independent full-video loops, 50 manual ticks: queries 3200 → 0.
  8 paused percentage-synchronized videos, 50 ticks: queries 2950 → 0.
  8 playing percentage-synchronized videos, 50 ticks: queries 4000 → 1550 (-61.3%).
  8 playing percentage-synchronized A/B videos, 50 ticks: queries 4400 → 1550.
  Joining an 8-video percentage group: state applications 24 → 8, or 3 → 1 per video.
Fifty ticks represent one second's work at the former 20 ms interval; this is not a one-second CPU sample.
The controller timer stops for ordinary independent playback, native full-video loops, and fully paused
sessions. Active A/B loops and synchronization still check every 20 ms.

Measure current code in PowerShell after installing requirements-dev.txt:
  .\.venv\Scripts\python.exe benchmarks\workspace_bench.py --platform windows --panes 16 --cycles 20 --output artifacts\workspace-current.json
  .\.venv\Scripts\python.exe benchmarks\interaction_bench.py --platform windows --source-width 3840 --source-height 2160 --output artifacts\interaction-4k-current.json

Strict historical reproduction requires the separately retained baseline source snapshot identified by
its recorded hashes. Current source measures only the current implementation. The baseline root must
contain gridstudio/playback.py:
  $baselineProject = Read-Host 'Internal baseline source root'
  .\.venv\Scripts\python.exe benchmarks\workspace_bench.py --project $baselineProject --platform windows --panes 16 --cycles 20 --output artifacts\workspace-before.json
  .\.venv\Scripts\python.exe benchmarks\playback_query_bench.py --baseline $baselineProject --output artifacts\playback-query-comparison.json
  interaction_bench.py also accepts --project $baselineProject.

Run timing scenarios sequentially, at least three times per implementation, using distinct output paths
and comparing medians. Keep the machine, display scaling, window, and input identical. Avoid concurrent
media tests or benchmarks. See docs/performance-audit.en.md for the complete audit and preserved behavior.

Earlier round: canvas movement / resizing (early implementation → internal baseline)
------------------------------------------------------------------------------------
The following original pre-release measurements come from an earlier round and different samples.
Do not combine their speedup percentages with the candidate comparison above or treat them as new
measurements made at stable-release time.
Environment: local Windows 11 x64, Qt/PySide6 6.10.2, 1280×720 logical pixels, 125% scaling.
Four independent video layers; real canvas mouse events act on the top layer. Each phase makes 120
consecutive moves/resizes, processing the normal Qt update queue after each. No per-frame screenshots or
forced whole-window repaints are made during timing. Both implementations use the same cProfile and
event counters. The table is one run of this controlled scenario, in milliseconds.

Input                            Move: early → baseline       Resize: early → baseline
640×360 synthetic frame          250.3 → 118.0 (-52.8%)        335.5 → 192.8 (-42.5%)
3840×2160 synthetic frame        324.3 → 141.5 (-56.4%)        413.2 → 196.2 (-52.5%)
640×360 H.264/AAC real playback  354.6 → 142.2 (-59.9%)        556.3 → 224.4 (-59.7%)

Synthetic frames isolate UI/painting work and exclude decoding; they do not prove four-stream 4K decoding.
Real playback checks valid frames and advancing timestamps on all four players before and after the
operations, with no player errors. Playback continues against wall-clock time, and Qt also delivers native
mouse events. In the real resize case, drag callbacks occurred 172 times for the early implementation and
121 for the baseline. The roughly 60% figure therefore applies only to that run's total time; the synthetic
43%–56% range provides the controlled attribution. Final geometry matches in every scenario.
These figures measure event handling and Qt painting throughput, not display latency, playback FPS,
or maximum concurrent streams.

Main changes:
Selection updates invalidate old/new edges instead of repainting the entire canvas on every move.
Repeated pixel coordinates do not trigger refreshes. Mouse movement resets the hide timer while titles,
button states, and control layout are reused when unchanged. Resizing avoids repeated hidden grid-title
updates and duplicate video fit transforms. Image quality, live playback, transparent letterboxing,
and synchronization behavior are retained.

In synthetic scenarios, total selection painting area fell by 85.7% (move) and 79.6% (resize).
Video painting area fell by 69.9% and 58.8%; transport-control layouts during resizing fell from 990 to 100.
Structured results and measured source hashes are in benchmarks/interaction-comparison.json.

Reproduce after installing dependencies, from the source directory:
  python benchmarks\interaction_bench.py --platform windows --output interaction.json
  python benchmarks\interaction_bench.py --platform windows --source-width 3840 --source-height 2160 --output interaction-4k.json
  python benchmarks\interaction_bench.py --platform windows --media demo\sample.mp4 --output interaction-real.json
  --project selects a retained internal source snapshot; run sequentially to avoid resource contention.
  --screenshot final.png saves the final window after the timed interval.
