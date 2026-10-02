import hashlib
import hmac
import time

from app.core.errors import ServiceError
from app.core.settings import Settings


def verify_hmac_signature(
    *,
    body: bytes,
    signature: str | None,
    timestamp: str | None,
    secret: str | None,
    max_clock_skew_seconds: int,
) -> bool:
    if not signature or not timestamp or not secret:
        return False
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - sent_at) > max_clock_skew_seconds:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    supplied = signature.removeprefix("sha256=").strip().lower()
    return hmac.compare_digest(expected, supplied)


def require_webhook_hmac(
    *,
    body: bytes,
    signature: str | None,
    timestamp: str | None,
    secret: str | None,
    settings: Settings,
) -> None:
    if not verify_hmac_signature(
        body=body,
        signature=signature,
        timestamp=timestamp,
        secret=secret,
        max_clock_skew_seconds=settings.webhook_max_clock_skew_seconds,
    ):
        raise ServiceError(
            "invalid_webhook_signature", "Webhook HMAC signature is invalid or expired.", 401
        )
