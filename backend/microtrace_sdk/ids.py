import re
import secrets


def valid_id(value: str, length: int) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None
        and value != "0" * length
    )


def _random_id(byte_count: int) -> str:
    while True:
        value = secrets.token_hex(byte_count)
        if value != "0" * (byte_count * 2):
            return value


def new_trace_id() -> str:
    return _random_id(16)


def new_span_id() -> str:
    return _random_id(8)
