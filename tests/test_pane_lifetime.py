"""Live video widgets stay inside one native window while layouts change."""

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QApplication, QMessageBox

from gridstudio.app import MainWindow, VideoPane
from test_app import drain_events, qapp


class PaneEvents(QObject):
    def __init__(self):
        super().__init__()
        self.events = []

    def eventFilter(self, watched, event):
        if isinstance(watched, VideoPane) and event.type() in (QEvent.Type.Show, QEvent.Type.ParentChange):
            self.events.append({
                "event": event.type(),
                "pane": watched,
                "parentless": watched.parent() is None,
                "window": watched.isWindow(),
                "visible": watched.isVisible(),
                "native_window": watched.windowHandle() is not None,
            })
        return False

    def assert_no_detached_surfaces(self):
        assert self.events, "The audit must observe actual Qt parenting/show events"
        invalid = [item for item in self.events if item["parentless"] or item["window"]]
        assert not invalid, invalid
        visible_native = [item for item in self.events
                          if item["event"] == QEvent.Type.Show and item["native_window"]]
        assert not visible_native, visible_native


@pytest.fixture
def lifetime_window(qapp, monkeypatch):
    def unexpected_modal(_parent, title, message, *_args, **_kwargs):
        pytest.fail(f"Unexpected modal dialog: {title}: {message}")

    monkeypatch.setattr(QMessageBox, "warning", unexpected_modal)
    audit = PaneEvents()
    qapp.installEventFilter(audit)
    win = MainWindow()
    win.show()
    drain_events(qapp)
    yield win, audit
    monkeypatch.undo()
    # Ignore Qt's final QObject destruction; the invariant concerns live panes.
    qapp.removeEventFilter(audit)
    if shiboken6.isValid(win):
        win.close()
        win.deleteLater()
    drain_events(qapp)


def assert_embedded(win):
    for pane in win.panes.values():
        assert pane.parent() is not None
        assert not pane.isWindow()
        assert pane.window() is win
        assert pane.windowHandle() is None


def test_live_panes_never_show_as_parentless_native_windows_during_rebuilds(lifetime_window, qapp):
    win, audit = lifetime_window
    win.add_blank()
    win.add_blank()
    drain_events(qapp)
    panes = tuple(win.panes.values())
    identities = {p.state.id: (p, p.player, p.canvas.video_item) for p in panes}
    assert win.pane_parking.parent() is win
    assert win.pane_parking.isHidden()
    for index in range(4):
        win.set_clean_mode(bool(index % 2))
        win.set_layout_mode("grid")
        drain_events(qapp)
        assert_embedded(win)
        win.toggle_focus(panes[index % len(panes)].state.id)
        drain_events(qapp)
        assert_embedded(win)
        win.toggle_focus()
        drain_events(qapp)
        win.set_layout_mode("canvas")
        drain_events(qapp)
        assert_embedded(win)
        win.toggle_focus(panes[(index + 1) % len(panes)].state.id)
        drain_events(qapp)
        win.toggle_focus()
        drain_events(qapp)
        assert_embedded(win)
        assert identities == {p.state.id: (p, p.player, p.canvas.video_item)
                              for p in win.panes.values()}
    audit.assert_no_detached_surfaces()


@pytest.mark.parametrize("layout_mode", ["canvas", "grid"])
def test_focus_keeps_siblings_hidden_in_parking_and_restores_same_players(lifetime_window, qapp, layout_mode):
    win, audit = lifetime_window
    win.add_blank()
    win.add_blank()
    win.set_layout_mode(layout_mode)
    drain_events(qapp)
    panes = tuple(win.panes.values())
    focus = panes[1]
    players = {p.state.id: p.player for p in panes}
    win.toggle_focus(focus.state.id)
    drain_events(qapp)
    assert win.focus_id == focus.state.id
    assert focus.parent() is win.stage
    assert focus.isVisible()
    for sibling in panes:
        if sibling is not focus:
            assert sibling.parent() is win.pane_parking
            assert not sibling.isVisible()
    assert_embedded(win)
    win.toggle_focus()
    drain_events(qapp)
    assert win.focus_id is None
    assert all(p.isVisible() for p in panes)
    assert all(p.player is players[p.state.id] for p in panes)
    assert_embedded(win)
    audit.assert_no_detached_surfaces()


def test_duplicate_and_removal_keep_remaining_live_layers_inside_window(lifetime_window, qapp):
    win, audit = lifetime_window
    original = win.active()
    original_player = original.player
    for _ in range(3):
        win.duplicate(original.state.id)
        duplicate = win.active()
        drain_events(qapp)
        assert duplicate.player is not original_player
        assert_embedded(win)
        win.remove_pane(duplicate.state.id)
        drain_events(qapp)
        assert win.panes[original.state.id] is original
        assert original.player is original_player
        assert_embedded(win)
    audit.assert_no_detached_surfaces()


def test_queued_media_notifications_do_not_touch_controls_after_pane_removal(lifetime_window, qapp, monkeypatch):
    win, _ = lifetime_window
    pane = win.active()
    hover = pane.hover_controls
    calls = []
    # Restore Python attributes before DeferredDelete destroys their Qt owners.
    with monkeypatch.context() as patch:
        for target, method in ((pane.timeline, "setValue"), (pane.timeline, "setRange"),
                               (pane.play_button, "setIcon"), (hover.bar, "set_media"),
                               (hover.play_button, "setIcon"), (hover.mute_button, "setIcon"),
                               (hover.volume_slider, "setValue")):
            original = getattr(target, method)

            def record(*args, original=original, method=method, **kwargs):
                calls.append(method)
                return original(*args, **kwargs)

            patch.setattr(target, method, record)
        pane.player.positionChanged.emit(3000)
        pane.player.durationChanged.emit(12000)
        pane.player.playbackStateChanged.emit(QMediaPlayer.PlaybackState.PlayingState)
        pane.audio.volumeChanged.emit(.7)
        pane.audio.mutedChanged.emit(False)
        assert calls == [], "Media notifications must not reenter widgets synchronously"
        win.remove_pane(pane.state.id)
        assert pane._disposed and hover._disposed
        calls.clear()
        # Deliver queued slots while the disposed widgets still exist, then
        # let their normal deferred destruction happen after spies are restored.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.MetaCall)
        assert shiboken6.isValid(pane)
        assert calls == []
    drain_events(qapp)
    assert not shiboken6.isValid(pane)

