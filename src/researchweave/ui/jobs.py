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
    chunk = pyqtSignal(str, int, str)


class _Task(QRunnable):
    def __init__(
        self,
        task_id: str,
        generation: int,
        stop: Event,
        callback: Callable[[Event], Any],
        signals: JobSignals,
    ) -> None:
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
            self.signals.failed.emit(
                self.task_id, self.generation, "Background task failed. Check the input and retry."
            )
            return
        if self.stop.is_set():
            self.signals.cancelled.emit(self.task_id, self.generation)
        else:
            self.signals.finished.emit(self.task_id, self.generation, result)


class _StreamingTask(QRunnable):
    def __init__(
        self,
        task_id: str,
        generation: int,
        stop: Event,
        callback: Callable[[Event, Callable[[str], None]], Any],
        signals: JobSignals,
    ) -> None:
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

        def emit_chunk(value: str) -> None:
            if not self.stop.is_set() and value:
                self.signals.chunk.emit(self.task_id, self.generation, value)

        try:
            result = self.callback(self.stop, emit_chunk)
        except Exception:
            self.signals.failed.emit(
                self.task_id, self.generation, "Background task failed. Check the input and retry."
            )
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
    callback: Callable[[Event], Any] | Callable[[Event, Callable[[str], None]], Any]
    streaming: bool = False
    state: str = "queued"
    progress: int = 0


class JobManager(QObject):
    result = pyqtSignal(str, object)
    error = pyqtSignal(str, str)
    changed = pyqtSignal(str, str)
    progress = pyqtSignal(str, int)
    chunk = pyqtSignal(str, str)

    def __init__(self, max_workers: int = 2) -> None:
        super().__init__()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max_workers)
        self.signals = JobSignals(self)
        self.signals.finished.connect(self._finished)
        self.signals.failed.connect(self._failed)
        self.signals.cancelled.connect(self._cancelled)
        self.signals.chunk.connect(self._chunk)
        self.jobs: dict[str, Job] = {}
        self.generation = 0

    def submit(self, task_id: str, callback: Callable[[Event], Any]) -> bool:
        if task_id in self.jobs and self.jobs[task_id].state in ("queued", "running"):
            return False
        stop = Event()
        job = Job(task_id, self.generation, stop, callback, False, "running", 0)
        self.jobs[task_id] = job
        self.pool.start(_Task(task_id, job.generation, stop, callback, self.signals))
        self.changed.emit(task_id, "running")
        return True

    def submit_stream(
        self,
        task_id: str,
        callback: Callable[[Event, Callable[[str], None]], Any],
    ) -> bool:
        if task_id in self.jobs and self.jobs[task_id].state in ("queued", "running"):
            return False
        stop = Event()
        job = Job(task_id, self.generation, stop, callback, True, "running", 0)
        self.jobs[task_id] = job
        self.pool.start(_StreamingTask(task_id, job.generation, stop, callback, self.signals))
        self.changed.emit(task_id, "running")
        return True

    def set_progress(self, task_id: str, percent: int) -> bool:
        job = self.jobs.get(task_id)
        if job is None or job.state not in ("queued", "running", "cancelling"):
            return False
        bounded = max(0, min(100, int(percent)))
        job.progress = bounded
        self.progress.emit(task_id, bounded)
        return True

    def retry(self, task_id: str) -> bool:
        job = self.jobs.get(task_id)
        if job is None or job.state not in ("failed", "cancelled"):
            return False
        if job.streaming:
            callback = job.callback
            return self.submit_stream(task_id, callback)  # type: ignore[arg-type]
        callback = job.callback
        return self.submit(task_id, callback)  # type: ignore[arg-type]

    def cancel(self, task_id: str) -> None:
        if task_id in self.jobs:
            self.jobs[task_id].stop.set()
            self.changed.emit(task_id, "cancelling")

    def invalidate(self) -> None:
        self.generation += 1
        for task_id in list(self.jobs):
            self.cancel(task_id)

    def _current(self, task_id: str, generation: int) -> bool:
        return (
            generation == self.generation
            and task_id in self.jobs
            and self.jobs[task_id].generation == generation
        )

    def _finished(self, task_id: str, generation: int, value: object) -> None:
        if self._current(task_id, generation):
            self.jobs[task_id].state = "completed"
            self.jobs[task_id].progress = 100
            self.progress.emit(task_id, 100)
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

    def _chunk(self, task_id: str, generation: int, value: str) -> None:
        if self._current(task_id, generation):
            self.chunk.emit(task_id, value)
