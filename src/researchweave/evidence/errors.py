"""Public, structured errors for the headless evidence domain."""

from __future__ import annotations


class EvidenceError(Exception):
    """Domain failure with a stable wire code and actionable explanation."""

    def __init__(self, code: str, message: str, recovery: str) -> None:
        super().__init__(message)
        self.code = code
        self.recovery = recovery

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self), "recovery": self.recovery}


def require(condition: bool, message: str, code: str = "INVALID_INPUT") -> None:
    if not condition:
        raise EvidenceError(code, message, "Correct the input and retry.")
