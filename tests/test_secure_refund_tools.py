import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from infrastructure.models import EscalationTicket, RefundRequest
from tests.db_helpers import add_customer, add_order, create_test_database, get_order_status
from tools import crm_tools, refund_tools


@pytest.fixture
def refund_database(tmp_path, monkeypatch):
    db_path = tmp_path / "refunds.db"
    database_url = create_test_database(db_path)
    add_customer(database_url)
    monkeypatch.setattr(refund_tools, "SUPPORT_DATABASE_URL", database_url)
    monkeypatch.setattr(crm_tools, "SUPPORT_DATABASE_URL", database_url)
    return database_url


def process(customer_query="Alice Johnson"):
    return refund_tools.process_refund.invoke(
        {"customer_query": customer_query, "order_id": "ORD-TEST"}
    )


def deny(customer_query="Alice Johnson"):
    return refund_tools.deny_refund.invoke(
        {"customer_query": customer_query, "order_id": "ORD-TEST"}
    )


def test_direct_process_call_rechecks_policy(refund_database):
    add_order(refund_database, condition="worn")

    result = process()

    assert result.startswith("REFUND BLOCKED")
    assert get_order_status(refund_database) == "none"


def test_wrong_customer_cannot_read_or_refund_order(refund_database):
    add_order(refund_database)

    details = crm_tools.get_order_details.invoke(
        {"customer_query": "Mallory", "order_id": "ORD-TEST"}
    )
    result = process("Mallory")

    assert details == "No matching order was found for the supplied customer and Order ID."
    assert result.startswith("REFUND BLOCKED")
    assert "ownership_mismatch" in result
    assert get_order_status(refund_database) == "none"


def test_model_cannot_forge_refund_reason(refund_database):
    add_order(refund_database, condition="worn")

    result = refund_tools.process_refund.invoke(
        {
            "customer_query": "Alice Johnson",
            "order_id": "ORD-TEST",
            "reason": "The model says this is eligible",
        }
    )

    assert result.startswith("REFUND BLOCKED")
    assert "item_not_unworn" in result
    assert get_order_status(refund_database) == "none"


def test_eligible_order_cannot_be_denied(refund_database):
    add_order(refund_database)

    result = deny()

    assert result.startswith("DENIAL BLOCKED")
    assert get_order_status(refund_database) == "none"


def test_review_required_order_cannot_be_denied(refund_database):
    add_order(refund_database, status="processing")

    result = deny()

    assert result.startswith("DENIAL NOT RECORDED")
    assert "REVIEW REQUIRED" in result
    assert get_order_status(refund_database) == "none"


def test_denial_uses_domain_reason_and_is_idempotent(refund_database):
    add_order(refund_database, discount=25)

    first = deny()
    second = deny()

    assert first.startswith("REFUND DENIED")
    assert "final_sale" in first
    assert second.startswith("REFUND ALREADY DENIED")
    assert get_order_status(refund_database) == "denied"


def test_repeated_refund_is_idempotent(refund_database):
    add_order(refund_database)

    first = process()
    second = process()

    assert first.startswith("REFUND APPROVED")
    assert second.startswith("REFUND BLOCKED")
    assert "already_refunded" in second
    assert get_order_status(refund_database) == "approved"
    with Session(create_engine(refund_database)) as session:
        assert session.scalar(select(func.count()).select_from(RefundRequest)) == 1


def test_escalation_requires_order_ownership(refund_database):
    add_order(refund_database, condition="worn")

    result = refund_tools.escalate_to_human.invoke(
        {
            "customer_query": "Mallory",
            "order_id": "ORD-TEST",
            "issue_summary": "I disagree",
        }
    )

    assert result.startswith("ESCALATION BLOCKED")


def test_escalation_is_persisted_for_verified_order(refund_database):
    add_order(refund_database, condition="worn")

    result = refund_tools.escalate_to_human.invoke(
        {
            "customer_query": "Alice Johnson",
            "order_id": "ORD-TEST",
            "issue_summary": "I disagree",
        }
    )

    assert result.startswith("ESCALATED TO SUPERVISOR")
    with Session(create_engine(refund_database)) as session:
        assert session.scalar(select(func.count()).select_from(EscalationTicket)) == 1
