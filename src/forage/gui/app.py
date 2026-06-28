"""Wire the window to the store/CLAP worker thread and run the Qt event loop."""

from __future__ import annotations

import sys

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .workers import StoreWorker


def build(app_argv=None):
    """Construct (QApplication, MainWindow, QThread, StoreWorker) fully wired but not
    started. Split out from run() so a headless smoke test can build without exec()."""
    app = QApplication.instance() or QApplication(app_argv or sys.argv)
    win = MainWindow()
    thread = QThread()
    worker = StoreWorker()
    worker.moveToThread(thread)
    thread.started.connect(worker.start)

    win.searchRequested.connect(worker.do_search)
    win.similarRequested.connect(worker.do_similar)
    win.growRequested.connect(worker.do_grow)
    win.categorizeRequested.connect(worker.do_categorize)

    worker.listed.connect(win.on_listed)
    worker.counted.connect(win.on_counted)
    worker.searched.connect(win.on_searched)
    worker.clapLoading.connect(win.on_clap_loading)
    worker.clapReady.connect(win.on_clap_ready)
    worker.growProgress.connect(win.on_grow_progress)
    worker.growDone.connect(win.on_grow_done)
    worker.categorized.connect(win.on_categorized)
    worker.failed.connect(win.on_failed)
    return app, win, thread, worker


def run() -> int:
    app, win, thread, worker = build()
    thread.start()
    win.show()
    code = app.exec()
    thread.quit()
    thread.wait()
    return code
