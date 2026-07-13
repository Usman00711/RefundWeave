from langchain_core.tools import tool

from application.support_service import SupportService
from domain.refunds import PolicyDecision
from infrastructure.database import get_database_url

SUPPORT_DATABASE_URL = get_database_url()


def format_policy_decision(decision: PolicyDecision) -> str:
    """Format a typed decision for the language model and activity UI."""
    if decision.eligible:
        label = "ELIGIBLE"
    elif decision.requires_review:
        label = "REVIEW REQUIRED"
    else:
        label = "DENIED"
    rule = f" — Policy Rule {decision.policy_rule}" if decision.policy_rule else ""
    details = [
        f"{label}{rule}: {decision.explanation}",
        f"  Reason Code: {decision.reason_code.value}",
    ]
    if decision.refund_amount is not None:
        details.append(f"  Refund Amount: ${decision.refund_amount:.2f}")
    if decision.days_since_delivery is not None:
        details.append(f"  Days Since Delivery: {decision.days_since_delivery}")
    return "\n".join(details)


@tool
def check_refund_eligibility(customer_query: str, order_id: str) -> str:
    """
    Validate whether an order is eligible for a refund based on Sole Syntax policy.
    Returns a detailed eligibility verdict with the specific rule that applies.
    """
    decision = SupportService(SUPPORT_DATABASE_URL).evaluate_refund(
        order_id=order_id,
        customer_query=customer_query,
    )
    return format_policy_decision(decision)
