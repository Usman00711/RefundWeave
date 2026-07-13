from datetime import date, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from infrastructure.models import Base, Customer, Order


def create_test_database(path) -> str:
    database_url = f"sqlite+pysqlite:///{path}"
    Base.metadata.create_all(create_engine(database_url))
    return database_url


def add_customer(
    database_url,
    *,
    customer_id=1,
    name="Alice Johnson",
    email="alice@example.com",
    tier="Standard",
):
    with Session(create_engine(database_url)) as session, session.begin():
        session.add(
            Customer(
                id=customer_id,
                name=name,
                email=email,
                phone="555-0101",
                loyalty_tier=tier,
                annual_spend=100,
            )
        )


def add_order(
    database_url,
    *,
    order_id="ORD-TEST",
    customer_id=1,
    days_ago=10,
    product="Everyday Runner",
    discount=0,
    status="delivered",
    condition="unworn",
    has_receipt=True,
    is_defective=False,
    refund_status="none",
    delivery_date=None,
):
    with Session(create_engine(database_url)) as session, session.begin():
        session.add(
            Order(
                order_id=order_id,
                customer_id=customer_id,
                product=product,
                size=9,
                price=99.99,
                discount_pct=discount,
                delivery_date=delivery_date or (date.today() - timedelta(days=days_ago)),
                status=status,
                condition=condition,
                has_receipt=has_receipt,
                is_defective=is_defective,
                refund_status=refund_status,
            )
        )


def get_order_status(database_url, order_id="ORD-TEST") -> str:
    with Session(create_engine(database_url)) as session:
        return session.scalar(select(Order.refund_status).where(Order.order_id == order_id))
