import hashlib
import hmac
import time

from app.services.webhooks import verify_hmac_signature


def signature(body: bytes, secret: str, timestamp: str) -> str:
    digest = hmac.new(
        secret.encode(),
        timestamp.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def test_hmac_accepts_valid_recent_signature(monkeypatch) -> None:
    timestamp = "1760000000"
    monkeypatch.setattr(time, "time", lambda: float(timestamp))

    assert verify_hmac_signature(
        body=b'{"event_id":"event-1"}',
        signature=signature(b'{"event_id":"event-1"}', "test-secret", timestamp),
        timestamp=timestamp,
        secret="test-secret",
        max_clock_skew_seconds=300,
    )


def test_hmac_rejects_tampered_body(monkeypatch) -> None:
    timestamp = "1760000000"
    monkeypatch.setattr(time, "time", lambda: float(timestamp))

    assert not verify_hmac_signature(
        body=b'{"event_id":"event-2"}',
        signature=signature(b'{"event_id":"event-1"}', "test-secret", timestamp),
        timestamp=timestamp,
        secret="test-secret",
        max_clock_skew_seconds=300,
    )


def test_hmac_rejects_expired_and_missing_signatures(monkeypatch) -> None:
    timestamp = "1760000000"
    monkeypatch.setattr(time, "time", lambda: float(timestamp) + 301)
    body = b'{"event_id":"event-1"}'

    assert not verify_hmac_signature(
        body=body,
        signature=signature(body, "test-secret", timestamp),
        timestamp=timestamp,
        secret="test-secret",
        max_clock_skew_seconds=300,
    )
    assert not verify_hmac_signature(
        body=body,
        signature=None,
        timestamp=timestamp,
        secret="test-secret",
        max_clock_skew_seconds=300,
    )
