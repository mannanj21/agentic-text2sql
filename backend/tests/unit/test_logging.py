import json
import logging
from io import StringIO

from app.logging import (
    JSONFormatter,
    redact_dict,
    redact_string,
    request_id_ctx,
    run_id_ctx,
)


def test_redact_string() -> None:
    dsn = "postgresql+asyncpg://app:supersecret123@localhost:5432/text2sql"
    redacted = redact_string(dsn)
    assert "supersecret123" not in redacted
    assert "app:***@localhost" in redacted

    # Non-sensitive string
    assert redact_string("hello world") == "hello world"


def test_redact_dict() -> None:
    data = {
        "user": "alice",
        "password": "my_password",
        "api_key": "sk-12345",
        "nested": {
            "token": "secret_token",
            "safe": "data",
        },
        "list_of_secrets": [{"cookie": "session_id_123"}, "plain_string"],
    }

    redacted = redact_dict(data)

    assert redacted["user"] == "alice"
    assert redacted["password"] == "***"  # noqa: S105
    assert redacted["api_key"] == "***"
    assert redacted["nested"]["token"] == "***"  # noqa: S105
    assert redacted["nested"]["safe"] == "data"
    assert redacted["list_of_secrets"][0]["cookie"] == "***"
    assert redacted["list_of_secrets"][1] == "plain_string"


def test_json_formatter() -> None:
    # Setup capturing log stream
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())

    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    # Set context vars
    req_token = request_id_ctx.set("req-123")
    run_token = run_id_ctx.set("run-456")

    try:
        # Log with extra args containing secrets and DSN in message
        logger.info(
            "Connecting to postgresql://user:pass@localhost:5432",
            extra={"api_key": "secret", "count": 5},
        )

        output = stream.getvalue()
        log_data = json.loads(output)

        assert log_data["level"] == "INFO"
        assert log_data["name"] == "test_logger"
        assert "pass" not in log_data["message"]
        assert "user:***@localhost" in log_data["message"]

        assert log_data["request_id"] == "req-123"
        assert log_data["run_id"] == "run-456"

        assert log_data["extra"]["count"] == 5
        assert log_data["extra"]["api_key"] == "***"

    finally:
        # Cleanup
        logger.removeHandler(handler)
        request_id_ctx.reset(req_token)
        run_id_ctx.reset(run_token)
