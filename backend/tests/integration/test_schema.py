"""Read-only validation of an explicitly migrated real PostgreSQL database."""

import os

import pytest
from sqlalchemy import create_engine, inspect

pytestmark = pytest.mark.integration


def test_frozen_postgresql_schema():
    url = os.environ.get("MICROTRACE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set MICROTRACE_TEST_DATABASE_URL to a migrated PostgreSQL test database")
    engine = create_engine(url)
    try:
        assert engine.dialect.name == "postgresql"
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == {"spans", "alembic_version"}
        columns = {column["name"]: column for column in inspector.get_columns("spans")}
        expected = {
            "trace_id": ("VARCHAR(32)", False),
            "span_id": ("VARCHAR(16)", False),
            "parent_span_id": ("VARCHAR(16)", True),
            "service_name": ("VARCHAR(100)", False),
            "operation_name": ("VARCHAR(200)", False),
            "span_kind": ("VARCHAR(16)", False),
            "start_time": ("TIMESTAMP", False),
            "end_time": ("TIMESTAMP", False),
            "duration_us": ("BIGINT", False),
            "status": ("VARCHAR(16)", False),
            "error_type": ("VARCHAR(128)", True),
            "error_message": ("VARCHAR(512)", True),
            "attributes": ("JSONB", False),
            "created_at": ("TIMESTAMP", False),
        }
        assert {name: (str(c["type"]), c["nullable"]) for name, c in columns.items()} == expected
        for name in ("start_time", "end_time", "created_at"):
            assert columns[name]["type"].timezone is True
        assert columns["attributes"]["default"] == "'{}'::jsonb"
        assert columns["created_at"]["default"] == "now()"
        assert inspector.get_pk_constraint("spans")["constrained_columns"] == [
            "trace_id",
            "span_id",
        ]
        assert inspector.get_foreign_keys("spans") == []
        checks = {c["name"] for c in inspector.get_check_constraints("spans")}
        assert checks == {"spans_duration_nonnegative", "spans_kind_valid", "spans_status_valid"}
        indexes = {i["name"]: i for i in inspector.get_indexes("spans")}
        assert set(indexes) == {
            "spans_start_time_idx",
            "spans_service_trace_idx",
            "spans_status_trace_idx",
        }
        assert indexes["spans_service_trace_idx"]["column_names"] == ["service_name", "trace_id"]
        assert indexes["spans_status_trace_idx"]["column_names"] == ["status", "trace_id"]
        assert indexes["spans_start_time_idx"]["column_sorting"] == {"start_time": ("desc",)}
    finally:
        engine.dispose()
