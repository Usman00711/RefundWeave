"""Create customer support schema.

Revision ID: 20260714_0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("loyalty_tier", sa.String(length=20), nullable=False),
        sa.Column("annual_spend", sa.Numeric(12, 2), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_customers"),
        sa.UniqueConstraint("email", name="uq_customers_email"),
    )
    op.create_index("ix_customers_name", "customers", ["name"])

    op.create_table(
        "orders",
        sa.Column("order_id", sa.String(length=40), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("product", sa.String(length=160), nullable=False),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_pct", sa.Integer(), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("condition", sa.String(length=30), nullable=False),
        sa.Column("has_receipt", sa.Boolean(), nullable=False),
        sa.Column("is_defective", sa.Boolean(), nullable=False),
        sa.Column("refund_status", sa.String(length=30), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["customers.id"],
            name="fk_orders_customer_id_customers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("order_id", name="pk_orders"),
    )
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index(
        "ix_orders_customer_refund_status", "orders", ["customer_id", "refund_status"]
    )

    op.create_table(
        "refund_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("reason_code", sa.String(length=60), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.order_id"],
            name="fk_refund_requests_order_id_orders",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refund_requests"),
        sa.UniqueConstraint("idempotency_key", name="uq_refund_requests_idempotency_key"),
    )
    op.create_index("ix_refund_requests_order_id", "refund_requests", ["order_id"])

    op.create_table(
        "refund_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("refund_request_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["refund_request_id"],
            ["refund_requests.id"],
            name="fk_refund_events_refund_request_id_refund_requests",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_refund_events"),
    )
    op.create_index(
        "ix_refund_events_refund_request_id", "refund_events", ["refund_request_id"]
    )

    op.create_table(
        "escalation_tickets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=40), nullable=False),
        sa.Column("issue_summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.order_id"],
            name="fk_escalation_tickets_order_id_orders",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_escalation_tickets"),
    )
    op.create_index("ix_escalation_tickets_order_id", "escalation_tickets", ["order_id"])


def downgrade() -> None:
    op.drop_table("escalation_tickets")
    op.drop_table("refund_events")
    op.drop_table("refund_requests")
    op.drop_table("orders")
    op.drop_table("customers")
