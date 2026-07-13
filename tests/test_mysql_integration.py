import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from application.support_service import RefundActionStatus, SupportService
from data.seed_db import seed
from infrastructure.models import Order, RefundEvent, RefundRequest

pytestmark = pytest.mark.mysql


@pytest.fixture
def mysql_database(monkeypatch):
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    monkeypatch.setenv("SOLE_SYNTAX_DATABASE_URL", database_url)
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    seed(reset=True, database_url=database_url)
    try:
        yield database_url
    finally:
        seed(reset=True, database_url=database_url)


def test_mysql_migration_creates_expected_schema(mysql_database):
    tables = set(inspect(create_engine(mysql_database)).get_table_names())

    assert {
        "alembic_version",
        "customers",
        "orders",
        "refund_requests",
        "refund_events",
        "escalation_tickets",
    }.issubset(tables)


def test_mysql_row_lock_and_idempotency_allow_one_refund(mysql_database):
    service = SupportService(mysql_database)

    def process_refund(_index):
        return service.process_refund(customer_query="Alice Johnson", order_id="ORD-001")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(process_refund, range(2)))

    assert sum(result.status is RefundActionStatus.APPROVED for result in results) == 1
    assert sum(result.status is RefundActionStatus.BLOCKED for result in results) == 1

    with Session(create_engine(mysql_database)) as session:
        order_status = session.scalar(
            select(Order.refund_status).where(Order.order_id == "ORD-001")
        )
        request_count = session.scalar(select(func.count()).select_from(RefundRequest))
        event_count = session.scalar(select(func.count()).select_from(RefundEvent))

    assert order_status == "approved"
    assert request_count == 1
    assert event_count == 1
