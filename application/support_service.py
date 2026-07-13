"""Typed support operations backed by SQLAlchemy repositories."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import inspect
from sqlalchemy.orm import Session, sessionmaker

from domain.refunds import PolicyDecision, RefundReason, evaluate_refund
from infrastructure.database import get_session_factory
from infrastructure.models import EscalationTicket, RefundEvent, RefundRequest
from infrastructure.repositories import SupportRepository


@dataclass(frozen=True)
class CustomerRecord:
    id: int
    name: str
    email: str
    phone: str | None
    loyalty_tier: str
    annual_spend: Decimal


@dataclass(frozen=True)
class OrderRecord:
    order_id: str
    customer_name: str
    customer_email: str
    loyalty_tier: str
    product: str
    size: int | None
    price: Decimal
    discount_pct: int
    delivery_date: str
    status: str
    condition: str
    has_receipt: bool
    is_defective: bool
    refund_status: str


class RefundActionStatus(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class RefundActionResult:
    status: RefundActionStatus
    decision: PolicyDecision
    message: str


@dataclass(frozen=True)
class EscalationResult:
    created: bool
    decision: PolicyDecision
    ticket_id: str | None


class SupportService:
    """Expose business operations without coupling callers to a database vendor."""

    def __init__(
        self,
        database_url: str,
        *,
        session_factory: sessionmaker[Session] | None = None,
    ):
        self.database_url = database_url
        self.session_factory = session_factory or get_session_factory(database_url)

    def is_ready(self) -> bool:
        engine = self.session_factory.kw["bind"]
        tables = set(inspect(engine).get_table_names())
        return {
            "customers",
            "orders",
            "refund_requests",
            "refund_events",
            "escalation_tickets",
        }.issubset(tables)

    def lookup_customer(self, query: str) -> CustomerRecord | None:
        with self.session_factory() as session:
            customer = SupportRepository(session).lookup_customer(query)
            if customer is None:
                return None
            return CustomerRecord(
                id=customer.id,
                name=customer.name,
                email=customer.email,
                phone=customer.phone,
                loyalty_tier=customer.loyalty_tier,
                annual_spend=customer.annual_spend,
            )

    def get_order(self, *, customer_query: str, order_id: str) -> OrderRecord | None:
        with self.session_factory() as session:
            row = SupportRepository(session).get_owned_order(
                customer_query=customer_query,
                order_id=order_id,
            )
            if row is None:
                return None
            order, customer = row
            return OrderRecord(
                order_id=order.order_id,
                customer_name=customer.name,
                customer_email=customer.email,
                loyalty_tier=customer.loyalty_tier,
                product=order.product,
                size=order.size,
                price=order.price,
                discount_pct=order.discount_pct,
                delivery_date=order.delivery_date.isoformat(),
                status=order.status,
                condition=order.condition,
                has_receipt=order.has_receipt,
                is_defective=order.is_defective,
                refund_status=order.refund_status,
            )

    def evaluate_refund(self, *, customer_query: str, order_id: str) -> PolicyDecision:
        with self.session_factory() as session:
            facts = SupportRepository(session).get_policy_facts(order_id=order_id)
            return evaluate_refund(
                facts,
                order_id=order_id,
                customer_query=customer_query,
            )

    def process_refund(self, *, customer_query: str, order_id: str) -> RefundActionResult:
        """Lock, recheck, mutate, and audit a refund in one transaction."""
        with self.session_factory.begin() as session:
            repository = SupportRepository(session)
            facts = repository.get_policy_facts(order_id=order_id, for_update=True)
            decision = evaluate_refund(
                facts,
                order_id=order_id,
                customer_query=customer_query,
            )
            if not decision.eligible:
                return RefundActionResult(
                    status=RefundActionStatus.BLOCKED,
                    decision=decision,
                    message="Refund blocked by the current policy decision.",
                )

            order = repository.get_order_for_update(decision.order_id)
            if order is None or order.refund_status != "none":
                latest = repository.get_policy_facts(order_id=order_id, for_update=True)
                return RefundActionResult(
                    status=RefundActionStatus.BLOCKED,
                    decision=evaluate_refund(
                        latest,
                        order_id=order_id,
                        customer_query=customer_query,
                    ),
                    message="The order changed while the refund was being processed.",
                )

            order.refund_status = "approved"
            request_id = str(uuid4())
            session.add(
                RefundRequest(
                    id=request_id,
                    order_id=order.order_id,
                    status="approved",
                    amount=decision.refund_amount,
                    reason_code=decision.reason_code.value,
                    idempotency_key=f"refund:{order.order_id}",
                )
            )
            session.flush()
            session.add(
                RefundEvent(
                    refund_request_id=request_id,
                    event_type="approved",
                    detail=decision.explanation,
                )
            )

        return RefundActionResult(
            status=RefundActionStatus.APPROVED,
            decision=decision,
            message="The simulated refund was approved.",
        )

    def deny_refund(self, *, customer_query: str, order_id: str) -> RefundActionResult:
        """Record a deterministic policy denial and its audit event."""
        with self.session_factory.begin() as session:
            repository = SupportRepository(session)
            facts = repository.get_policy_facts(order_id=order_id, for_update=True)
            decision = evaluate_refund(
                facts,
                order_id=order_id,
                customer_query=customer_query,
            )
            non_actionable = {
                RefundReason.ORDER_NOT_FOUND,
                RefundReason.OWNERSHIP_MISMATCH,
                RefundReason.ALREADY_REFUNDED,
            }
            if decision.eligible or decision.requires_review or decision.reason_code in non_actionable:
                return RefundActionResult(
                    status=RefundActionStatus.BLOCKED,
                    decision=decision,
                    message="A denial was not recorded.",
                )
            if decision.reason_code is RefundReason.PREVIOUSLY_DENIED:
                return RefundActionResult(
                    status=RefundActionStatus.DENIED,
                    decision=decision,
                    message="The order was already denied.",
                )

            order = repository.get_order_for_update(decision.order_id)
            if order is None or order.refund_status != "none":
                return RefundActionResult(
                    status=RefundActionStatus.BLOCKED,
                    decision=decision,
                    message="The order changed while the denial was being recorded.",
                )
            order.refund_status = "denied"
            request_id = str(uuid4())
            session.add(
                RefundRequest(
                    id=request_id,
                    order_id=order.order_id,
                    status="denied",
                    amount=None,
                    reason_code=decision.reason_code.value,
                    idempotency_key=f"denial:{order.order_id}",
                )
            )
            session.flush()
            session.add(
                RefundEvent(
                    refund_request_id=request_id,
                    event_type="denied",
                    detail=decision.explanation,
                )
            )

        return RefundActionResult(
            status=RefundActionStatus.DENIED,
            decision=decision,
            message="The policy denial was recorded.",
        )

    def escalate(
        self,
        *,
        customer_query: str,
        order_id: str,
        issue_summary: str,
    ) -> EscalationResult:
        with self.session_factory.begin() as session:
            repository = SupportRepository(session)
            facts = repository.get_policy_facts(order_id=order_id, for_update=True)
            decision = evaluate_refund(
                facts,
                order_id=order_id,
                customer_query=customer_query,
            )
            if decision.reason_code in {
                RefundReason.ORDER_NOT_FOUND,
                RefundReason.OWNERSHIP_MISMATCH,
            }:
                return EscalationResult(created=False, decision=decision, ticket_id=None)

            ticket_id = str(uuid4())
            session.add(
                EscalationTicket(
                    id=ticket_id,
                    order_id=decision.order_id,
                    issue_summary=issue_summary.strip(),
                    status="open",
                )
            )
        return EscalationResult(created=True, decision=decision, ticket_id=ticket_id)
