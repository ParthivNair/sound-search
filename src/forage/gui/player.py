"""Audition the ORIGINAL file via QtMultimedia (ships with PySide6, no extra dep).

QtMultimedia is imported lazily so merely constructing the window (e.g. the headless
launch smoke test) doesn't require an audio backend.
"""

from __future__ import annotations


class AuditionPlayer:
    def __init__(self):
        self._player = None
        self._out = None

    def _ensure(self):
        if self._player is None:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            self._out = QAudioOutput()
            self._player = QMediaPlayer()
            self._player.setAudioOutput(self._out)

    def play(self, path):
        from PySide6.QtCore import QUrl
        self._ensure()
        self._player.stop()                       # stop-on-new-selection
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()

    def stop(self):
        if self._player is not None:
            self._player.stop()
