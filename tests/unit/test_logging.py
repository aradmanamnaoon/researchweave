import logging
from unittest.mock import Mock

from researchweave.app.logging import log_event


def test_secret_redaction() -> None:
    logger = Mock(spec=logging.Logger)
    log_event(logger, "test", api_key="top-secret", count=4)
    message = logger.info.call_args.args[0]
    assert "top-secret" not in message
    assert "[REDACTED]" in message
    assert '"count": "4"' in message
