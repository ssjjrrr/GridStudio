"""English/Chinese UI text and live language switching without media rebuilds.

Workspace keys and media paths never pass through this module. CLI overrides
last for one process; only an explicit language-menu selection is persisted.
"""
from __future__ import annotations

from collections import OrderedDict
import os
from pathlib import Path
import re
import sys

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QObject, QSettings, QTranslator, Signal

from ._translations import ENGLISH, ERRORS


class _LanguageEvents(QObject):
    changed = Signal()


events = _LanguageEvents()
_language = "zh_CN"
_initialized = False
_follow_system = False
_qt_translator = None
# Remember formatted UI strings so an already visible label can be translated
# without guessing substitutions or touching filenames. Bound memory use.
_rendered: OrderedDict[str, tuple[str, dict]] = OrderedDict()
_english_sources = {english: chinese for chinese, english in ENGLISH.items() if "{" not in english}
_english_sources.update({english.replace("Ctrl+", "⌘"): chinese
                         for english, chinese in list(_english_sources.items())})
_english_sources.update({chinese.replace("Ctrl+", "⌘"): chinese
                         for chinese in ENGLISH if "{" not in chinese})


def normalize_language(value: str) -> str:
    return "zh_CN" if value.lower().replace("-", "_").startswith("zh") else "en"


def preferred_language(override=None, *, settings=None, system_language=None):
    if override:
        return normalize_language(override)
    if environment := os.environ.get("GRIDSTUDIO_LANGUAGE"):
        return normalize_language(environment)
    settings = settings if settings is not None else QSettings("GridStudio", "GridStudio")
    if saved := settings.value("ui/language", ""):
        return normalize_language(str(saved))
    return normalize_language(system_language or QLocale.system().name())


def language() -> str:
    return _language


def qt_translation_loaded() -> bool:
    return _qt_translator is not None


def initialize(override=None):
    global _initialized, _follow_system
    if not _initialized or override is not None:
        set_language(preferred_language(override))
        _follow_system = not (override or os.environ.get("GRIDSTUDIO_LANGUAGE") or
                              QSettings("GridStudio", "GridStudio").value("ui/language", ""))
        _initialized = True
    else:
        _install_qt_translation()


def _install_qt_translation():
    global _qt_translator
    app = QCoreApplication.instance()
    if app is None:
        return
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator.deleteLater()
        _qt_translator = None
    if _language == "zh_CN":
        candidates = [Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))]
        if hasattr(sys, "_MEIPASS"):
            candidates.insert(0, Path(sys._MEIPASS) / "assets" / "translations")
        for directory in candidates:
            translator = QTranslator(app)
            if translator.load("qtbase_zh_CN", str(directory)):
                app.installTranslator(translator)
                _qt_translator = translator
                break
            translator.deleteLater()
    QLocale.setDefault(QLocale("zh_CN" if _language == "zh_CN" else "en_US"))


def set_language(value: str, *, persist=False):
    global _language, _initialized, _follow_system
    new_language = normalize_language(value)
    changed = _language != new_language
    _language = new_language
    _initialized = True
    _follow_system = False
    if persist:
        settings = QSettings("GridStudio", "GridStudio")
        settings.setValue("ui/language", _language)
        settings.sync()
    _install_qt_translation()
    if changed:
        events.changed.emit()


def follows_system():
    return _follow_system


def use_system_language():
    global _follow_system
    settings = QSettings("GridStudio", "GridStudio")
    settings.remove("ui/language")
    settings.sync()
    set_language(QLocale.system().name())
    _follow_system = True


def tr(source: str, **values) -> str:
    template = ENGLISH.get(source, source) if _language == "en" else source
    # Qt's Ctrl modifier maps to Command on macOS; show the same native key.
    if sys.platform == "darwin":
        template = template.replace("Ctrl+", "⌘")
    result = template.format(**values) if values else template
    if source in ENGLISH:
        _rendered[result] = (source, values)
        _rendered.move_to_end(result)
        while len(_rendered) > 2048:
            _rendered.popitem(last=False)
    return result


def translated_existing(text: str) -> str:
    entry = _rendered.get(text)
    if entry is not None:
        source, values = entry
        return tr(source, **values)
    if text in ENGLISH:
        return tr(text)
    if text in _english_sources:
        return tr(_english_sources[text])
    return text


def retranslate_widgets(root):
    """Refresh text properties only; never reparent widgets or touch players."""
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QWidget

    for widget in [root, *root.findChildren(QWidget), *root.findChildren(QAction)]:
        if not widget.property("i18nUserText"):
            properties = [("text", "setText"), ("toolTip", "setToolTip"),
                          ("windowTitle", "setWindowTitle"),
                          ("accessibleName", "setAccessibleName")]
            for getter, setter in properties:
                if hasattr(widget, getter) and hasattr(widget, setter):
                    previous = getattr(widget, getter)()
                    current = translated_existing(previous)
                    if current != previous:
                        getattr(widget, setter)(current)
        if isinstance(widget, QComboBox):
            for index in range(widget.count()):
                widget.setItemText(index, translated_existing(widget.itemText(index)))
        if isinstance(widget, QDoubleSpinBox):
            widget.setSuffix(translated_existing(widget.suffix()))
    root.update()


def error_text(message: str) -> str:
    """Translate model validation errors at the UI boundary, preserving keys."""
    if _language != "zh_CN":
        return translated_existing(message)
    for english, chinese in ERRORS.items():
        if "{" not in english:
            if message == english:
                return chinese
            continue
        pattern = re.escape(english)
        names = re.findall(r"\{(\w+)\}", english)
        for name in names:
            pattern = pattern.replace(re.escape("{" + name + "}"), f"(?P<{name}>.+?)")
        if match := re.fullmatch(pattern, message):
            return chinese.format(**match.groupdict())
    return translated_existing(message)
