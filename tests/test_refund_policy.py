from dataclasses import replace

import pytest

from domain.refunds import RefundReason, evaluate_refund
from infrastructure.database import get_session_factory
from infrastructure.repositories import SupportRepository
from tests.db_helpers import add_customer, add_order, create_test_database
from tools import policy_tools


@pytest.fixture
def policy_database(tmp_path, monkeypatch):
    db_path = tmp_path / "policy.db"
    database_url = create_test_database(db_path)
    monkeypatch.setattr(policy_tools, "SUPPORT_DATABASE_URL", database_url)
    return database_url


def verdict(order_id="ORD-TEST", customer_query="Alice Johnson"):
    return policy_tools.check_refund_eligibility.invoke(
        {"customer_query": customer_query, "order_id": order_id}
    )


@pytest.mark.parametrize(
    ("tier", "days_ago", "expected"),
    [
        ("Standard", 30, "ELIGIBLE"),
        ("Standard", 31, "DENIED"),
        ("Gold", 45, "ELIGIBLE"),
        ("Gold", 46, "DENIED"),
        ("Platinum", 60, "ELIGIBLE"),
        ("Platinum", 61, "DENIED"),
    ],
)
def test_loyalty_return_window_boundaries(policy_database, tier, days_ago, expected):
    add_customer(policy_database, tier=tier)
    add_order(policy_database, days_ago=days_ago)

    assert verdict().startswith(expected)


@pytest.mark.parametrize(
    ("overrides", "rule"),
    [
        ({"has_receipt": False}, "Policy Rule 3"),
        ({"discount": 20}, "Policy Rule 4"),
        ({"product": "Custom Kicks"}, "Policy Rule 9"),
        ({"condition": "worn"}, "Policy Rule 2"),
    ],
)
def test_hard_denial_rules(policy_database, overrides, rule):
    add_customer(policy_database)
    add_order(policy_database, **overrides)

    result = verdict()

    assert result.startswith("DENIED")
    assert rule in result


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [(90, "ELIGIBLE"), (91, "DENIED")],
)
def test_defect_window_boundary(policy_database, days_ago, expected):
    add_customer(policy_database)
    add_order(policy_database, days_ago=days_ago, is_defective=True)

    assert verdict().startswith(expected)


@pytest.mark.parametrize("refund_status", ["approved", "denied"])
def test_previous_refund_decision_is_denied(policy_database, refund_status):
    add_customer(policy_database)
    add_order(policy_database, refund_status=refund_status)

    assert verdict().startswith("DENIED")


def test_unknown_order_returns_safe_failure(policy_database):
    result = verdict("ORD-MISSING")

    assert result.startswith("DENIED")
    assert RefundReason.ORDER_NOT_FOUND.value in result


def test_customer_must_own_order(policy_database):
    add_customer(policy_database)
    add_order(policy_database)

    result = verdict(customer_query="Mallory")

    assert result.startswith("DENIED")
    assert RefundReason.OWNERSHIP_MISMATCH.value in result


def test_domain_returns_typed_policy_decision(policy_database):
    add_customer(policy_database, tier="Gold")
    add_order(policy_database, days_ago=45)

    with get_session_factory(policy_database)() as session:
        facts = SupportRepository(session).get_policy_facts(order_id="ORD-TEST")
        decision = evaluate_refund(
            facts,
            order_id="ORD-TEST",
            customer_query="alice@example.com",
        )

    assert decision.eligible is True
    assert decision.reason_code is RefundReason.ELIGIBLE_STANDARD
    assert decision.return_window_days == 45


def test_order_must_be_delivered(policy_database):
    add_customer(policy_database)
    add_order(policy_database, status="processing")

    result = verdict()

    assert result.startswith("REVIEW REQUIRED")
    assert RefundReason.NOT_DELIVERED.value in result


def test_invalid_delivery_date_requires_review(policy_database):
    add_customer(policy_database)
    add_order(policy_database)

    with get_session_factory(policy_database)() as session:
        facts = SupportRepository(session).get_policy_facts(order_id="ORD-TEST")
    invalid_facts = replace(facts, delivery_date="not-a-date")
    decision = evaluate_refund(
        invalid_facts,
        order_id="ORD-TEST",
        customer_query="Alice Johnson",
    )

    assert decision.requires_review
    assert decision.reason_code is RefundReason.INVALID_DELIVERY_DATE


def test_future_delivery_date_requires_review(policy_database):
    add_customer(policy_database)
    add_order(policy_database, days_ago=-1)

    result = verdict()

    assert result.startswith("REVIEW REQUIRED")
    assert RefundReason.FUTURE_DELIVERY_DATE.value in result
