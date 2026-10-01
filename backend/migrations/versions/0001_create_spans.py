"""Create the frozen spans schema.

Revision ID: 0001
Revises: none
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "spans",
        sa.Column("trace_id", sa.String(32), nullable=False),
        sa.Column("span_id", sa.String(16), nullable=False),
        sa.Column("parent_span_id", sa.String(16), nullable=True),
        sa.Column("service_name", sa.String(100), nullable=False),
        sa.Column("operation_name", sa.String(200), nullable=False),
        sa.Column("span_kind", sa.String(16), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_us", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column("error_message", sa.String(512), nullable=True),
        sa.Column(
            "attributes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("trace_id", "span_id", name="spans_pkey"),
        sa.CheckConstraint("duration_us >= 0", name="spans_duration_nonnegative"),
        sa.CheckConstraint(
            "span_kind IN ('SERVER', 'CLIENT', 'INTERNAL')", name="spans_kind_valid"
        ),
        sa.CheckConstraint("status IN ('OK', 'ERROR')", name="spans_status_valid"),
    )
    op.create_index("spans_start_time_idx", "spans", [sa.text("start_time DESC")])
    op.create_index("spans_service_trace_idx", "spans", ["service_name", "trace_id"])
    op.create_index("spans_status_trace_idx", "spans", ["status", "trace_id"])


def downgrade() -> None:
    op.drop_index("spans_status_trace_idx", table_name="spans")
    op.drop_index("spans_service_trace_idx", table_name="spans")
    op.drop_index("spans_start_time_idx", table_name="spans")
    op.drop_table("spans")
