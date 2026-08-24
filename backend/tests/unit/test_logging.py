from ima.infrastructure.observability.logging import redact


def test_redaction_is_recursive() -> None:
    value = {"user": {"name": "Ada", "apiKey": "secret"}, "items": [{"token": "x"}]}
    assert redact(value) == {
        "user": {"name": "Ada", "apiKey": "[REDACTED]"},
        "items": [{"token": "[REDACTED]"}],
    }
