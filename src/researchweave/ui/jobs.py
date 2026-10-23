"""Bounded Qt worker queue with cancellation and generation-aware UI callbacks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import Event
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class JobSignals(QObject):
    finished = pyqtSignal(str, int, object)
    failed = pyqtSignal(str, int, str)
    cancelled = pyqtSignal(str, int)


class _Task(QRunnable):
    def __init__(self, task_id: str, generation: int, stop: Event,
                 callback: Callable[[Event], Any], signals: JobSignals) -> None:
        super().__init__()
        self.task_id = task_id
        self.generation = generation
        self.stop = stop
        self.callback = callback
        self.signals = signals

    def run(self) -> None:
        if self.stop.is_set():
            self.signals.cancelled.emit(self.task_id, self.generation)
            return
        try:
            result = self.callback(self.stop)
        except Exception:
            self.signals.failed.emit(self.task_id, self.generation,
                                     "Background task failed. Check the input and retry.")
            return
        if self.stop.is_set():
            self.signals.cancelled.emit(self.task_id, self.generation)
        else:
            self.signals.finished.emit(self.task_id, self.generation, result)


@dataclass
class Job:
    task_id: str
    generation: int
    stop: Event
    state: str = "queued"


class JobManager(QObject):
    result = pyqtSignal(str, object)
    error = pyqtSignal(str, str)
    changed = pyqtSignal(str, str)

    def __init__(self, max_workers: int = 2) -> None:
        super().__init__()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max_workers)
        self.signals = JobSignals(self)
        self.signals.finished.connect(self._finished)
        self.signals.failed.connect(self._failed)
        self.signals.cancelled.connect(self._cancelled)
        self.jobs: dict[str, Job] = {}
        self.generation = 0

    def submit(self, task_id: str, callback: Callable[[Event], Any]) -> bool:
        if task_id in self.jobs and self.jobs[task_id].state in ("queued", "running"):
            return False
        stop = Event()
        job = Job(task_id, self.generation, stop, "running")
        self.jobs[task_id] = job
        self.pool.start(_Task(task_id, job.generation, stop, callback, self.signals))
        self.changed.emit(task_id, "running")
        return True

    def cancel(self, task_id: str) -> None:
        if task_id in self.jobs:
            self.jobs[task_id].stop.set()
            self.changed.emit(task_id, "cancelling")

    def invalidate(self) -> None:
        self.generation += 1
        for task_id in list(self.jobs):
            self.cancel(task_id)

    def _current(self, task_id: str, generation: int) -> bool:
        return (generation == self.generation and task_id in self.jobs
                and self.jobs[task_id].generation == generation)

    def _finished(self, task_id: str, generation: int, value: object) -> None:
        if self._current(task_id, generation):
            self.jobs[task_id].state = "completed"
            self.changed.emit(task_id, "completed")
            self.result.emit(task_id, value)

    def _failed(self, task_id: str, generation: int, message: str) -> None:
        if self._current(task_id, generation):
            self.jobs[task_id].state = "failed"
            self.changed.emit(task_id, "failed")
            self.error.emit(task_id, message)

    def _cancelled(self, task_id: str, generation: int) -> None:
        if self._current(task_id, generation):
            self.jobs[task_id].state = "cancelled"
            self.changed.emit(task_id, "cancelled")
