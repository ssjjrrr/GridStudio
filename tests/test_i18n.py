"""Language selection and live translation preserve media objects and user data."""
import ast
from pathlib import Path
import re

import pytest
from PySide6.QtCore import QLocale, QSettings
from PySide6.QtWidgets import QDialogButtonBox, QFileDialog, QLabel, QMessageBox

from gridstudio import i18n
from gridstudio.app import MainWindow
from gridstudio._translations import ENGLISH, ERRORS
from test_app import drain_events, qapp


@pytest.fixture(autouse=True)
def language_settings(qapp, monkeypatch, tmp_path):
    settings = QSettings(str(tmp_path / "language.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(i18n, "QSettings", lambda *_args: settings)
    monkeypatch.delenv("GRIDSTUDIO_LANGUAGE", raising=False)
    previous = i18n.language()
    i18n.set_language("zh_CN")
    yield settings
    i18n.set_language(previous)
    drain_events(qapp)


def test_language_precedence_and_system_fallback(language_settings, monkeypatch):
    assert i18n.preferred_language(system_language="zh_TW") == "zh_CN"
    assert i18n.preferred_language(system_language="fr_FR") == "en"
    language_settings.setValue("ui/language", "zh_CN")
    assert i18n.preferred_language(system_language="en_US") == "zh_CN"
    monkeypatch.setenv("GRIDSTUDIO_LANGUAGE", "en")
    assert i18n.preferred_language() == "en"
    assert i18n.preferred_language("zh_CN") == "zh_CN"


def test_explicit_override_does_not_persist_and_system_restores_default(language_settings):
    i18n.set_language("en", persist=True)
    i18n.initialize("zh_CN")
    assert i18n.language() == "zh_CN"
    assert language_settings.value("ui/language") == "en"
    i18n.use_system_language()
    assert not language_settings.contains("ui/language")
    assert i18n.follows_system()
    assert i18n.language() == i18n.normalize_language(QLocale.system().name())


def menu_actions(menu):
    # Keep the menu wrappers retained by MainWindow; re-wrapping menuAction()
    # submenus can transfer PySide ownership when a temporary generator ends.
    return [action for submenu in [menu, *menu._submenus] for action in submenu.actions()]


@pytest.mark.parametrize("layout_mode", ["canvas", "grid"])
def test_menu_switch_updates_existing_widgets_without_rebuilding_players(qapp, language_settings, layout_mode):
    window = MainWindow()
    window.show()
    window.set_layout_mode(layout_mode)
    window.set_clean_mode(False)
    pane = window.active()
    pane.state.rotation = 90
    pane.state.crop = (.1, .1, .8, .7)
    pane.state.source = "C:/videos/布局-Ctrl+O.mp4"
    pane.apply_state()
    pane.refresh_header()
    window.refresh_inspector()
    drain_events(qapp)
    state_before = pane.state.to_dict()
    player_before = pane.player
    canvas_before = pane.canvas
    geometry_before = pane.geometry()
    try:
        menu = window.create_context_menu()
        next(a for a in menu_actions(menu) if a.text() == "English").trigger()
        drain_events(qapp)
        assert language_settings.value("ui/language") == "en"
        assert window.windowTitle() == "GridStudio · Multi-video player"
        assert window.rotation_label.text() == "Rotation: 90°"
        assert window.crop_label.text().startswith("Kept region 80% × 70%")
        assert window.layout_combo.itemText(0) == "Free canvas"
        assert window.fit_mode.itemText(0) == "Keep aspect ratio (show all)"
        assert window.selected_label.text() == "布局-Ctrl+O.mp4"
        assert window.source_label.text() == "C:/videos/布局-Ctrl+O.mp4"
        assert pane.player is player_before
        assert pane.canvas is canvas_before
        assert pane.state.to_dict() == state_before
        # Free-canvas layers keep their pixel geometry. Grid editing chrome
        # can legitimately relayout when translated labels change width;
        # both modes must preserve the exact saved state and media objects.
        if layout_mode == "canvas":
            assert pane.geometry() == geometry_before
        assert pane.hover_controls.mute_button.toolTip() == "Unmute"
        english_menu = window.create_context_menu()
        exceptions = {"Language / 语言", "简体中文", "System default / 跟随系统"}
        assert all(not re.search("[\u4e00-\u9fff]", a.text()) for a in menu_actions(english_menu)
                   if a.text() not in exceptions and "布局-Ctrl+O.mp4" not in a.text())
        next(a for a in menu_actions(english_menu) if a.text() == "简体中文").trigger()
        drain_events(qapp)
        assert window.rotation_label.text() == "当前旋转 90°"
        assert window.layout_combo.itemText(0) == "自由画布"
        assert window.source_label.text() == "C:/videos/布局-Ctrl+O.mp4"
        assert pane.player is player_before
        assert pane.state.to_dict() == state_before
        menu.deleteLater()
        english_menu.deleteLater()
    finally:
        window.close()
        window.deleteLater()
        drain_events(qapp)


def test_static_translation_survives_formatted_text_cache_eviction(qapp):
    i18n.set_language("en")
    label = QLabel(i18n.tr("自由画布"))
    for index in range(2200):
        i18n.tr("当前旋转 {value1}°", value1=index)
    assert "Free canvas" not in i18n._rendered
    i18n.set_language("zh_CN")
    i18n.retranslate_widgets(label)
    assert label.text() == "自由画布"
    label.deleteLater()


def test_mac_shortcut_substitution_preserves_user_values(monkeypatch):
    monkeypatch.setattr(i18n.sys, "platform", "darwin")
    i18n.set_language("en")
    assert i18n.tr("添加视频…\tCtrl+O") == "Add videos…\t⌘O"
    assert i18n.tr("工作区已保存：{path}", path="/tmp/Ctrl+O.gstudio") == "Workspace saved: /tmp/Ctrl+O.gstudio"


def test_mac_chinese_shortcut_survives_cache_eviction(monkeypatch):
    monkeypatch.setattr(i18n.sys, "platform", "darwin")
    i18n.set_language("zh_CN")
    tooltip = i18n.tr("打开本地视频，可多选（Ctrl+O）")
    assert "⌘O" in tooltip
    for index in range(2200):
        i18n.tr("当前旋转 {value1}°", value1=index)
    assert tooltip not in i18n._rendered
    i18n.set_language("en")
    assert i18n.translated_existing(tooltip) == "Open local videos; multiple selection supported (⌘O)"


def test_qt_standard_buttons_translate_in_both_languages(qapp):
    i18n.set_language("zh_CN")
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
    assert buttons.button(QDialogButtonBox.StandardButton.Cancel).text().replace("&", "") == "取消"
    i18n.set_language("en")
    drain_events(qapp)
    assert buttons.button(QDialogButtonBox.StandardButton.Cancel).text().replace("&", "") == "Cancel"
    buttons.deleteLater()


def test_english_help_file_filters_and_localized_model_errors(qapp, monkeypatch, tmp_path):
    i18n.set_language("en")
    window = MainWindow()
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda _parent, title, text: messages.append((title, text)))
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, title, text: messages.append((title, text)))
    files = []
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: (files.append(args) or ([], "")))
    try:
        window.show_help()
        assert messages[-1][0] == "About GridStudio"
        assert not re.search("[\u4e00-\u9fff]", messages[-1][1])
        window.open_files()
        assert files[-1][-1].startswith("Video files")
        invalid = tmp_path / "invalid.gstudio"
        invalid.write_text('{}', encoding="utf-8")
        assert not window.load_session(invalid)
        assert messages[-1][0] == "Cannot open workspace"
        i18n.set_language("zh_CN")
        assert not window.load_session(invalid)
        assert messages[-1][0] == "无法打开工作区"
        assert messages[-1][1] == "工作区必须包含 format、version、panes 和 layout"
        assert i18n.error_text("volume must be finite and between 0 and 1") == "volume 必须是 0 到 1 之间的有限数字"
    finally:
        window.close()
        window.deleteLater()
        drain_events(qapp)


def test_empty_canvas_sentinel_survives_language_changes(qapp):
    window = MainWindow()
    pane = window.active()
    i18n.set_language("en")
    pane.canvas.set_has_media(True)
    assert pane.canvas._message == ""
    pane.canvas.set_has_media(False)
    assert i18n.tr(pane.canvas._message) == "Drop video files here"
    i18n.set_language("zh_CN")
    assert pane.canvas._message == "拖入视频文件"
    window.close()
    window.deleteLater()
    drain_events(qapp)


def test_language_switch_preserves_notification_expiry(qapp, monkeypatch):
    window = MainWindow()
    window.notify(i18n.tr("已取消裁剪"), 6000)
    calls = []
    try:
        # Restore the native QStatusBar method while its C++ object still
        # exists. Restoring it after deferred deletion can crash Shiboken.
        with monkeypatch.context() as patch:
            patch.setattr(window.statusBar(), "showMessage", lambda text, timeout=0: calls.append((text, timeout)))
            i18n.set_language("en")
            assert calls[-1][0] == "Crop cancelled"
            assert 0 < calls[-1][1] <= 6000
    finally:
        window.close()
        window.deleteLater()
        drain_events(qapp)


def test_translation_calls_and_model_validation_messages_have_catalog_entries():
    package = Path(__file__).resolve().parents[1] / "gridstudio"
    for filename in ("app.py", "hover_controls.py", "canvas.py", "playback.py"):
        tree = ast.parse((package / filename).read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
                if node.args and isinstance(node.args[0], ast.Constant):
                    assert node.args[0].value in ENGLISH, (filename, node.lineno, node.args[0].value)
    tree = ast.parse((package / "model.py").read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ValueError":
            value = node.args[0]
            if isinstance(value, ast.Constant):
                assert value.value in ERRORS
