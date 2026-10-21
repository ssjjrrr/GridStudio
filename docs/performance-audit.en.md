# Pre-release performance audit

[简体中文](performance-audit.md) | **English**

Before the first stable release, an internal source snapshot was compared with the optimized development build. The audit covered freeform layer changes, selection and inspectors, hover controls, crop painting, loop/synchronization timers, and packaged startup validation. The aim was to reduce repeated UI and control work while retaining image quality and independent playback.

Three-run timings, environment, counts, and source hashes are in [performance.json](../benchmarks/performance.json). These are retained measurements from before the first release, not new measurements for 1.0.0 or 1.1.0. They do not establish Linux/macOS performance.

## Implemented changes

| Area | Previous overhead | Implemented behavior | Verification |
| --- | --- | --- | --- |
| Add, clone, or remove layers | Rebuilding the canvas hid and reparented unchanged panels | Compare existing layers; attach only new panels and remove only deleted ones, retaining players, positions, and hover state | No Hide/Show/ParentChange events on existing panels; pixel and lifecycle regressions |
| Playback clock | Independent playback, native full-video loops, and fully paused sessions still woke the controller timer | Stop the controller timer for those cases; active A/B loops and synchronized groups still check every 20 ms | Timer state, wake counts, query budgets, real loop/synchronization tests |
| Synchronization queries | The same durations were queried repeatedly within a tick | Cache durations for one tick only, refreshing next tick as media loads | Different-duration percentage sync, query counts, real media |
| Group settings | Consecutive loop/rate changes repeatedly applied state | Merge state application within each operation, once per video | Counts and pause/seek/rate/loop/loading semantics |
| Hidden hover controls | Invisible controls formatted timestamps and requested painting | Store new data while hidden and refresh when shown | No hidden formatting/repainting; correct time and button state on reveal |
| Crop selection | Local selection changes repainted the whole video view | Use minimal viewport updates and limit dirty regions | Crop pixels, dirty areas, rotation/flips, cancellation |
| Selection and inspector | Repeated selection scanned all panels and rewrote all fields | Update only previous/new selections and changed inspector fields | No redundant property reads, volume updates only its fields, same-ID workspace replacements still refresh |
| Packaged verification | A screenshot alone did not prove decoding | Emit PNG/JSON diagnostics, check valid frames and errors for every open source, exit nonzero on failure | Real-media tests, packaged process exit code, decoding diagnostics |

Selection-edge invalidation, skipping unchanged pixel positions, and control-layout caching were also implemented.

## Measurements and scope

### Layer management: a bounded UI benchmark

Using the native Windows Qt platform and a 1280×720 logical-pixel window, display 16 synthetic 640×360 video frames, then perform 20 clone/delete pairs. Process the normal Qt event and painting queues after each operation. Run the baseline and optimized build sequentially three times each and compare medians.

| Metric | Internal baseline | Optimized pre-release build |
| --- | ---: | ---: |
| Total time for 20 clone/delete pairs | 5132 ms | 498 ms |
| ParentChange events on existing layers | 1280 | 0 |

Total time fell by 90.3% in this scenario. Synthetic input excludes file opening and decoding costs. This is not a measurement of single-mouse-event latency, display latency, decoding FPS, maximum concurrency, or a generally applicable speedup.

Measure the current version on Windows:

```powershell
.\.venv\Scripts\python.exe benchmarks\workspace_bench.py --platform windows --panes 16 --cycles 20 --output artifacts\workspace-current.json
```

For the historical comparison, pass `--project <baseline-source-directory>` to the same benchmark. Run at least three times per implementation, sequentially, on the same machine, scale, window, and inputs. Avoid concurrent decoding tests or other benchmarks. The internal baseline snapshot must be supplied separately; public current source can only reproduce the current side.

In the same round, with four synthetic 3840×2160 layers, medians for 120 moves and 120 resizes were 165.5 → 155.4 ms and 235.7 → 224.7 ms. Final geometry matched. These differences are comparable to run-to-run variation and are not treated as a substantial speedup.

### Synchronization: deterministic workload counts

For eight percentage-synchronized videos of different durations over 50 checks, player queries fell from 4000 to 1550 (61.3%). Joining a group applied each video's state once instead of three times.

Counting player doubles isolate controller logic. These counts do not measure CPU utilization, energy, elapsed time, or decoding load. Regressions also cover duration changes, offsets, A/B boundaries, drift correction, and incomplete media loading, avoiding permanently stale caches.

Rerun with `benchmarks/playback_query_bench.py --baseline <baseline-source-directory> --output <result.json>`. It loads baseline and current controllers against the counting players used in tests. The 50 ticks are invoked manually without processing the Qt event loop during the counted interval. Timer activity is recorded separately.

## Preserved behavior

- Resolution, image quality, and rendering sampling quality are retained. Videos continue to play while being dragged.
- Clones retain separate players and decoding paths, with independent seeking, speed, playback, or group membership. No shared decoder was introduced.
- Qt's existing occlusion painting behavior remains. The entire canvas was not declared opaque, and no unverified GPU/OpenGL rendering path was added. Transparent letterboxing and mouse pass-through remain available.
- Active A/B loops and synchronization groups retain the 20 ms interval and drift-correction semantics; idle improvements did not come from reducing their check frequency.
- Grid, focus, cloned transforms, workspace format, hover operations, and per-video audio settings remain available.

## Validation materials

Workload and correctness regressions mainly live in `tests/test_render_perf.py`, `test_playback_perf.py`, and `test_app_perf.py`, and run alongside composition-pixel, real-decoding, loop/synchronization, and panel-lifecycle tests. See [development](development.en.md) for test commands, isolated real-hover checks, subprocess deadlock tests, and CI builds.

Call counts are reproducible structural constraints; elapsed times vary by machine and system state. A separate, earlier move/resize optimization round is retained in [benchmarks/README.en.txt](../benchmarks/README.en.txt). Its percentages must not be combined with the layer-management result above.
