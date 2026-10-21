"""Playback coordination, independent of the window and its controls.

Every user action is applied directly to the media players.  Qt's asynchronous
status signals never turn into new user actions, which prevents seek/play signal
feedback.  The timer only handles A/B boundaries and meaningful playback drift.
"""

from __future__ import annotations

from .i18n import tr

import time
from contextlib import contextmanager

from PySide6.QtCore import QObject, QTimer, Qt
from PySide6.QtMultimedia import QMediaPlayer

from .media_commands import media_command


class PlaybackController(QObject):
    DRIFT_MS = 100
    SEEK_COOLDOWN = 0.45

    def __init__(self, owner):
        super().__init__(owner if isinstance(owner, QObject) else None)
        self.owner = owner
        self._leaders = {}
        self._playing = {}
        self._last_seek = {}
        self._wrap_wait = {}
        self._in_tick = False
        self._shutdown = False
        self._deferred_changes = None
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.tick)
        self.refresh_activity()

    def refresh_activity(self):
        """Poll only while controller-managed playback needs a clock.

        Whole-file loops without a sync group are handled by Qt. Desired
        playback state is already tracked here; checking it must not query or
        retain native media objects. Loading and disposed panes cannot advance
        until their lifecycle callback refreshes activity again.
        """
        if self._in_tick:
            return
        active = False
        if not self._shutdown:
            for pane in self.owner.panes.values():
                state = pane.state
                if (not state.source or getattr(pane, "_pending_restore", False)
                        or getattr(pane, "_disposed", False)):
                    continue
                if state.sync_group:
                    if self._playing.get(state.sync_group, not state.paused):
                        active = True
                        break
                elif (not state.paused and state.loop
                      and (state.loop_start_ms or state.loop_end_ms is not None)):
                    active = True
                    break
        if active != self.timer.isActive():
            self.timer.start() if active else self.timer.stop()

    def shutdown(self):
        """Keep disposal signals from restarting the clock during shutdown."""
        self._shutdown = True
        self.timer.stop()

    def reset(self):
        """Forget a previous workspace's leaders and pending playback intent."""
        self._leaders.clear()
        self._playing.clear()
        self._last_seek.clear()
        self._wrap_wait.clear()
        self.timer.stop()

    def _pane(self, pane_id):
        return self.owner.panes.get(pane_id)

    def _members(self, pane):
        group = pane.state.sync_group
        if not group:
            return [pane]
        return [p for p in self.owner.panes.values() if p.state.sync_group == group and p.state.source]

    @staticmethod
    def _duration(pane, durations=None):
        if durations is None:
            return pane.player.duration()
        key = id(pane)
        if key not in durations:
            durations[key] = pane.player.duration()
        return durations[key]

    @staticmethod
    def _ready(pane, *, durations=None):
        return (bool(pane.state.source) and not getattr(pane, "_pending_restore", False)
                and PlaybackController._duration(pane, durations) > 0)

    @staticmethod
    def _current(pane):
        return pane.state.position_ms if getattr(pane, "_pending_restore", False) else pane.player.position()

    @staticmethod
    def _percent(pane):
        return getattr(pane.state, "sync_mode", "time") == "percent" and bool(pane.state.sync_group)

    def _clock(self, pane, position=None, *, durations=None):
        position = self._current(pane) if position is None else position
        if self._percent(pane):
            duration = self._duration(pane, durations)
            return position / duration if duration > 0 else None
        return position - pane.state.sync_offset_ms

    def _position(self, pane, clock, *, durations=None):
        if self._percent(pane):
            return round(clock * self._duration(pane, durations))
        return round(clock + pane.state.sync_offset_ms)

    def _changed(self, panes):
        if self._deferred_changes is not None:
            self._deferred_changes.update((p.state.id, p) for p in panes)
            return
        for pane in panes:
            pane.apply_state()
        refresh = getattr(self.owner, "refresh_inspector", None)
        if refresh is not None:
            refresh()
        self.refresh_activity()

    @contextmanager
    def _batch_changes(self):
        """Apply related loop/rate edits together before native transport."""
        if self._deferred_changes is not None:
            yield
            return
        self._deferred_changes = {}
        try:
            yield
        finally:
            panes = list(self._deferred_changes.values())
            self._deferred_changes = None
            if panes:
                self._changed(panes)

    def _notify(self, message):
        notify = getattr(self.owner, "notify", None)
        if notify is not None:
            notify(message)

    def _lead(self, pane):
        group = pane.state.sync_group
        if group:
            self._leaders[group] = pane.state.id

    def _seek_one(self, pane, position, *, force=True, durations=None, current_position=None):
        position = max(0, round(position))
        duration = self._duration(pane, durations)
        if duration > 0:
            position = min(position, duration)
        pane.state.position_ms = position
        if getattr(pane, "_pending_restore", False):
            return
        # Joining/pausing a group often asks the leader (and already-aligned
        # copies) to seek to the position they already display. Avoid restarting
        # identical FFmpeg seeks, especially with multiple paused decoders.
        if (pane.player.position() if current_position is None else current_position) == position:
            return
        now = time.monotonic()
        if not force and now - self._last_seek.get(pane.state.id, -100) < self.SEEK_COOLDOWN:
            return
        self._last_seek[pane.state.id] = now
        media_command(pane.player, "setPosition", position)

    def _play_one(self, pane, playing, *, playback_state=None):
        pane.state.paused = not playing
        if getattr(pane, "_pending_restore", False) or not pane.state.source:
            return
        state = pane.player.playbackState() if playback_state is None else playback_state
        if playing:
            if state != QMediaPlayer.PlaybackState.PlayingState:
                media_command(pane.player, "play")
        elif state == QMediaPlayer.PlaybackState.PlayingState:
            media_command(pane.player, "pause")

    def _group_leader(self, members, *, durations=None):
        group = members[0].state.sync_group
        leader = self._pane(self._leaders.get(group))
        if leader not in members:
            leader = next((p for p in members if self._ready(p, durations=durations)), members[0])
            self._leaders[group] = leader.state.id
        return leader

    def _bounds(self, members, leader, *, durations=None):
        """Intersection in group time; unavailable media cannot supply a bound."""
        starts, ends = [], []
        for pane in members:
            if not self._ready(pane, durations=durations):
                continue
            starts.append(self._clock(pane, 0, durations=durations))
            ends.append(self._clock(pane, self._duration(pane, durations), durations=durations))
            if leader.state.loop and pane.state.loop:
                starts.append(self._clock(pane, pane.state.loop_start_ms, durations=durations))
                if pane.state.loop_end_ms is not None:
                    ends.append(self._clock(pane, pane.state.loop_end_ms, durations=durations))
        if not starts or not ends:
            return None
        start, end = max(starts), min(ends)
        return (start, end) if end > start else None

    def _align(self, members, leader, *, clock=None, force=True, durations=None):
        clock = self._clock(leader, durations=durations) if clock is None else clock
        if clock is None:
            return
        for pane in members:
            if self._percent(pane) and self._duration(pane, durations) <= 0:
                continue
            self._seek_one(pane, self._position(pane, clock, durations=durations),
                           force=force, durations=durations)

    def set_playing(self, pane_id, playing):
        pane = self._pane(pane_id)
        if pane is None:
            return
        playing = bool(playing)
        self._lead(pane)
        members = self._members(pane)
        if pane.state.sync_group:
            self._playing[pane.state.sync_group] = playing
        durations = {}
        clock = original_clock = self._clock(pane, durations=durations)
        bounds = self._bounds(members, pane, durations=durations)
        if playing and clock is not None and bounds is not None:
            start, end = bounds
            # Restarting an ended group uses its common beginning.
            if clock < start or clock >= end:
                clock = start
        if pane.state.sync_group and clock is not None:
            self._align(members, pane, clock=clock, durations=durations)
        elif playing and bounds is not None and clock is not None and original_clock != clock:
            self._seek_one(pane, self._position(pane, clock, durations=durations), durations=durations)
        for member in members:
            self._play_one(member, playing)
        self.refresh_activity()

    def seek(self, pane_id, position_ms):
        pane = self._pane(pane_id)
        if pane is None:
            return
        self._lead(pane)
        position_ms = max(0, round(position_ms))
        if not pane.state.sync_group:
            self._seek_one(pane, position_ms)
            return
        durations = {}
        clock = self._clock(pane, position_ms, durations=durations)
        if clock is None:
            self._seek_one(pane, position_ms)
            return
        members = self._members(pane)
        # Seeks may inspect any part of an A/B video while paused.  Source
        # boundaries still constrain the shared clock for signed offsets.
        starts, ends = [], []
        for member in members:
            if self._ready(member, durations=durations):
                starts.append(self._clock(member, 0, durations=durations))
                ends.append(self._clock(member, self._duration(member, durations), durations=durations))
        if starts and ends and max(starts) <= min(ends):
            clock = max(max(starts), min(clock, min(ends)))
        self._align(members, pane, clock=clock, durations=durations)

    def _rates(self, members, leader, rate):
        values = {}
        durations = {}
        leader_duration = self._duration(leader, durations) if self._percent(leader) else 0
        for pane in members:
            value = float(rate)
            if leader_duration > 0:
                duration = self._duration(pane, durations)
                if duration > 0:
                    value *= duration / leader_duration
            if not 0.1 - 1e-9 <= value <= 8.0 + 1e-9:
                return None
            values[pane.state.id] = min(8.0, max(0.1, value))
        return values

    def set_rate(self, pane_id, rate):
        pane = self._pane(pane_id)
        if pane is None or not 0.1 <= rate <= 8.0:
            return False
        members = self._members(pane)
        rates = self._rates(members, pane, rate)
        if rates is None:
            self._notify(tr('这些视频时长差异过大，所选速度无法保持百分比同步（支持 0.1–8 倍速）'))
            return False
        self._lead(pane)
        for member in members:
            member.state.rate = rates[member.state.id]
        self._changed(members)
        return True

    def join_group(self, pane_ids, group="1", leader_id=None, preserve_offsets=False, mode="time"):
        if group not in ("1", "2", "3", "4") or mode not in ("time", "percent"):
            return False
        selected = [self._pane(i) for i in dict.fromkeys(pane_ids)]
        selected = [p for p in selected if p is not None and p.state.source]
        if not selected:
            return False
        existing = [p for p in self.owner.panes.values() if p.state.sync_group == group and p.state.source]
        existing_ids = {p.state.id for p in existing}
        selected_ids = {p.state.id for p in selected}
        members = existing + [p for p in selected if p.state.id not in existing_ids]
        leader = self._pane(leader_id)
        if leader not in members:
            leader = existing[0] if existing else selected[0]
        durations = {}
        leader_duration = self._duration(leader, durations) if mode == "percent" else 0
        if leader_duration > 0:
            lengths = [self._duration(p, durations) for p in members]
            lengths = [d for d in lengths if d > 0]
            minimum = max(0.1 * leader_duration / d for d in lengths)
            maximum = min(8.0 * leader_duration / d for d in lengths)
            if minimum > maximum:
                self._notify(tr('这些视频时长差异过大，无法在 0.1–8 倍速内保持百分比同步'))
                return False
            leader.state.rate = min(maximum, max(minimum, leader.state.rate))
        leader_position = self._current(leader)
        old_leader_offset = leader.state.sync_offset_ms if leader.state.id in existing_ids else 0
        clock = leader_position - old_leader_offset
        for pane in members:
            pane.state.sync_group = group
            pane.state.sync_mode = mode
            if mode == "percent":
                pane.state.sync_offset_ms = 0
            elif pane.state.id in selected_ids:
                pane.state.sync_offset_ms = self._current(pane) - clock if preserve_offsets else old_leader_offset
        self._leaders[group] = leader.state.id
        self._playing[group] = not leader.state.paused
        # Setting loop settings through the same mapping keeps saved sessions
        # and joins consistent, including percent groups of unequal lengths.
        with self._batch_changes():
            self.set_loop(leader.state.id, leader.state.loop,
                          leader.state.loop_start_ms, leader.state.loop_end_ms)
            self.set_rate(leader.state.id, leader.state.rate)
            for pane in members:
                pane.state.paused = not self._playing[group]
            self._changed(members)
        self._align(members, leader, durations=durations)
        for pane in members:
            self._play_one(pane, self._playing[group])
        self.refresh_activity()
        return True

    def leave_group(self, pane_ids):
        panes = [self._pane(i) for i in pane_ids]
        panes = [p for p in panes if p is not None]
        for pane in panes:
            pane.state.sync_group = ""
            pane.state.sync_offset_ms = 0
            pane.state.sync_mode = "time"
        self._changed(panes)

    def set_loop(self, pane_id, enabled, start_ms=0, end_ms=None, propagate=True):
        pane = self._pane(pane_id)
        if pane is None or type(start_ms) is not int or start_ms < 0:
            return False
        if end_ms is not None and (type(end_ms) is not int or end_ms <= start_ms):
            return False
        durations = {}
        duration = self._duration(pane, durations)
        if duration > 0 and (start_ms >= duration or (end_ms is not None and end_ms > duration)):
            return False
        members = self._members(pane) if propagate else [pane]
        start_clock = self._clock(pane, start_ms, durations=durations)
        end_clock = self._clock(pane, end_ms, durations=durations) if end_ms is not None else None
        settings = []
        for member in members:
            if member is pane or start_clock is None or (self._percent(member) and self._duration(member, durations) <= 0):
                start, end = start_ms, end_ms
            else:
                start = max(0, self._position(member, start_clock, durations=durations))
                end = self._position(member, end_clock, durations=durations) if end_clock is not None else None
            member_duration = self._duration(member, durations)
            if member_duration > 0:
                start = min(start, max(0, member_duration - 1))
                end = min(end, member_duration) if end is not None else None
            if end is not None and end <= start:
                return False
            settings.append((member, start, end))
        self._lead(pane)
        for member, start, end in settings:
            member.state.loop = bool(enabled)
            member.state.loop_start_ms = start
            member.state.loop_end_ms = end
        self._changed(members)
        return True

    def set_a(self, pane_id):
        pane = self._pane(pane_id)
        if pane is None:
            return False
        position = self._current(pane)
        end = pane.state.loop_end_ms
        if end is not None and end <= position:
            end = None
        return self.set_loop(pane_id, True, position, end)

    def set_b(self, pane_id):
        pane = self._pane(pane_id)
        if pane is None:
            return False
        return self.set_loop(pane_id, True, pane.state.loop_start_ms, self._current(pane))

    def clear_loop(self, pane_id):
        pane = self._pane(pane_id)
        if pane is None:
            return False
        return self.set_loop(pane_id, pane.state.loop, 0, None)

    def media_ready(self, pane_id):
        if self._shutdown:
            return
        self.refresh_activity()
        pane = self._pane(pane_id)
        if pane is None or not pane.state.sync_group:
            return
        members = self._members(pane)
        durations = {}
        leader = self._group_leader(members, durations=durations)
        group = pane.state.sync_group
        playing = self._playing.setdefault(group, not leader.state.paused)
        if not self._ready(leader, durations=durations):
            return
        if self._percent(leader):
            lengths = [self._duration(p, durations) for p in members if self._ready(p, durations=durations)]
            leader_duration = self._duration(leader, durations)
            minimum = max(0.1 * leader_duration / d for d in lengths)
            maximum = min(8.0 * leader_duration / d for d in lengths)
            if minimum > maximum:
                self.leave_group([pane_id])
                self._notify(tr('视频时长差异过大，刚载入的视频已退出百分比同步（支持 0.1–8 倍速）'))
                return
            leader.state.rate = min(maximum, max(minimum, leader.state.rate))
        self._align(members, leader, durations=durations)
        with self._batch_changes():
            self.set_loop(leader.state.id, leader.state.loop, leader.state.loop_start_ms, leader.state.loop_end_ms)
            self.set_rate(leader.state.id, leader.state.rate)
            for member in members:
                member.state.paused = not playing
        for member in members:
            self._play_one(member, playing)
        self.refresh_activity()

    def _wrap_allowed(self, key, outside):
        if not outside:
            self._wrap_wait.pop(key, None)
            return True
        now = time.monotonic()
        if now - self._wrap_wait.get(key, -100) < 0.15:
            return False
        self._wrap_wait[key] = now
        return True

    def tick(self):
        if self._shutdown or self._in_tick:
            return
        self._in_tick = True
        try:
            groups = {}
            # Durations are stable for one synchronous coordination pass. Do
            # not keep them between ticks: load completion can change them.
            durations = {}
            for pane in list(self.owner.panes.values()):
                if not pane.state.source or getattr(pane, "_disposed", False):
                    continue
                if pane.state.sync_group:
                    groups.setdefault(pane.state.sync_group, []).append(pane)
                elif (pane.state.loop and (pane.state.loop_end_ms is not None or pane.state.loop_start_ms)
                      and self._ready(pane, durations=durations)):
                    end = pane.state.loop_end_ms or self._duration(pane, durations)
                    if end <= pane.state.loop_start_ms:
                        continue
                    # A paused seek is allowed to inspect outside A/B.
                    playback_state = pane.player.playbackState()
                    playing = playback_state == QMediaPlayer.PlaybackState.PlayingState
                    if not playing and pane.state.paused:
                        continue
                    ended = not playing and pane.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia
                    position = pane.player.position()
                    outside = position >= end or position < pane.state.loop_start_ms
                    can_wrap = self._wrap_allowed(pane.state.id, outside)
                    if (playing or (ended and not pane.state.paused)) and outside and can_wrap:
                        self._seek_one(pane, pane.state.loop_start_ms,
                                       durations=durations, current_position=position)
                        self._play_one(pane, True)
            for group, members in groups.items():
                # Explicit actions already align paused groups. Native queries
                # here would add work without changing any player.
                if self._playing.get(group) is False:
                    continue
                leader = self._group_leader(members, durations=durations)
                if not self._ready(leader, durations=durations):
                    continue
                playing = self._playing.setdefault(group, not leader.state.paused)
                if not playing:
                    continue
                clock = self._clock(leader, durations=durations)
                bounds = self._bounds(members, leader, durations=durations)
                if clock is None or bounds is None:
                    continue
                start, end = bounds
                ready = [p for p in members if self._ready(p, durations=durations)]
                ended = any(p.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia for p in ready)
                outside = clock >= end or clock < start or ended
                can_wrap = self._wrap_allowed("group:" + group, outside)
                if playing and outside and can_wrap:
                    if leader.state.loop:
                        self._align(members, leader, clock=start, durations=durations)
                        for pane in members:
                            self._play_one(pane, True)
                    else:
                        self._playing[group] = False
                        for pane in members:
                            self._play_one(pane, False)
                        self._align(members, leader, clock=end, durations=durations)
                    continue
                if outside:
                    continue
                for pane in ready:
                    if pane is leader:
                        continue
                    target = self._position(pane, clock, durations=durations)
                    position = pane.player.position()
                    if abs(position - target) > self.DRIFT_MS:
                        self._seek_one(pane, target, force=False,
                                       durations=durations, current_position=position)
                    playback_state = pane.player.playbackState()
                    if playback_state != QMediaPlayer.PlaybackState.PlayingState:
                        self._play_one(pane, True, playback_state=playback_state)
        finally:
            self._in_tick = False
            self.refresh_activity()
