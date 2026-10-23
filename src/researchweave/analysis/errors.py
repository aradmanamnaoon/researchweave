"""Stable, machine-readable domain errors without sensitive payload leakage."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(eq=False)
class AnalysisError(Exception):
    code: str
    message: str
    recovery: str = "Review the arguments and try again."

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def require(condition: bool, message: str, code: str = "INVALID_INPUT") -> None:
    if not condition:
        raise AnalysisError(code, message)
