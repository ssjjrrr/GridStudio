"""Enter native media slots without holding Python's interpreter lock.

Several direct PySide QMediaPlayer controls hold the GIL. During a seek Qt replaces
decoder/renderer objects; a renderer thread can call disconnectNotify on the
Python-created audio output while holding a Qt connection lock. Entering the
next media operation with the GIL held can then invert those two locks.

QtCore's native invokeMethod glue releases the GIL around the C++ call.
DirectConnection preserves command ordering and immediate state changes; it
does not enqueue work or move an object to a different thread.
"""
from __future__ import annotations

from PySide6.QtCore import Q_ARG, QMetaObject, QThread, Qt
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

_MISSING = object()
_ARGUMENTS = {
    "setPosition": ("qlonglong", int),
    "setPlaybackRate": ("double", float),
    "setSource": ("QUrl", lambda value: value),
    "setVolume": ("float", float),
    "setMuted": ("bool", bool),
}
_NO_ARGUMENTS = frozenset(("play", "pause", "stop"))


def media_command(target, method: str, value=_MISSING) -> None:
    """Call a supported native media slot synchronously, with the GIL released.

    Lightweight engine test doubles retain their normal Python methods. A
    failed native invocation never falls back to the unsafe direct wrapper.
    """
    if method in _NO_ARGUMENTS:
        if value is not _MISSING:
            raise TypeError(f"{method} takes no argument")
        arguments = ()
    elif method in _ARGUMENTS:
        if value is _MISSING:
            raise TypeError(f"{method} requires an argument")
        type_name, convert = _ARGUMENTS[method]
        value = convert(value)
        arguments = (Q_ARG(type_name, value),)
    else:
        raise ValueError(f"Unsupported media command: {method}")

    if not isinstance(target, (QMediaPlayer, QAudioOutput)):
        getattr(target, method)(*(() if value is _MISSING else (value,)))
        return
    if QThread.currentThread() != target.thread():
        raise RuntimeError("Media commands must run on the media object's Qt thread")
    if not QMetaObject.invokeMethod(target, method, Qt.ConnectionType.DirectConnection, *arguments):
        raise RuntimeError(f"Native media command failed: {method}")
