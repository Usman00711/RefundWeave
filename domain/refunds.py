"""Deterministic refund policy evaluation independent of the language model."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

RETURN_WINDOWS = {"Standard": 30, "Gold": 45, "Platinum": 60}


class DecisionOutcome(StrEnum):
    ELIGIBLE = "eligible"
    DENIED = "denied"
    REVIEW_REQUIRED = "review_required"


class RefundReason(StrEnum):
    ELIGIBLE_STANDARD = "eligible_standard"
    ELIGIBLE_DEFECT = "eligible_defect"
    ORDER_NOT_FOUND = "order_not_found"
    OWNERSHIP_MISMATCH = "ownership_mismatch"
    ALREADY_REFUNDED = "already_refunded"
    PREVIOUSLY_DENIED = "previously_denied"
    NOT_DELIVERED = "not_delivered"
    NO_PROOF_OF_PURCHASE = "no_proof_of_purchase"
    FINAL_SALE = "final_sale"
    CUSTOMIZED_ITEM = "customized_item"
    DEFECT_WINDOW_EXPIRED = "defect_window_expired"
    RETURN_WINDOW_EXPIRED = "return_window_expired"
    ITEM_NOT_UNWORN = "item_not_unworn"
    INVALID_DELIVERY_DATE = "invalid_delivery_date"
    FUTURE_DELIVERY_DATE = "future_delivery_date"


@dataclass(frozen=True)
class PolicyDecision:
    outcome: DecisionOutcome
    reason_code: RefundReason
    explanation: str
    order_id: str
    policy_rule: str | None = None
    product: str | None = None
    refund_amount: Decimal | None = None
    days_since_delivery: int | None = None
    return_window_days: int | None = None

    @property
    def eligible(self) -> bool:
        return self.outcome is DecisionOutcome.ELIGIBLE

    @property
    def requires_review(self) -> bool:
        return self.outcome is DecisionOutcome.REVIEW_REQUIRED


@dataclass(frozen=True)
class OrderPolicyFacts:
    order_id: str
    customer_name: str
    customer_email: str
    loyalty_tier: str
    product: str
    price: Decimal
    discount_pct: int
    delivery_date: date | str
    order_status: str
    condition: str
    has_receipt: bool
    is_defective: bool
    refund_status: str


def _denied(
    reason_code: RefundReason,
    explanation: str,
    order_id: str,
    *,
    policy_rule: str | None = None,
    product: str | None = None,
    refund_amount: Decimal | None = None,
    days_since_delivery: int | None = None,
    return_window_days: int | None = None,
) -> PolicyDecision:
    return PolicyDecision(
        outcome=DecisionOutcome.DENIED,
        reason_code=reason_code,
        explanation=explanation,
        order_id=order_id,
        policy_rule=policy_rule,
        product=product,
        refund_amount=refund_amount,
        days_since_delivery=days_since_delivery,
        return_window_days=return_window_days,
    )


def _review_required(
    reason_code: RefundReason,
    explanation: str,
    order_id: str,
    *,
    product: str | None = None,
    refund_amount: Decimal | None = None,
) -> PolicyDecision:
    return PolicyDecision(
        outcome=DecisionOutcome.REVIEW_REQUIRED,
        reason_code=reason_code,
        explanation=explanation,
        order_id=order_id,
        product=product,
        refund_amount=refund_amount,
    )


def evaluate_refund(
    facts: OrderPolicyFacts | None,
    *,
    order_id: str,
    customer_query: str,
    today: date | None = None,
) -> PolicyDecision:
    """Evaluate trusted order facts without database or language-model coupling."""
    normalized_order_id = order_id.strip().upper()
    normalized_customer = customer_query.strip()
    if facts is None:
        return _denied(
            RefundReason.ORDER_NOT_FOUND,
            "The order could not be found. Verify the customer details and Order ID.",
            normalized_order_id,
        )

    amount = Decimal(str(facts.price)).quantize(Decimal("0.01"))

    owns_order = normalized_customer.casefold() in {
        facts.customer_name.casefold(),
        facts.customer_email.casefold(),
    }
    if not owns_order:
        return _denied(
            RefundReason.OWNERSHIP_MISMATCH,
            "The supplied customer does not match this order.",
            facts.order_id,
        )

    common = {
        "order_id": facts.order_id,
        "product": facts.product,
        "refund_amount": amount,
    }
    if facts.refund_status == "approved":
        return _denied(
            RefundReason.ALREADY_REFUNDED,
            f"Order {facts.order_id} has already been refunded.",
            **common,
        )
    if facts.refund_status == "denied":
        return _denied(
            RefundReason.PREVIOUSLY_DENIED,
            f"Order {facts.order_id} was previously denied and may be escalated.",
            **common,
        )
    if facts.order_status != "delivered":
        return _review_required(
            RefundReason.NOT_DELIVERED,
            f"Order {facts.order_id} is not marked as delivered and requires review.",
            **common,
        )
    if not facts.has_receipt:
        return _denied(
            RefundReason.NO_PROOF_OF_PURCHASE,
            "No valid proof of purchase is on file.",
            policy_rule="3",
            **common,
        )
    if facts.discount_pct >= 20:
        return _denied(
            RefundReason.FINAL_SALE,
            f"'{facts.product}' was purchased at {facts.discount_pct}% discount and is Final Sale.",
            policy_rule="4",
            **common,
        )
    if "custom" in facts.product.casefold():
        return _denied(
            RefundReason.CUSTOMIZED_ITEM,
            f"'{facts.product}' is customized and cannot be returned.",
            policy_rule="9",
            **common,
        )

    try:
        delivery_date = (
            facts.delivery_date
            if isinstance(facts.delivery_date, date)
            else date.fromisoformat(facts.delivery_date)
        )
        days_since_delivery = ((today or date.today()) - delivery_date).days
    except (TypeError, ValueError):
        return _review_required(
            RefundReason.INVALID_DELIVERY_DATE,
            "The order delivery date is invalid and requires human review.",
            **common,
        )
    if days_since_delivery < 0:
        return _review_required(
            RefundReason.FUTURE_DELIVERY_DATE,
            "The order delivery date is in the future and requires human review.",
            **common,
        )

    if facts.is_defective:
        if days_since_delivery <= 90:
            return PolicyDecision(
                outcome=DecisionOutcome.ELIGIBLE,
                reason_code=RefundReason.ELIGIBLE_DEFECT,
                explanation=(
                    f"'{facts.product}' has a reported manufacturing defect within the 90-day window."
                ),
                policy_rule="5",
                days_since_delivery=days_since_delivery,
                **common,
            )
        return _denied(
            RefundReason.DEFECT_WINDOW_EXPIRED,
            f"The defect was reported {days_since_delivery} days after delivery.",
            policy_rule="5",
            days_since_delivery=days_since_delivery,
            **common,
        )

    return_window = RETURN_WINDOWS.get(facts.loyalty_tier, 30)
    timing = {
        "days_since_delivery": days_since_delivery,
        "return_window_days": return_window,
    }
    if days_since_delivery > return_window:
        return _denied(
            RefundReason.RETURN_WINDOW_EXPIRED,
            f"The {facts.loyalty_tier} return window is {return_window} days; this request is day "
            f"{days_since_delivery}.",
            policy_rule="1 & 6",
            **common,
            **timing,
        )
    if facts.condition != "unworn":
        return _denied(
            RefundReason.ITEM_NOT_UNWORN,
            f"'{facts.product}' is recorded as {facts.condition}; eligible items must be unworn.",
            policy_rule="2",
            **common,
            **timing,
        )

    return PolicyDecision(
        outcome=DecisionOutcome.ELIGIBLE,
        reason_code=RefundReason.ELIGIBLE_STANDARD,
        explanation=(
            f"'{facts.product}' meets all criteria within the {return_window}-day "
            f"{facts.loyalty_tier} return window."
        ),
        policy_rule="1, 2, 3, 4 & 6",
        **common,
        **timing,
    )
