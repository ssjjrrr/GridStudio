"""Offscreen integration checks for pane ownership, layout, and workspace state.

These deliberately run deferred deletes: a pane can look alive immediately after
reparenting yet be destroyed on the next Qt event-loop turn.
"""

import json
import os
from contextlib import contextmanager
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QMimeData, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QEnterEvent
from PySide6.QtTest import QTest
from scripts.qt_test_support import qt_wait
from PySide6.QtWidgets import QApplication, QMessageBox, QSplitter

from gridstudio.app import MainWindow, PANE_MIME, STYLE
from gridstudio.model import leaf_ids


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    yield app


def drain_events(app):
    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    qt_wait(1)


def move_pointer(widget, position, delay=5):
    """Deliver native-window mouse input without requiring a desktop cursor warp.

    Qt's QWidget overload only warps QCursor for a button-free move. Desktop
    services may reject that OS operation without delivering any Qt event.
    The QWindow overload goes through Qt's QPA event delivery and hit testing.
    Offscreen checks retain their existing synthetic platform cursor behavior.
    """
    if QApplication.platformName() in ("offscreen", "minimal"):
        QTest.mouseMove(widget, position, delay)
    else:
        window = widget.window()
        pointer = getattr(window, "_test_native_pointer", None)
        if pointer is not None:
            pointer.position = window.windowHandle().mapToGlobal(widget.mapTo(window, position))
        QTest.mouseMove(window.windowHandle(), widget.mapTo(window, position), delay)


def _pointer_button(action, widget, button, modifier=Qt.KeyboardModifier.NoModifier, pos=QPoint(), delay=-1):
    method = getattr(QTest, action)
    if QApplication.platformName() in ("offscreen", "minimal"):
        method(widget, button, modifier, pos, delay)
    else:
        window = widget.window()
        local = widget.rect().center() if pos.isNull() else pos
        pointer = getattr(window, "_test_native_pointer", None)
        if pointer is not None:
            pointer.position = window.windowHandle().mapToGlobal(widget.mapTo(window, local))
        method(window.windowHandle(), button, modifier, widget.mapTo(window, local), delay)


def press_pointer(widget, button, modifier=Qt.KeyboardModifier.NoModifier, pos=QPoint(), delay=-1):
    _pointer_button("mousePress", widget, button, modifier, pos, delay)


def release_pointer(widget, button, modifier=Qt.KeyboardModifier.NoModifier, pos=QPoint(), delay=-1):
    _pointer_button("mouseRelease", widget, button, modifier, pos, delay)


def click_pointer(widget, button, modifier=Qt.KeyboardModifier.NoModifier, pos=QPoint(), delay=-1):
    _pointer_button("mouseClick", widget, button, modifier, pos, delay)


@contextmanager
def native_pointer_driver(window, app):
    """Keep desktop queries consistent with Qt's injected native-window input.

    QTest's QWindow overload dispatches QPA events without warping the physical
    desktop pointer. This adapter supplies only that external desktop state to
    the hover code. Actual Qt window dispatch, child hit testing (including
    masks), Enter/Leave, timers and hover behavior remain under test. These are
    native-window synthetic-input checks, not OS cursor-permission checks.
    """
    if app.platformName() in ("offscreen", "minimal"):
        yield
        return
    from gridstudio import hover_controls

    class Pointer(QObject):
        def __init__(self):
            super().__init__()
            # Do not inherit whichever desktop pixel the preceding test (or
            # the CI desktop service) happened to leave the physical cursor on.
            self.position = window.mapToGlobal(QPoint(-32, -32))

        def eventFilter(self, watched, event):
            if event.type() in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
                                QEvent.Type.MouseButtonRelease, QEvent.Type.MouseButtonDblClick):
                # The test driver owns this logical desktop. Ignore unrelated
                # physical cursor traffic instead of mixing two input streams.
                if event.globalPosition().toPoint() != self.position:
                    return True
            elif event.type() == QEvent.Type.Enter and hasattr(event, "globalPosition"):
                # Qt synthesizes Enter when a child appears/disappears. On a
                # native backend that event can use the OS cursor rather than
                # the QWindow-injected position. Keep this one external input
                # coordinate consistent with the logical desktop adapter.
                if event.globalPosition().toPoint() != self.position:
                    local = watched.mapFromGlobal(self.position)
                    if not (0 <= local.x() < watched.width() and 0 <= local.y() < watched.height()):
                        return True
                    normalized = QEnterEvent(QPointF(local), QPointF(window.mapFromGlobal(self.position)),
                                             QPointF(self.position))
                    QCoreApplication.sendEvent(watched, normalized)
                    return True
            return False

        def pos(self):
            return QPoint(self.position)

        def widgetAt(self, point):
            local = window.mapFromGlobal(point)
            if not window.isVisible() or not window.rect().contains(local):
                return None
            return window.childAt(local) or window

    pointer = Pointer()
    window._test_native_pointer = pointer
    app.installEventFilter(pointer)
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(hover_controls, "QCursor", pointer)
            patch.setattr(hover_controls, "QApplication", pointer)
            yield
    finally:
        app.removeEventFilter(pointer)
        del window._test_native_pointer
        pointer.deleteLater()


@pytest.fixture
def window(qapp, monkeypatch):
    def unexpected_modal(_parent, title, message, *_args, **_kwargs):
        pytest.fail(f"Unexpected modal dialog: {title}: {message}")

    monkeypatch.setattr(QMessageBox, "warning", unexpected_modal)
    win = MainWindow()
    # These regression checks exercise the original splitter layout explicitly;
    # default free-canvas behavior is covered in test_free_canvas.py.
    win.set_layout_mode("grid")
    win.show()
    drain_events(qapp)
    yield win
    # Restore patched bound Qt methods while their native objects still exist.
    monkeypatch.undo()
    if shiboken6.isValid(win):
        win.close()
        win.deleteLater()
    drain_events(qapp)


def assert_live_panes(win, refs=None, *, visible=True):
    assert set(leaf_ids(win.tree)) == set(win.panes)
    assert len(leaf_ids(win.tree)) == len(win.panes)
    for pid, pane in (refs or win.panes).items():
        assert win.panes[pid] is pane
        assert shiboken6.isValid(pane), f"Pane {pid} was deleted during layout rebuild"
        assert shiboken6.isValid(pane.player)
        assert shiboken6.isValid(pane.canvas)
        if visible:
            assert pane.isVisible(), f"Pane {pid} stayed hidden after restoring layout"


def reduce_to_one(win, app):
    keep = leaf_ids(win.tree)[0]
    for pid in list(win.panes):
        if pid != keep:
            win.remove_pane(pid)
            drain_events(app)
    assert win.root_widget is win.panes[keep]
    return keep


def apply_preset(win, key):
    index = win.layout_combo.findData(key)
    assert index >= 0
    win.layout_combo.setCurrentIndex(index)
    win.preset_selected(index)


def test_main_window_starts_with_one_live_pane(window):
    assert len(window.panes) == 1
    assert window.active() is window.panes[window.active_id]
    assert window.root_widget is window.active()
    assert_live_panes(window)


@pytest.mark.parametrize("preset", ["columns", "rows", "grid4", "grid9", "focus-left", "focus-top"])
def test_presets_preserve_existing_pane_and_player_objects(window, qapp, preset):
    refs = dict(window.panes)
    players = {pid: pane.player for pid, pane in refs.items()}
    apply_preset(window, preset)
    drain_events(qapp)
    assert_live_panes(window, refs)
    assert all(window.panes[pid].player is player for pid, player in players.items())
    expected = {"grid4": 4, "grid9": 9, "columns": 2, "rows": 2,
                "focus-left": 3, "focus-top": 3}
    assert len(window.panes) == expected[preset]


@pytest.mark.parametrize("axis", ["horizontal", "vertical"])
def test_split_blank_pane_preserves_original(window, qapp, axis):
    original_id = window.active_id
    original = window.active()
    old_ids = set(window.panes)
    window.add_blank(original_id, axis)
    drain_events(qapp)
    assert len(window.panes) == len(old_ids) + 1
    assert window.panes[original_id] is original
    assert window.active_id not in old_ids
    assert window.active().state.source == ""
    assert_live_panes(window)


def test_duplicate_copies_transforms_and_survives_original_close(window, qapp):
    original = window.active()
    original.state.crop = (0.1, 0.2, 0.6, 0.5)
    original.state.rotation = 270
    original.state.flip_h = True
    original.state.flip_v = True
    original.state.rate = 1.5
    original.state.volume = 0.37
    original.state.muted = False
    original.state.loop = True
    original.apply_state()
    old_ids = set(window.panes)

    window.duplicate(original.state.id, "vertical")
    drain_events(qapp)
    duplicate = window.active()
    assert duplicate.state.id not in old_ids
    assert duplicate is not original
    assert duplicate.player is not original.player
    for name in ("source", "crop", "rotation", "flip_h", "flip_v", "rate", "volume", "muted", "loop"):
        assert getattr(duplicate.state, name) == getattr(original.state, name)

    duplicate.state.crop = (0.2, 0.1, 0.3, 0.7)
    duplicate.state.rotation = 90
    duplicate.apply_state()
    assert original.state.crop == (0.1, 0.2, 0.6, 0.5)
    assert original.state.rotation == 270
    window.remove_pane(original.state.id)
    drain_events(qapp)
    assert shiboken6.isValid(duplicate)
    assert window.panes[duplicate.state.id] is duplicate
    assert duplicate.state.crop == (0.2, 0.1, 0.3, 0.7)
    assert_live_panes(window)


def test_repeated_focus_restore_keeps_every_pane_alive_and_visible(window, qapp):
    apply_preset(window, "grid4")
    drain_events(qapp)
    refs = dict(window.panes)
    for pane_id in list(refs) * 3:
        window.toggle_focus(pane_id)
        drain_events(qapp)
        assert window.focus_id == pane_id
        assert window.root_widget is refs[pane_id]
        assert refs[pane_id].isVisible()
        assert_live_panes(window, refs, visible=False)
        window.toggle_focus(pane_id)
        drain_events(qapp)
        assert window.focus_id is None
        assert_live_panes(window, refs)


def test_single_pane_root_survives_rebuild_split_focus_and_close(window, qapp):
    pane_id = reduce_to_one(window, qapp)
    pane = window.panes[pane_id]
    for _ in range(4):
        window.rebuild()
        drain_events(qapp)
        assert_live_panes(window, {pane_id: pane})
        window.toggle_focus(pane_id)
        drain_events(qapp)
        window.toggle_focus(pane_id)
        drain_events(qapp)
        window.add_blank(pane_id)
        drain_events(qapp)
        new_id = window.active_id
        assert_live_panes(window, {pane_id: pane})
        window.remove_pane(new_id)
        drain_events(qapp)
        assert window.root_widget is pane
        assert_live_panes(window, {pane_id: pane})
    window.remove_pane(pane_id)
    drain_events(qapp)
    assert len(window.panes) == 1
    assert pane_id not in window.panes
    assert_live_panes(window)


@pytest.mark.parametrize("surface", ["pane", "canvas"])
def test_native_pane_drop_swaps_layout_without_replacing_players(window, qapp, surface):
    window.add_blank()
    drain_events(qapp)
    refs = dict(window.panes)
    before = leaf_ids(window.tree)
    source_id, destination_id = before[0], before[-1]
    destination_pane = window.panes[destination_id]
    destination = destination_pane if surface == "pane" else destination_pane.canvas.viewport()
    mime = QMimeData()
    mime.setData(PANE_MIME, source_id.encode("utf-8"))
    enter = QDragEnterEvent(QPoint(15, 15), Qt.DropAction.MoveAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(destination, enter)
    assert enter.isAccepted()
    drop = QDropEvent(QPointF(15, 15), Qt.DropAction.MoveAction, mime,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(destination, drop)
    assert drop.isAccepted()
    drain_events(qapp)
    after = leaf_ids(window.tree)
    expected = [destination_id if pid == source_id else source_id if pid == destination_id else pid for pid in before]
    assert after == expected
    assert_live_panes(window, refs)


def test_canvas_mouse_crop_updates_pane_model_and_selection_cancels_crop(window, qapp):
    window.add_blank()
    drain_events(qapp)
    pane = window.active()
    canvas = pane.canvas
    canvas.set_has_media(True)
    pane.state.rotation = 90
    pane.state.flip_h = True
    pane.apply_state()
    canvas.start_crop()
    drain_events(qapp)
    size = canvas.source_size()
    start = canvas.mapFromScene(QPointF(size.width() * 0.2, size.height() * 0.25))
    end = canvas.mapFromScene(QPointF(size.width() * 0.7, size.height() * 0.75))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    drain_events(qapp)
    assert not canvas.crop_active
    assert pane.state.crop == pytest.approx((0.2, 0.25, 0.5, 0.5), abs=0.015)
    assert pane.state.rotation == 90
    assert pane.state.flip_h is True
    canvas.start_crop()
    other_id = next(pid for pid in window.panes if pid != pane.state.id)
    window.select(other_id)
    assert not canvas.crop_active


def test_splitter_capture_and_workspace_roundtrip(window, qapp, tmp_path):
    first_id = reduce_to_one(window, qapp)
    window.add_blank(first_id, "horizontal")
    drain_events(qapp)
    splitter, node = window._split_nodes[-1]
    splitter.setSizes([700, 300])
    drain_events(qapp)
    window.capture_sizes()
    sizes = splitter.sizes()
    assert node["sizes"] == sizes
    assert sizes[0] > sizes[1] > 0
    expected_ratio = sizes[0] / sum(sizes)
    first = window.panes[first_id]
    first.state.crop = (0.05, 0.1, 0.7, 0.8)
    first.state.rotation = 90
    first.state.flip_h = True
    first.apply_state()
    pane_ids = leaf_ids(window.tree)
    path = tmp_path / "layout.gstudio"
    assert window.save_session(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved["panes"]) == 2

    window.add_blank()
    drain_events(qapp)
    assert window.load_session(path)
    drain_events(qapp)
    assert leaf_ids(window.tree) == pane_ids
    assert window.panes[first_id].state.crop == (0.05, 0.1, 0.7, 0.8)
    assert window.panes[first_id].state.rotation == 90
    assert window.panes[first_id].state.flip_h is True
    restored, _ = window._split_nodes[-1]
    restored_sizes = restored.sizes()
    assert restored_sizes[0] / sum(restored_sizes) == pytest.approx(expected_ratio, abs=0.025)
    assert_live_panes(window)


def test_workspace_existing_media_path_roundtrip_when_fixture_available(window, qapp, tmp_path):
    sample = Path(__file__).parent / "fixtures" / "sample.mp4"
    if not sample.is_file():
        pytest.skip("Generated sample.mp4 is not available")
    pane = window.active()
    pane.state.source = str(sample.resolve())
    pane.state.paused = True
    pane.load_source()
    drain_events(qapp)
    path = tmp_path / "media.gstudio"
    assert window.save_session(path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    stored = next(s for s in saved["panes"] if s["id"] == pane.state.id)
    assert (path.parent / stored["source"]).resolve() == sample.resolve()
    assert window.load_session(path)
    drain_events(qapp)
    assert window.panes[pane.state.id].state.source == str(sample.resolve())
    assert_live_panes(window)
