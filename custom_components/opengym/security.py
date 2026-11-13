"""Signature verification for openGym webhooks.

openGym sends `X-OpenGym-Signature: t=<unix seconds>,v1=<hex>` where the hex is
HMAC-SHA256 over `<t>.<raw body>` with the webhook's signing secret.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time

from .const import SIGNATURE_MAX_AGE

_SIG_RE = re.compile(r"^t=(\d+),v1=([0-9a-f]{64})$")


def verify_signature(secret: str, raw_body: bytes, header: str) -> bool:
    """Return True if the signature header is valid for the raw body."""
    match = _SIG_RE.fullmatch(header or "")
    if not match:
        return False
    timestamp = int(match.group(1))
    if abs(time.time() - timestamp) > SIGNATURE_MAX_AGE:
        return False
    wanted = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(wanted, match.group(2))
