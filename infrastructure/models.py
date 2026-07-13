"""SQLAlchemy persistence models shared by MySQL and repository tests."""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    loyalty_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="Standard")
    annual_spend: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00")
    )


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product: Mapped[str] = mapped_column(String(160), nullable=False)
    size: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="delivered")
    condition: Mapped[str] = mapped_column(String(30), nullable=False, default="unworn")
    has_receipt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_defective: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    refund_status: Mapped[str] = mapped_column(String(30), nullable=False, default="none")


class RefundRequest(Base):
    __tablename__ = "refund_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    reason_code: Mapped[str] = mapped_column(String(60), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class RefundEvent(Base):
    __tablename__ = "refund_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    refund_request_id: Mapped[str] = mapped_column(
        ForeignKey("refund_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class EscalationTicket(Base):
    __tablename__ = "escalation_tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    issue_summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


Index("ix_orders_customer_refund_status", Order.customer_id, Order.refund_status)
