"""Identificadores UUIDv7 (RFC 9562): ordenables en el tiempo y no enumerables."""

import secrets
import time
import uuid

_MASK_48 = (1 << 48) - 1


def uuid7() -> uuid.UUID:
    unix_ms = time.time_ns() // 1_000_000
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    value = (unix_ms & _MASK_48) << 80 | 0x7 << 76 | rand_a << 64 | 0b10 << 62 | rand_b
    return uuid.UUID(int=value)
