"""Clock wakeups and native-query budgets, without opening a media source.

These are deterministic work-count regressions, not wall-clock timing claims.
The existing engine tests cover offset, A/B, end-of-media and cooldown behavior.
"""

from collections import Counter

import pytest
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QSignalSpy
from scripts.qt_test_support import qt_wait

from gridstudio.playback import PlaybackController
from test_playback_engine import FakePlayer, Owner, application


class CountingPlayer(FakePlayer):
    def __init__(self, duration, position, paused, name, events):
        super().__init__(duration, position, paused)
        self.queries = Counter()
        self.name = name
        self.events = events

    def duration(self):
        self.queries["duration"] += 1
        return super().duration()

    def position(self):
        self.queries["position"] += 1
        return super().position()

    def playbackState(self):
        self.queries["playbackState"] += 1
        return super().playbackState()

    def mediaStatus(self):
        self.queries["mediaStatus"] += 1
        return super().mediaStatus()

    def setPosition(self, value):
        self.events.append((self.name, "seek", value))
        super().setPosition(value)

    def play(self):
        self.events.append((self.name, "play"))
        super().play()


class CountingOwner(Owner):
    def __init__(self):
        super().__init__()
        self.events = []
        self.refreshes = 0

    def refresh_inspector(self):
        self.refreshes += 1

    def add(self, name, *, duration=10_000, position=1000, paused=True):
        pane = super().add(name, duration=duration, position=position, paused=paused)
        pane.player = CountingPlayer(duration, position, paused, name, self.events)
        pane.applied = []

        def apply():
            value = (pane.state.loop_start_ms, pane.state.loop_end_ms,
                     pane.state.rate, pane.state.paused)
            pane.applied.append(value)
            self.events.append((name, "apply", value))

        pane.apply_state = apply
        return pane

    def clear_counts(self):
        self.events.clear()
        self.refreshes = 0
        for pane in self.panes.values():
            pane.player.queries.clear()
            pane.applied.clear()


@pytest.fixture
def perf_rig(application):
    owner = CountingOwner()
    controller = PlaybackController(owner)
    yield owner, controller
    controller.shutdown()
    controller.deleteLater()
    owner.deleteLater()


def make_percent_group(owner, controller, *, paused=False, count=8):
    panes = [owner.add(str(i), duration=10_000 * (i + 1),
                       position=1000 * (i + 1), paused=paused) for i in range(count)]
    assert controller.join_group([p.state.id for p in panes], mode="percent")
    owner.clear_counts()
    return panes


@pytest.mark.parametrize("loop", [False, True])
def test_independent_whole_video_playback_has_no_clock_or_native_polling(perf_rig, loop):
    owner, controller = perf_rig
    for i in range(64):
        owner.add(str(i), paused=False).state.loop = loop
    controller.refresh_activity()
    assert not controller.timer.isActive()
    for _ in range(50):
        controller.tick()
    assert all(not p.player.queries for p in owner.panes.values())


def test_paused_groups_do_not_poll_and_allow_outside_ab_inspection(perf_rig):
    owner, controller = perf_rig
    panes = make_percent_group(owner, controller, paused=True)
    assert controller.set_loop("0", True, 2000, 4000)
    controller.seek("0", 8000)
    owner.clear_counts()
    controller.refresh_activity()
    assert not controller.timer.isActive()
    for _ in range(50):
        controller.tick()
    assert all(not p.player.queries for p in panes)
    assert [p.player.pos for p in panes] == [8000 * (i + 1) for i in range(8)]


def test_idle_clock_has_no_timeout_wakeups(perf_rig):
    owner, controller = perf_rig
    owner.add("native-loop", paused=False)
    controller.refresh_activity()
    timeouts = QSignalSpy(controller.timer.timeout)
    qt_wait(70)
    assert timeouts.count() == 0


def test_ab_activity_tracks_actions_and_native_loop_restoration(perf_rig):
    owner, controller = perf_rig
    pane = owner.add("a", paused=False)
    assert controller.set_loop("a", True, 1000, 3000)
    assert controller.timer.isActive()
    controller.set_playing("a", False)
    assert not controller.timer.isActive()
    controller.set_playing("a", True)
    assert controller.timer.isActive()
    assert controller.clear_loop("a")
    assert pane.state.loop and pane.state.loop_end_ms is None
    assert not controller.timer.isActive()


def test_activity_uses_no_getters_and_loading_or_disposed_panes_do_not_wake_it(perf_rig):
    owner, controller = perf_rig
    pane = owner.add("a", paused=False)
    pane.state.loop_end_ms = 2000
    pane._pending_restore = True
    controller.refresh_activity()
    assert not controller.timer.isActive()
    pane._pending_restore = False
    controller.media_ready("a")
    assert controller.timer.isActive()
    pane._disposed = True
    controller.refresh_activity()
    assert not controller.timer.isActive()
    assert not pane.player.queries


def test_shutdown_prevents_lifecycle_callbacks_from_restarting_timer(perf_rig):
    owner, controller = perf_rig
    pane = owner.add("a", paused=False)
    pane.state.loop_end_ms = 2000
    controller.refresh_activity()
    assert controller.timer.isActive()
    controller.shutdown()
    controller.refresh_activity()
    controller.media_ready("a")
    controller.tick()  # An already-queued EndOfMedia callback may still run.
    assert not controller.timer.isActive()
    assert not pane.player.queries


def test_group_pause_resume_and_leave_refresh_clock_without_media_signals(perf_rig):
    owner, controller = perf_rig
    panes = make_percent_group(owner, controller)
    assert controller.timer.isActive()
    controller.set_playing("3", False)
    assert not controller.timer.isActive()
    controller.set_playing("1", True)
    assert controller.timer.isActive()
    controller.leave_group([p.state.id for p in panes])
    assert not controller.timer.isActive()


def test_nonloop_group_end_stops_clock_and_resume_restarts_it(perf_rig):
    owner, controller = perf_rig
    panes = make_percent_group(owner, controller)
    assert controller.set_loop("0", False)
    for pane in panes:
        pane.player.pos = pane.player.length
        pane.player.status = QMediaPlayer.MediaStatus.EndOfMedia
    controller.tick()
    assert not controller.timer.isActive()
    assert all(p.state.paused for p in panes)
    controller.set_playing("2", True)
    assert controller.timer.isActive()
    assert all(p.player.pos == 0 and p.player.playing for p in panes)


def test_reset_stops_clock_until_new_workspace_activity_is_refreshed(perf_rig):
    owner, controller = perf_rig
    panes = make_percent_group(owner, controller)
    assert controller.timer.isActive()
    controller.reset()
    assert not controller.timer.isActive()
    for pane in panes:
        pane.state.paused = True
    controller.refresh_activity()
    assert not controller.timer.isActive()
    panes[0].state.paused = False
    controller.refresh_activity()
    assert controller.timer.isActive()


def test_active_percent_tick_reads_duration_and_position_once_per_member(perf_rig):
    owner, controller = perf_rig
    panes = make_percent_group(owner, controller)
    controller.tick()
    assert all(p.player.queries["duration"] == 1 for p in panes)
    assert all(p.player.queries["position"] == 1 for p in panes)
    assert not any(event[1] == "seek" for event in owner.events)


def test_drift_seek_reuses_current_position_and_duration_but_honors_cooldown(perf_rig, monkeypatch):
    owner, controller = perf_rig
    panes = make_percent_group(owner, controller, count=2)
    follower = panes[1]
    now = [100.0]
    monkeypatch.setattr("gridstudio.playback.time.monotonic", lambda: now[0])
    controller._last_seek.clear()
    follower.player.pos = 1500
    controller.tick()
    assert follower.player.seeks == [2000]
    assert follower.player.queries["position"] == follower.player.queries["duration"] == 1
    owner.clear_counts()
    follower.player.pos = 1400
    controller.tick()
    assert follower.player.seeks == [2000]
    assert follower.player.queries["position"] == follower.player.queries["duration"] == 1
    now[0] += .5
    controller.tick()
    assert follower.player.seeks == [2000, 2000]


def test_duration_snapshot_does_not_survive_a_tick(perf_rig):
    owner, controller = perf_rig
    panes = make_percent_group(owner, controller, count=2)
    controller.tick()
    owner.clear_counts()
    panes[1].player.length = 40_000
    controller.tick()
    assert panes[1].player.pos == 4000
    assert panes[1].player.queries["duration"] == 1


@pytest.mark.parametrize("action", ["seek", "loop", "rate"])
def test_percent_actions_read_duration_once_per_member(perf_rig, action):
    owner, controller = perf_rig
    panes = make_percent_group(owner, controller)
    if action == "seek":
        controller.seek("0", 3000)
        assert [p.player.pos for p in panes] == [3000 * (i + 1) for i in range(8)]
    elif action == "loop":
        assert controller.set_loop("0", True, 2000, 4000)
        assert [p.state.loop_end_ms for p in panes] == [4000 * (i + 1) for i in range(8)]
    else:
        assert controller.set_rate("0", .5)
        assert [p.state.rate for p in panes] == [.5 * (i + 1) for i in range(8)]
    assert all(p.player.queries["duration"] == 1 for p in panes)


def test_join_applies_loop_rate_and_intent_once_before_seek_and_play(perf_rig):
    owner, controller = perf_rig
    a = owner.add("a", position=2500, paused=False)
    b = owner.add("b", duration=20_000, position=7000)
    a.state.rate = 1.5
    a.state.loop_start_ms, a.state.loop_end_ms = 1000, 8000
    assert controller.join_group(["a", "b"], leader_id="a", mode="percent")
    assert a.applied == [(1000, 8000, 1.5, False)]
    assert b.applied == [(2000, 16_000, 3.0, False)]
    assert owner.refreshes == 1
    assert (b.player.pos, b.player.playing) == (5000, True)
    apply_indices = [i for i, event in enumerate(owner.events) if event[1] == "apply"]
    transport_indices = [i for i, event in enumerate(owner.events) if event[1] in ("seek", "play")]
    assert max(apply_indices) < min(transport_indices)


def test_media_ready_applies_group_settings_once_with_updated_duration(perf_rig):
    owner, controller = perf_rig
    panes = make_percent_group(owner, controller, count=2)
    panes[1].player.length = 40_000
    controller.media_ready("1")
    assert all(len(p.applied) == 1 for p in panes)
    assert owner.refreshes == 1
    assert panes[1].state.rate == 4
    assert panes[1].player.pos == 4000

