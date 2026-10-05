import time

from app.core.ids import uuid7


def test_uuid7_version_and_variant() -> None:
    value = uuid7()
    assert value.version == 7
    assert value.variant == "specified in RFC 4122"


def test_uuid7_is_time_ordered() -> None:
    first = uuid7()
    time.sleep(0.002)
    second = uuid7()
    assert first < second
