from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB

# Alembic owns schema creation. This mapping never creates tables during app startup.
metadata = MetaData()
spans = Table(
    "spans",
    metadata,
    Column("trace_id", String(32), primary_key=True),
    Column("span_id", String(16), primary_key=True),
    Column("parent_span_id", String(16)),
    Column("service_name", String(100), nullable=False),
    Column("operation_name", String(200), nullable=False),
    Column("span_kind", String(16), nullable=False),
    Column("start_time", DateTime(timezone=True), nullable=False),
    Column("end_time", DateTime(timezone=True), nullable=False),
    Column("duration_us", BigInteger, nullable=False),
    Column("status", String(16), nullable=False),
    Column("error_type", String(128)),
    Column("error_message", String(512)),
    Column("attributes", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True)),
)
