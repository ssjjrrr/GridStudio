"""Deterministic clock, loop and group semantics without a video decoder."""

import os
from types import SimpleNamespace

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PySide6.QtCore import QObject
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication

from gridstudio.model import PaneState
from gridstudio.playback import PlaybackController


class FakePlayer:
    def __init__(self, duration, position, paused):
        self.length = duration
        self.pos = position
        self.playing = not paused
        self.status = QMediaPlayer.MediaStatus.LoadedMedia
        self.seeks = []

    def duration(self):
        return self.length

    def position(self):
        return self.pos

    def playbackState(self):
        return QMediaPlayer.PlaybackState.PlayingState if self.playing else QMediaPlayer.PlaybackState.PausedState

    def mediaStatus(self):
        return self.status

    def setPosition(self, value):
        self.pos = value
        self.seeks.append(value)
        self.status = QMediaPlayer.MediaStatus.LoadedMedia

    def play(self):
        self.playing = True

    def pause(self):
        self.playing = False


class Owner(QObject):
    def __init__(self):
        super().__init__()
        self.panes = {}
        self.messages = []

    def notify(self, text):
        self.messages.append(text)

    def refresh_inspector(self):
        pass

    def add(self, name, *, duration=10_000, position=1000, paused=True):
        state = PaneState(id=name, source=name + ".mp4", position_ms=position, paused=paused)
        player = FakePlayer(duration, position, paused)
        pane = SimpleNamespace(state=state, player=player, _pending_restore=False, apply_state=lambda: None)
        self.panes[name] = pane
        return pane


@pytest.fixture(scope="session")
def application():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def rig(application):
    owner = Owner()
    controller = PlaybackController(owner)
    controller.timer.stop()
    yield owner, controller
    controller.deleteLater()
    owner.deleteLater()


def test_join_aligns_position_rate_and_playback(rig):
    owner, controller = rig
    a = owner.add("a", position=2500, paused=False)
    b = owner.add("b", position=7500)
    a.state.rate = 1.5
    assert controller.join_group(["a", "b"], leader_id="a")
    assert b.player.position() == 2500
    assert b.state.rate == 1.5
    assert b.player.playing and not b.state.paused
    assert a.state.sync_group == b.state.sync_group == "1"


def test_already_aligned_join_and_resume_do_not_seek_native_players(rig):
    owner, controller = rig
    panes = [owner.add(name, position=1000) for name in "abcd"]
    assert controller.join_group(list("abcd"))
    assert all(p.player.seeks == [] for p in panes)
    controller.set_playing("a", True)
    controller.set_playing("a", False)
    controller.seek("b", 1000)
    assert all(p.player.seeks == [] for p in panes)
    assert all(p.state.position_ms == 1000 for p in panes)


def test_actions_from_any_member_control_only_its_group(rig):
    owner, controller = rig
    a, b, c = (owner.add(x) for x in "abc")
    controller.join_group(["a", "b"])
    controller.seek("b", 4200)
    assert a.player.position() == b.player.position() == 4200
    assert c.player.position() == 1000
    controller.set_playing("b", True)
    assert a.player.playing and b.player.playing and not c.player.playing
    controller.set_rate("b", 1.75)
    assert a.state.rate == b.state.rate == 1.75
    assert c.state.rate == 1
    controller.set_playing("a", False)
    assert not a.player.playing and not b.player.playing


def test_offsets_preserve_relative_positions_and_seek_from_follower(rig):
    owner, controller = rig
    a = owner.add("a", position=1000)
    b = owner.add("b", position=3000)
    controller.join_group(["a", "b"], leader_id="a", preserve_offsets=True)
    assert b.state.sync_offset_ms == 2000
    assert b.player.position() == 3000
    controller.seek("b", 6000)
    assert a.player.position() == 4000
    assert b.player.position() == 6000


def test_loop_markers_propagate_with_offsets_and_wrap_together(rig):
    owner, controller = rig
    a = owner.add("a", position=1000, paused=False)
    b = owner.add("b", position=3000)
    controller.join_group(["a", "b"], preserve_offsets=True)
    assert controller.set_loop("a", True, 1000, 2000)
    assert (b.state.loop_start_ms, b.state.loop_end_ms) == (3000, 4000)
    a.player.pos, b.player.pos = 2010, 4010
    controller.tick()
    assert (a.player.pos, b.player.pos) == (1000, 3000)
    assert a.player.playing and b.player.playing


def test_group_whole_loop_uses_shortest_duration(rig):
    owner, controller = rig
    a = owner.add("a", duration=10_000, paused=False)
    b = owner.add("b", duration=5000)
    controller.join_group(["a", "b"])
    a.player.pos = b.player.pos = 5000
    controller.tick()
    assert (a.player.pos, b.player.pos) == (0, 0)


def test_group_nonloop_pauses_every_member_at_shortest_end(rig):
    owner, controller = rig
    a = owner.add("a", duration=10_000, paused=False)
    b = owner.add("b", duration=5000)
    a.state.loop = False
    controller.join_group(["a", "b"])
    a.player.pos = b.player.pos = 5000
    controller.tick()
    assert not a.player.playing and not b.player.playing
    assert a.state.paused and b.state.paused
    assert (a.player.pos, b.player.pos) == (5000, 5000)
    controller.set_playing("b", True)
    assert (a.player.pos, b.player.pos) == (0, 0)


def test_ab_loop_repeats_short_segments_without_drift_cooldown(rig):
    owner, controller = rig
    a = owner.add("a", paused=False)
    controller.set_loop("a", True, 1000, 1100)
    a.player.pos = 1105
    controller.tick()
    assert a.player.pos == 1000
    controller.tick()  # Observe the seek landing inside A/B.
    a.player.pos = 1105
    controller.tick()
    assert a.player.pos == 1000
    assert a.player.seeks == [1000, 1000]


def test_a_only_loops_from_a_to_end(rig):
    owner, controller = rig
    a = owner.add("a", paused=False)
    controller.set_loop("a", True, 2000)
    a.player.pos = 10_000
    a.player.playing = False
    a.player.status = QMediaPlayer.MediaStatus.EndOfMedia
    controller.tick()
    assert a.player.pos == 2000 and a.player.playing


def test_paused_seek_outside_ab_is_left_for_inspection(rig):
    owner, controller = rig
    a = owner.add("a")
    controller.set_loop("a", True, 2000, 4000)
    controller.seek("a", 8000)
    controller.tick()
    assert a.player.pos == 8000
    controller.set_playing("a", True)
    assert a.player.pos == 2000


def test_drift_correction_has_threshold_and_cooldown(rig, monkeypatch):
    owner, controller = rig
    a = owner.add("a", paused=False)
    b = owner.add("b")
    now = [10.0]
    monkeypatch.setattr("gridstudio.playback.time.monotonic", lambda: now[0])
    controller.join_group(["a", "b"])
    b.player.seeks.clear()
    now[0] += 1
    b.player.pos = 920
    controller.tick()
    assert not b.player.seeks
    b.player.pos = 800
    controller.tick()
    assert b.player.seeks == [1000]
    b.player.pos = 700
    controller.tick()
    assert b.player.seeks == [1000]
    now[0] += 0.5
    controller.tick()
    assert b.player.seeks == [1000, 1000]


def test_clear_markers_keeps_loop_enabled_and_rejects_invalid_ab(rig):
    owner, controller = rig
    a = owner.add("a")
    assert controller.set_loop("a", True, 1000, 3000)
    assert not controller.set_loop("a", True, 3000, 2000)
    assert not controller.set_loop("a", True, 1000, 20_000)
    assert controller.clear_loop("a")
    assert a.state.loop
    assert (a.state.loop_start_ms, a.state.loop_end_ms) == (0, None)


def test_set_a_and_b_capture_current_position_and_validate_order(rig):
    owner, controller = rig
    a = owner.add("a")
    assert controller.set_a("a")
    assert a.state.loop_start_ms == 1000
    assert not controller.set_b("a")
    a.player.pos = 2500
    assert controller.set_b("a")
    assert a.state.loop_end_ms == 2500
    a.player.pos = 3000
    assert controller.set_a("a")
    assert a.state.loop_end_ms is None


def test_percent_sync_maps_positions_rates_and_ab(rig):
    owner, controller = rig
    a = owner.add("a", duration=10_000, position=2500, paused=False)
    b = owner.add("b", duration=20_000)
    assert controller.join_group(["a", "b"], mode="percent")
    assert b.player.pos == 5000 and b.state.rate == 2
    controller.seek("b", 12_000)
    assert a.player.pos == 6000 and b.player.pos == 12_000
    assert controller.set_rate("b", 1)
    assert a.state.rate == 0.5 and b.state.rate == 1
    assert controller.set_loop("b", True, 4000, 8000)
    assert (a.state.loop_start_ms, a.state.loop_end_ms) == (2000, 4000)
    b.player.pos, a.player.pos = 8020, 4010
    controller.tick()
    assert (a.player.pos, b.player.pos) == (2000, 4000)


def test_percent_impossible_rate_rejected_without_changing_members(rig):
    owner, controller = rig
    a = owner.add("a", duration=1000)
    b = owner.add("b", duration=100_000)
    assert not controller.join_group(["a", "b"], mode="percent")
    assert a.state.sync_group == b.state.sync_group == ""
    assert owner.messages


def test_join_while_loading_preserves_master_and_deferred_actions(rig):
    owner, controller = rig
    a = owner.add("a", position=3500, paused=False)
    b = owner.add("b", position=7000)
    a._pending_restore = b._pending_restore = True
    controller.join_group(["a", "b"], leader_id="a")
    controller.seek("a", 4200)
    assert a.state.position_ms == b.state.position_ms == 4200
    b._pending_restore = False
    controller.media_ready("b")
    assert controller._leaders["1"] == "a"
    a._pending_restore = False
    a.player.pos = a.state.position_ms
    controller.media_ready("a")
    assert a.player.pos == b.player.pos == 4200
    assert a.player.playing and b.player.playing


def test_leave_group_and_removed_leader_do_not_break_other_players(rig):
    owner, controller = rig
    a, b, c = (owner.add(x) for x in "abc")
    controller.join_group(["a", "b", "c"])
    controller.leave_group(["c"])
    del owner.panes["a"]
    controller.tick()
    controller.seek("b", 4000)
    assert b.player.pos == 4000 and c.player.pos == 1000
    assert c.state.sync_group == "" and c.state.sync_offset_ms == 0


def test_deferred_percent_duration_selects_feasible_rates(rig):
    owner, controller = rig
    a = owner.add("a", duration=1000)
    b = owner.add("b", duration=0)
    b._pending_restore = True
    assert controller.join_group(["a", "b"], mode="percent")
    b.player.length = 40_000
    b._pending_restore = False
    controller.media_ready("b")
    assert a.state.rate == pytest.approx(0.2)
    assert b.state.rate == pytest.approx(8)


def test_deferred_impossible_percent_duration_leaves_new_member(rig):
    owner, controller = rig
    a = owner.add("a", duration=1000)
    b = owner.add("b", duration=0)
    b._pending_restore = True
    assert controller.join_group(["a", "b"], mode="percent")
    b.player.length = 100_000
    b._pending_restore = False
    controller.media_ready("b")
    assert a.state.sync_group == "1"
    assert b.state.sync_group == ""
    assert owner.messages


def test_reset_forgets_previous_workspace_playing_intent(rig):
    owner, controller = rig
    a = owner.add("a", paused=False)
    b = owner.add("b")
    controller.join_group(["a", "b"])
    assert controller._playing["1"]
    controller.reset()
    a.state.paused = b.state.paused = True
    a.player.pause()
    b.player.pause()
    controller.media_ready("a")
    assert not a.player.playing and not b.player.playing
    assert not controller._playing["1"]
