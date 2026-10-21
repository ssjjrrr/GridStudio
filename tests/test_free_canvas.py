"""Free placement, resizing and composited stacking through the actual Qt UI."""

import json

import pytest
import shiboken6
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDoubleSpinBox, QMessageBox

from gridstudio.app import MainWindow
from test_app import drain_events, qapp
from test_media import current_frame, load_pane, sample_video, wait_ready, wait_until
from test_seamless import feed_solid, matches


@pytest.fixture
def canvas_window(qapp, monkeypatch):
    def unexpected_modal(_parent, title, message, *_args, **_kwargs):
        pytest.fail(f"Unexpected modal dialog: {title}: {message}")

    monkeypatch.setattr(QMessageBox, "warning", unexpected_modal)
    win = MainWindow()
    win.resize(1000, 700)
    win.show()
    drain_events(qapp)
    yield win
    if shiboken6.isValid(win):
        win.close()
        win.deleteLater()
    drain_events(qapp)


def assert_canvas_chrome_hidden(win):
    for pane in win.panes.values():
        assert pane.header.isHidden()
        assert pane.controls.isHidden()
        assert not pane.property("selected")
        assert pane.layout().contentsMargins().isNull()
        assert pane.canvas.geometry() == pane.rect()


def color_at(win, x=.5, y=.5):
    """Read the composed window, including overlapping sibling video widgets."""
    image = win.stage.grab().toImage()
    return image.pixelColor(round((image.width() - 1) * x),
                            round((image.height() - 1) * y))


def make_layers(win, app, colors=("red", "lime", "blue")):
    while len(win.panes) < len(colors):
        win.add_blank()
    panes = list(win.panes.values())
    for index, (pane, color) in enumerate(zip(panes, colors)):
        pane.state.fit_mode = "stretch"
        pane.apply_state()
        win.canvas_workspace.set_rect(pane.state.id, (.1 + index * .05, .1 + index * .05, .7, .7))
        feed_solid(pane.canvas, color)
    drain_events(app)
    return panes


def test_default_is_one_video_only_free_canvas(canvas_window):
    win = canvas_window
    assert win.layout_mode == "canvas"
    assert win.root_widget is win.canvas_workspace
    assert len(win.panes) == 1
    assert win.active().state.canvas_rect == (0, 0, 1, 1)
    assert win.active().geometry() == win.canvas_workspace.rect()
    assert win.clean_mode
    assert win.top_panel.isHidden() and win.inspector.isHidden()
    assert not win._split_nodes
    assert win.active().state.fit_mode == "contain"
    assert_canvas_chrome_hidden(win)


def test_tab_edits_without_per_video_controls_and_escape_cleans_picture(canvas_window, qapp):
    win = canvas_window
    pane = win.active()
    pane.state.fit_mode = "stretch"
    pane.apply_state()
    feed_solid(pane.canvas, "red")
    win.activateWindow()
    pane.canvas.setFocus()
    QTest.keyClick(pane.canvas.viewport(), Qt.Key.Key_Tab)
    drain_events(qapp)
    assert not win.clean_mode
    assert win.top_panel.isHidden() and win.tools_panel.isHidden()
    assert win.inspector.isHidden() and win.statusBar().isHidden()
    assert_canvas_chrome_hidden(win)
    QTest.keyClick(pane.canvas.viewport(), Qt.Key.Key_Escape)
    drain_events(qapp)
    assert win.clean_mode
    assert_canvas_chrome_hidden(win)
    # A full-frame red source must not contain residual selection handles/borders.
    image = win.stage.grab().toImage()
    for x, y in ((0, 0), (1, image.height() // 2),
                 (image.width() - 1, image.height() - 1),
                 (image.width() // 2, image.height() // 2)):
        assert matches(image.pixelColor(x, y), "red")


def test_mouse_moves_video_freely_in_both_axes_without_changing_size(canvas_window, qapp):
    win = canvas_window
    win.set_clean_mode(False)
    pane = win.active()
    win.canvas_workspace.set_rect(pane.state.id, (.15, .15, .45, .4))
    drain_events(qapp)
    before = pane.geometry()
    target = pane.canvas.viewport()
    start = target.rect().center()
    delta = QPoint(77, 43)
    end_global = target.mapToGlobal(start) + delta
    QTest.mousePress(target, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(target, target.mapFromGlobal(end_global), delay=20)
    # The viewport has moved under the pointer, so recompute its local release
    # point rather than accidentally moving the mouse a second time.
    QTest.mouseRelease(target, Qt.MouseButton.LeftButton, pos=target.mapFromGlobal(end_global))
    drain_events(qapp)
    after = pane.geometry()
    assert after.x() == pytest.approx(before.x() + delta.x(), abs=2)
    assert after.y() == pytest.approx(before.y() + delta.y(), abs=2)
    assert after.size() == before.size()
    assert pane.state.canvas_rect[0] == pytest.approx(after.x() / win.canvas_workspace.width(), abs=.002)
    assert pane.state.canvas_rect[1] == pytest.approx(after.y() / win.canvas_workspace.height(), abs=.002)


@pytest.mark.parametrize("edge", ["right", "bottom", "left", "top", "top-left", "top-right", "bottom-left", "bottom-right"])
def test_mouse_resizes_edges_and_corner_independently(canvas_window, qapp, edge):
    win = canvas_window
    win.set_clean_mode(False)
    pane = win.active()
    win.canvas_workspace.set_rect(pane.state.id, (.15, .15, .4, .4))
    drain_events(qapp)
    before = pane.geometry()
    target = pane.canvas.viewport()
    rect = target.rect()
    left, right, top, bottom = (name in edge for name in ("left", "right", "top", "bottom"))
    start = QPoint(1 if left else rect.right() - 1 if right else rect.center().x(),
                   1 if top else rect.bottom() - 1 if bottom else rect.center().y())
    delta = QPoint(-59 if left else 69 if right else 0, -31 if top else 41 if bottom else 0)
    end_global = target.mapToGlobal(start) + delta
    QTest.mousePress(target, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(target, target.mapFromGlobal(end_global), delay=20)
    QTest.mouseRelease(target, Qt.MouseButton.LeftButton, pos=target.mapFromGlobal(end_global))
    drain_events(qapp)
    after = pane.geometry()
    assert after.x() == pytest.approx(before.x() + (delta.x() if left else 0), abs=2)
    assert after.y() == pytest.approx(before.y() + (delta.y() if top else 0), abs=2)
    assert after.width() == pytest.approx(before.width() + (-delta.x() if left else delta.x()), abs=2)
    assert after.height() == pytest.approx(before.height() + (-delta.y() if top else delta.y()), abs=2)


def test_crop_gesture_in_edit_mode_changes_source_crop_instead_of_layer_rect(canvas_window, qapp):
    win = canvas_window
    win.set_clean_mode(False)
    pane = win.active()
    win.canvas_workspace.set_rect(pane.state.id, (.12, .14, .62, .7))
    feed_solid(pane.canvas, "red", (400, 200))
    canvas = pane.canvas
    canvas.start_crop()
    drain_events(qapp)
    original_rect = pane.state.canvas_rect
    start = canvas.mapFromScene(QPointF(80, 40))
    end = canvas.mapFromScene(QPointF(300, 160))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end, delay=20)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    drain_events(qapp)
    assert not canvas.crop_active
    assert pane.state.crop == pytest.approx((.2, .2, .55, .6), abs=.015)
    assert pane.state.canvas_rect == original_rect


def test_clean_playback_click_and_drag_dont_move_or_resize_video(canvas_window, qapp):
    win = canvas_window
    pane = win.active()
    win.canvas_workspace.set_rect(pane.state.id, (.15, .2, .55, .5))
    drain_events(qapp)
    expected = pane.state.canvas_rect
    target = pane.canvas.viewport()
    start = target.rect().center()
    QTest.mousePress(target, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(target, start + QPoint(50, 40), delay=20)
    QTest.mouseRelease(target, Qt.MouseButton.LeftButton, pos=start + QPoint(50, 40))
    drain_events(qapp)
    assert pane.state.canvas_rect == expected
    assert win.clean_mode
    assert_canvas_chrome_hidden(win)


def test_layer_front_back_changes_real_composited_picture_and_preserves_geometry(canvas_window, qapp):
    win = canvas_window
    red, green = make_layers(win, qapp, ("red", "lime"))
    rects = {pid: pane.state.canvas_rect for pid, pane in win.panes.items()}
    assert matches(color_at(win), "lime")
    win.select(red.state.id)
    win.move_layer("front")
    drain_events(qapp)
    assert matches(color_at(win), "red")
    win.move_layer("back")
    drain_events(qapp)
    assert matches(color_at(win), "lime")
    assert {pid: pane.state.canvas_rect for pid, pane in win.panes.items()} == rects
    assert red.player is not green.player


def test_forward_backward_move_only_one_layer(canvas_window, qapp):
    win = canvas_window
    red, green, blue = make_layers(win, qapp)
    order = lambda: [p.state.id for p in sorted(win.panes.values(), key=lambda p: p.state.z_order)]
    win.select(red.state.id)
    win.move_layer("forward")
    drain_events(qapp)
    assert order() == [green.state.id, red.state.id, blue.state.id]
    assert matches(color_at(win), "blue")
    win.move_layer("forward")
    drain_events(qapp)
    assert order() == [green.state.id, blue.state.id, red.state.id]
    assert matches(color_at(win), "red")
    win.move_layer("backward")
    drain_events(qapp)
    assert order() == [green.state.id, red.state.id, blue.state.id]
    assert matches(color_at(win), "blue")


def test_select_fully_covered_layer_via_menu_never_raises_it(canvas_window, qapp):
    win = canvas_window
    red, green = make_layers(win, qapp, ("red", "lime"))
    for pane in (red, green):
        win.canvas_workspace.set_rect(pane.state.id, (.1, .1, .8, .8))
    drain_events(qapp)
    expected = {pid: pane.state.z_order for pid, pane in win.panes.items()}
    menu = win.create_context_menu(green.state.id)
    selection = next(m for m in menu._submenus if m.title() == "选中图层")
    selection.actions()[-1].trigger()
    drain_events(qapp)
    assert win.active_id == red.state.id
    assert {pid: pane.state.z_order for pid, pane in win.panes.items()} == expected
    assert matches(color_at(win), "lime")
    menu.deleteLater()
    # Picking an exposed part of the rear image also preserves stacking.
    win.canvas_workspace.set_rect(green.state.id, (.3, .3, .6, .6))
    QTest.mouseClick(red.canvas.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(20, 20))
    drain_events(qapp)
    assert win.active_id == red.state.id
    assert {pid: pane.state.z_order for pid, pane in win.panes.items()} == expected


def test_canvas_rect_survives_window_resize_focus_and_layout_switches(canvas_window, qapp):
    win = canvas_window
    win.add_blank()
    pane = win.active()
    expected = (.19, .23, .37, .41)
    win.canvas_workspace.set_rect(pane.state.id, expected)
    refs = dict(win.panes)
    players = {pid: p.player for pid, p in refs.items()}
    for width, height in ((750, 530), (1250, 820), (1000, 700)):
        win.resize(width, height)
        drain_events(qapp)
        assert pane.state.canvas_rect == expected
        stage = win.canvas_workspace
        assert pane.x() / stage.width() == pytest.approx(expected[0], abs=.002)
        assert pane.height() / stage.height() == pytest.approx(expected[3], abs=.003)
    for _ in range(2):
        win.toggle_focus(pane.state.id)
        drain_events(qapp)
        assert win.root_widget is pane
        win.toggle_focus(pane.state.id)
        win.set_layout_mode("grid")
        drain_events(qapp)
        win.set_layout_mode("canvas")
        drain_events(qapp)
        assert pane.state.canvas_rect == expected
        for pid, ref in refs.items():
            assert win.panes[pid] is ref and shiboken6.isValid(ref)
            assert ref.player is players[pid] and ref.isVisible()


def test_copy_preserves_transforms_and_appears_offset_as_top_layer(canvas_window, qapp):
    win = canvas_window
    original = win.active()
    win.canvas_workspace.set_rect(original.state.id, (.1, .15, .4, .45))
    original.state.crop = (.1, .2, .6, .5)
    original.state.rotation = 270
    original.state.flip_h = True
    original.state.fit_mode = "contain"
    original.state.loop_start_ms = 1200
    original.state.loop_end_ms = 3500
    original.state.sync_group = "2"
    original.apply_state()
    win.duplicate()
    drain_events(qapp)
    copied = win.active()
    for field in ("crop", "rotation", "flip_h", "fit_mode", "loop_start_ms", "loop_end_ms", "sync_group"):
        assert getattr(copied.state, field) == getattr(original.state, field)
    x, y, width, height = copied.state.canvas_rect
    assert x > original.state.canvas_rect[0]
    assert y > original.state.canvas_rect[1]
    assert (width, height) == original.state.canvas_rect[2:]
    assert copied.state.z_order > original.state.z_order
    assert copied.player is not original.player
    win.remove_pane(original.state.id)
    drain_events(qapp)
    assert shiboken6.isValid(copied) and copied.isVisible()


def test_numeric_position_and_size_dialog_applies_exact_pixels(canvas_window, qapp, monkeypatch):
    win = canvas_window
    target = (96, 64, 360, 220)

    def accept_position(dialog):
        fields = dialog.findChildren(QDoubleSpinBox)
        assert len(fields) == 4
        for field, value in zip(fields, target):
            field.setValue(value)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", accept_position)
    win.layer_rect_dialog()
    drain_events(qapp)
    rect = win.active().geometry()
    assert (rect.x(), rect.y(), rect.width(), rect.height()) == target


def test_workspace_restores_mode_position_size_and_layer_order(canvas_window, qapp, tmp_path):
    win = canvas_window
    red, green, blue = make_layers(win, qapp)
    win.select(red.state.id)
    win.move_layer("front")
    expected = {pid: (p.state.canvas_rect, p.state.z_order) for pid, p in win.panes.items()}
    session = tmp_path / "free-layout.gstudio"
    assert win.save_session(session)
    data = json.loads(session.read_text(encoding="utf-8"))
    assert data["layout_mode"] == "canvas"
    win.set_layout_mode("grid")
    assert win.load_session(session)
    drain_events(qapp)
    assert win.layout_mode == "canvas"
    assert win.root_widget is win.canvas_workspace
    assert {pid: (p.state.canvas_rect, p.state.z_order) for pid, p in win.panes.items()} == expected
    assert all(shiboken6.isValid(p) and p.isVisible() for p in win.panes.values())


def test_old_workspace_without_canvas_fields_opens_as_grid(canvas_window, qapp, tmp_path):
    win = canvas_window
    win.add_blank()
    data = win.session_data()
    data.pop("layout_mode")
    for pane in data["panes"]:
        pane.pop("canvas_rect")
        pane.pop("z_order")
    session = tmp_path / "old-grid.gstudio"
    session.write_text(json.dumps(data), encoding="utf-8")
    assert win.load_session(session)
    drain_events(qapp)
    assert win.layout_mode == "grid"
    assert win.canvas_workspace is None
    assert win._split_nodes
    assert len(win.panes) == 2


def test_duplicate_with_max_saved_z_order_still_saves_valid_workspace(canvas_window, qapp, tmp_path):
    win = canvas_window
    low = win.active()
    win.add_blank()
    high = win.active()
    low.state.z_order = -1_000_000
    high.state.z_order = 1_000_000
    win.duplicate(high.state.id)
    drain_events(qapp)
    copied = win.active()
    assert low.state.z_order < high.state.z_order < copied.state.z_order
    assert copied.state.z_order <= 1_000_000
    assert win.save_session(tmp_path / "bounded-layers.gstudio")


def test_converting_focused_legacy_grid_uses_unfocused_pane_positions(canvas_window, qapp):
    win = canvas_window
    win.set_layout_mode("grid")
    win.add_blank()
    drain_events(qapp)
    splitter = win.root_widget
    splitter.setSizes([700, 300])
    drain_events(qapp)
    expected = {}
    for pane in win.panes.values():
        pane.state.canvas_rect = None
        origin = pane.mapTo(win.stage, QPoint())
        expected[pane.state.id] = (origin.x() / win.stage.width(), origin.y() / win.stage.height(),
                                   pane.width() / win.stage.width(), pane.height() / win.stage.height())
    first = next(iter(win.panes.values()))
    win.toggle_focus(first.state.id)
    drain_events(qapp)
    assert win.root_widget is first
    win.set_layout_mode("canvas")
    drain_events(qapp)
    assert win.focus_id is None
    assert win.canvas_workspace is win.root_widget
    for pid, rect in expected.items():
        assert win.panes[pid].state.canvas_rect == pytest.approx(rect, abs=.003)


@pytest.mark.parametrize("surface", ["pane", "canvas"])
def test_dropping_file_on_existing_canvas_video_adds_layer_without_replacing_original(canvas_window, qapp, sample_video, surface):
    win = canvas_window
    original = load_pane(win, sample_video, position_ms=2200)
    wait_ready(original, position_ms=2200)
    original.state.crop = (.1, .15, .6, .65)
    original.state.rotation = 90
    original.apply_state()
    second_source = sample_video.with_name("sample-short.mp4")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(second_source))])
    target = original if surface == "pane" else original.canvas.viewport()
    enter = QDragEnterEvent(QPoint(20, 20), Qt.DropAction.CopyAction, mime,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(target, enter)
    assert enter.isAccepted()
    drop = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, mime,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(target, drop)
    assert drop.isAccepted()
    drain_events(qapp)
    assert len(win.panes) == 2
    assert win.panes[original.state.id] is original
    assert original.state.source == str(sample_video)
    assert original.state.crop == (.1, .15, .6, .65)
    assert original.state.rotation == 90
    assert original.player.position() == pytest.approx(2200, abs=50)
    added = win.active()
    assert added is not original
    assert added.state.source == str(second_source)
    assert added.state.z_order > original.state.z_order
    wait_ready(added, paused=False)


def test_canvas_changes_preserve_real_video_position_loop_and_sync(canvas_window, qapp, sample_video):
    win = canvas_window
    first = load_pane(win, sample_video, position_ms=2200)
    wait_ready(first, position_ms=2200)
    win.duplicate()
    second = win.active()
    wait_ready(second, position_ms=2200)
    win.playback.join_group([first.state.id, second.state.id], leader_id=first.state.id)
    win.playback.set_loop(first.state.id, True, start_ms=1000, end_ms=3500)
    players = {p.state.id: p.player for p in (first, second)}
    for clean in (False, True):
        win.set_clean_mode(clean)
        win.canvas_workspace.set_rect(first.state.id, (.05, .1, .65, .75))
        win.move_layer("back")
        win.set_layout_mode("grid")
        drain_events(qapp)
        win.set_layout_mode("canvas")
        drain_events(qapp)
        for pane in (first, second):
            assert pane.player is players[pane.state.id]
            assert pane.player.position() == pytest.approx(2200, abs=50)
            assert pane.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
            assert pane.state.sync_group == "1"
            assert (pane.state.loop_start_ms, pane.state.loop_end_ms) == (1000, 3500)
            assert not pane._pending_restore
            assert current_frame(pane).isValid()
    win.playback.seek(second.state.id, 2700)
    for pane in (first, second):
        wait_ready(pane, position_ms=2700)
    win.playback.set_playing(first.state.id, True)
    wait_until(lambda: all(p.player.position() > 2900 for p in (first, second)),
               "both canvas players advancing after layout edits", panes=[first, second])
