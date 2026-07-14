"""Versioned HTTP request and response contracts."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from application.support_service import RefundActionStatus
from domain.refunds import DecisionOutcome, RefundReason

CustomerQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]
OrderId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=5,
        max_length=40,
        pattern=r"^[Oo][Rr][Dd]-[A-Za-z0-9-]+$",
    ),
]
ChatMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]


class CustomerLookupRequest(BaseModel):
    query: CustomerQuery


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    loyalty_tier: str
    annual_spend: Decimal


class OwnedOrderRequest(BaseModel):
    customer_query: CustomerQuery
    order_id: OrderId


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: str
    customer_name: str
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


class PolicyDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    outcome: DecisionOutcome
    reason_code: RefundReason
    explanation: str
    order_id: str
    policy_rule: str | None
    product: str | None
    refund_amount: Decimal | None
    days_since_delivery: int | None
    return_window_days: int | None


class RefundConfirmationRequest(BaseModel):
    customer_query: CustomerQuery
    confirmed: Literal[True] = Field(description="Must be true before a refund can be attempted")


class RefundConfirmationResponse(BaseModel):
    status: RefundActionStatus
    message: str
    decision: PolicyDecisionResponse


class ChatStreamRequest(BaseModel):
    message: ChatMessage
    thread_id: UUID | None = Field(
        default=None,
        description="Reuse the thread ID returned by the first event for follow-up messages.",
    )


class HealthResponse(BaseModel):
    status: Literal["ok", "unhealthy"]
    database: Literal["ready", "unavailable"]
    version: str


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
