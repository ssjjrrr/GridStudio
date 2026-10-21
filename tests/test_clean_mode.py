"""Checks that video-only playback stays usable without persistent controls."""

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest

from test_app import assert_live_panes, drain_events, qapp, window
from test_media import current_frame, load_pane, wait_ready, wait_until


def assert_video_only(win):
    assert win.clean_mode
    assert win.top_panel.isHidden()
    assert win.tools_panel.isHidden()
    assert win.inspector.isHidden()
    assert win.statusBar().isHidden()
    assert win.body_layout.contentsMargins().isNull()
    for pane in win.panes.values():
        assert pane.header.isHidden()
        assert pane.controls.isHidden()
        assert not pane.property("selected")
        assert pane.layout().contentsMargins().isNull()
        assert pane.canvas.geometry() == pane.rect()
        assert pane.canvas.backgroundBrush().color().name() == "#000000"
    for splitter, _ in win._split_nodes:
        assert splitter.handleWidth() == 0


def menu_action(menu, label):
    # Traverse QObject ownership directly. Recursive action.menu() temporaries
    # can invalidate a nested QAction wrapper in PySide even while Qt owns it.
    for action in menu.findChildren(QAction):
        if action.text().split("\t")[0] == label:
            return action
    return None


def test_default_client_area_contains_only_one_full_size_canvas(window, qapp):
    assert len(window.panes) == 1
    assert window.stage.geometry() == window.centralWidget().rect()
    assert window.active().state.fit_mode == "contain"
    assert window.active().canvas.fill_mode == "contain"
    assert_video_only(window)
    QTest.mouseMove(window.active().canvas.viewport(), QPoint(100, 100))
    drain_events(qapp)
    assert_video_only(window)


def test_tab_from_video_shows_editor_and_escape_returns_to_video_only(window, qapp):
    pane = window.active()
    window.activateWindow()
    pane.canvas.setFocus()
    QTest.keyClick(pane.canvas.viewport(), Qt.Key.Key_Tab)
    drain_events(qapp)
    assert not window.clean_mode
    assert window.top_panel.isVisible()
    assert window.tools_panel.isVisible()
    assert window.inspector.isVisible()
    assert window.statusBar().isVisible()
    assert pane.header.isVisible()
    assert pane.controls.isVisible()
    assert pane.header.copy_button.isVisible()
    assert pane.timeline.isVisible()
    assert pane.property("selected")
    assert pane.canvas.fill_mode == "contain"
    QTest.keyClick(pane.canvas.viewport(), Qt.Key.Key_Escape)
    drain_events(qapp)
    assert_video_only(window)
    assert window.active() is pane
    assert pane.canvas.fill_mode == "contain"


def test_clean_splitter_still_resizes_by_dragging(window, qapp):
    window.add_blank()
    drain_events(qapp)
    splitter = window.root_widget
    before = splitter.sizes()
    handle = splitter.handle(1)
    start = handle.rect().center()
    QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(handle, start + QPoint(110, 0), delay=30)
    QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=start + QPoint(110, 0))
    drain_events(qapp)
    after = splitter.sizes()
    assert after[0] > before[0] + 50
    assert after[1] < before[1] - 50
    assert_video_only(window)


def test_switching_modes_preserves_divider_proportions_and_players(window, qapp):
    window.add_blank()
    drain_events(qapp)
    splitter = window.root_widget
    splitter.setSizes([700, 300])
    drain_events(qapp)
    refs = dict(window.panes)
    players = {pid: pane.player for pid, pane in refs.items()}
    before = splitter.sizes()
    ratio = before[0] / sum(before)
    for _ in range(3):
        window.set_clean_mode(False)
        drain_events(qapp)
        assert splitter.handleWidth() == 7
        window.set_clean_mode(True)
        drain_events(qapp)
        assert_video_only(window)
        assert_live_panes(window, refs)
        assert all(window.panes[pid].player is player for pid, player in players.items())
        sizes = splitter.sizes()
        assert sizes[0] / sum(sizes) == pytest.approx(ratio, abs=0.015)


def test_new_duplicate_and_restored_panes_keep_video_only_layout(window, qapp, tmp_path):
    original = window.active()
    original.state.crop = (0.1, 0.2, 0.6, 0.5)
    original.state.rotation = 270
    original.state.flip_h = True
    original.apply_state()
    window.duplicate()
    drain_events(qapp)
    duplicate = window.active()
    assert duplicate.state.crop == original.state.crop
    assert duplicate.state.rotation == 270
    assert duplicate.state.flip_h
    assert_video_only(window)
    window.add_blank(axis="vertical")
    drain_events(qapp)
    assert_video_only(window)
    session = tmp_path / "video-only.gstudio"
    assert window.save_session(session)
    assert window.load_session(session)
    drain_events(qapp)
    assert len(window.panes) == 3
    assert window.panes[duplicate.state.id].state.crop == (0.1, 0.2, 0.6, 0.5)
    assert window.panes[duplicate.state.id].state.rotation == 270
    assert_video_only(window)
    for pid in window.panes:
        window.select(pid)
        assert not any(pane.property("selected") for pane in window.panes.values())


def test_context_menu_operates_on_picture_and_duplicates_without_showing_ui(window, qapp):
    original = window.active()
    menu = window.create_context_menu(original.state.id)
    for label in ("添加视频…", "布局", "工作区", "显示编辑界面", "全屏 / 退出全屏"):
        assert menu_action(menu, label) is not None
    menu_action(menu, "顺时针旋转 90°").trigger()
    assert original.state.rotation == 90
    menu_action(menu, "水平镜像").trigger()
    assert original.state.flip_h
    menu_action(menu, "复制窗格").trigger()
    drain_events(qapp)
    assert len(window.panes) == 2
    assert window.active().state.rotation == 90
    assert window.active().state.flip_h
    assert_video_only(window)
    menu.deleteLater()


@pytest.mark.parametrize("paused", [True, False])
def test_changing_ui_keeps_real_video_position_and_playback(window, qapp, paused):
    sample = Path(__file__).parent / "fixtures" / "sample.mp4"
    if not sample.is_file():
        pytest.skip("Generated sample.mp4 is not available")
    pane = load_pane(window, sample.resolve(), position_ms=3000, paused=paused)
    wait_ready(pane, position_ms=3000, paused=paused)
    player = pane.player
    source = player.source()
    position = player.position()
    frame = current_frame(pane).startTime()
    for clean in (False, True, False, True):
        window.set_clean_mode(clean)
        drain_events(qapp)
        assert window.active() is pane
        assert pane.player is player
        assert player.source() == source
        assert not pane._pending_restore
        assert player.playbackState() == (QMediaPlayer.PlaybackState.PausedState if paused
                                           else QMediaPlayer.PlaybackState.PlayingState)
        assert player.position() >= position - 50
    assert_video_only(window)
    if paused:
        assert player.position() == pytest.approx(position, abs=50)
        assert current_frame(pane).startTime() == frame
    else:
        wait_until(lambda: player.position() > position + 250
                   and current_frame(pane).startTime() > frame + 150000,
                   "video continuing after UI mode changes", panes=[pane])


def test_fullscreen_removes_window_chrome_and_escape_restores_video_only(window, qapp):
    window.activateWindow()
    window.active().canvas.setFocus()
    QTest.keyClick(window.active().canvas.viewport(), Qt.Key.Key_F11)
    drain_events(qapp)
    assert window.isFullScreen()
    assert_video_only(window)
    QTest.keyClick(window.active().canvas.viewport(), Qt.Key.Key_Escape)
    drain_events(qapp)
    assert not window.isFullScreen()
    assert_video_only(window)
