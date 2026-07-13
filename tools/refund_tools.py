from langchain_core.tools import tool

from application.support_service import RefundActionStatus, SupportService
from infrastructure.database import get_database_url
from tools.policy_tools import format_policy_decision

SUPPORT_DATABASE_URL = get_database_url()


@tool
def process_refund(customer_query: str, order_id: str) -> str:
    """
    Process a refund after independently verifying ownership and eligibility.
    The operation is transactional and safe to retry.
    """
    result = SupportService(SUPPORT_DATABASE_URL).process_refund(
        customer_query=customer_query,
        order_id=order_id,
    )
    decision = result.decision
    if result.status is RefundActionStatus.BLOCKED:
        return f"REFUND BLOCKED ✗\n{format_policy_decision(decision)}"

    return (
        f"REFUND APPROVED ✓\n"
        f"  Order: {decision.order_id} — {decision.product}\n"
        f"  Amount: ${decision.refund_amount:.2f}\n"
        f"  Policy Decision: {decision.reason_code.value}\n"
        f"  The refund of ${decision.refund_amount:.2f} will be returned to the original payment method "
        f"within 5–7 business days."
    )


@tool
def deny_refund(customer_query: str, order_id: str) -> str:
    """
    Record a denial after independently verifying ownership and ineligibility.
    The language model cannot supply or override the policy reason.
    """
    result = SupportService(SUPPORT_DATABASE_URL).deny_refund(
        customer_query=customer_query,
        order_id=order_id,
    )
    decision = result.decision
    if result.status is RefundActionStatus.BLOCKED:
        prefix = "DENIAL BLOCKED" if decision.eligible else "DENIAL NOT RECORDED"
        return f"{prefix} ✗\n{format_policy_decision(decision)}"
    if decision.reason_code.value == "previously_denied":
        return f"REFUND ALREADY DENIED\n{format_policy_decision(decision)}"

    return (
        f"REFUND DENIED ✗\n"
        f"  Order: {decision.order_id} — {decision.product}\n"
        f"  Reason Code: {decision.reason_code.value}\n"
        f"  Reason: {decision.explanation}\n"
        f"  If you believe this decision is incorrect, you may request escalation "
        f"to a human supervisor who will review your case within 24 hours."
    )


@tool
def escalate_to_human(customer_query: str, order_id: str, issue_summary: str) -> str:
    """
    Escalate a disputed refund case to a human supervisor.
    Use when the customer disputes a denial or the case is too complex to resolve automatically.
    """
    result = SupportService(SUPPORT_DATABASE_URL).escalate(
        customer_query=customer_query,
        order_id=order_id,
        issue_summary=issue_summary,
    )
    decision = result.decision
    if not result.created:
        return f"ESCALATION BLOCKED ✗\n{format_policy_decision(result.decision)}"

    return (
        f"ESCALATED TO SUPERVISOR ⚡\n"
        f"  Order: {decision.order_id}\n"
        f"  Ticket: {result.ticket_id}\n"
        f"  Issue: {issue_summary}\n"
        f"  A Sole Syntax supervisor will review this case and contact the customer "
        f"via email within 24 hours. Reference this ticket for follow-up."
    )
