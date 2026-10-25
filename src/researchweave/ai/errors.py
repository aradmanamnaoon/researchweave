from __future__ import annotations


class AIError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds
