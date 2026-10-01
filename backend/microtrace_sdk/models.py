import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from microtrace_sdk.ids import valid_id

Scalar = str | int | float | bool | None
ALLOWED_ATTRIBUTES = frozenset(
    {"http.method", "http.route", "http.status_code", "peer.service", "demo.scenario", "order.id"}
)


class SpanKind(StrEnum):
    SERVER = "SERVER"
    CLIENT = "CLIENT"
    INTERNAL = "INTERNAL"


class SpanStatus(StrEnum):
    OK = "OK"
    ERROR = "ERROR"


@dataclass(frozen=True)
class SpanContext:
    trace_id: str
    span_id: str
    trace_flags: str = "01"

    def __post_init__(self) -> None:
        if not valid_id(self.trace_id, 32) or not valid_id(self.span_id, 16):
            raise ValueError("Invalid trace/span identity")
        if (
            not isinstance(self.trace_flags, str)
            or re.fullmatch(r"[0-9a-f]{2}", self.trace_flags) is None
        ):
            raise ValueError("Invalid trace flags")


def validate_attributes(attributes: dict[str, Scalar]) -> dict[str, Scalar]:
    if len(attributes) > 16:
        raise ValueError("At most 16 attributes are allowed")
    for key, value in attributes.items():
        if not isinstance(key, str) or len(key) > 64 or key not in ALLOWED_ATTRIBUTES:
            raise ValueError("Attribute key is not allowed")
        if type(value) not in (str, int, float, bool, type(None)):
            raise ValueError("Attribute values must be JSON scalars")
        if isinstance(value, str) and len(value) > 256:
            raise ValueError("Attribute string is too long")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Attribute number must be finite")
    return dict(attributes)


class FinishedSpan(BaseModel):
    """Completed telemetry snapshot; internal clocks and flags are never exported."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    trace_id: str
    span_id: str
    parent_span_id: str | None
    service_name: str = Field(min_length=1, max_length=100)
    operation_name: str = Field(min_length=1, max_length=200)
    span_kind: SpanKind
    start_time: datetime
    end_time: datetime
    duration_us: int = Field(ge=0, le=9223372036854775807)
    status: SpanStatus
    error_type: str | None = Field(max_length=128)
    error_message: str | None = Field(max_length=512)
    attributes: Mapping[str, Scalar]

    @field_validator("trace_id", "span_id", "parent_span_id")
    @classmethod
    def identifiers(cls, value: str | None, info) -> str | None:
        if value is None and info.field_name == "parent_span_id":
            return value
        if not valid_id(value, 32 if info.field_name == "trace_id" else 16):
            raise ValueError("Invalid identifier")
        return value

    @field_validator("attributes", mode="before")
    @classmethod
    def attributes_valid(cls, value):
        if not isinstance(value, Mapping):
            raise ValueError("Attributes must be an object")
        return validate_attributes(value)

    @field_validator("attributes")
    @classmethod
    def immutable_attributes(cls, value):
        return MappingProxyType(dict(value))

    @field_serializer("attributes")
    def serialize_attributes(self, value):
        return dict(value)

    @model_validator(mode="after")
    def timing_valid(self):
        for timestamp in (self.start_time, self.end_time):
            if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds() != 0:
                raise ValueError("Timestamps must be timezone-aware UTC")
        if self.end_time < self.start_time:
            raise ValueError("End time must not precede start time")
        return self
