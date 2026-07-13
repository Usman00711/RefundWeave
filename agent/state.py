"""Typed state shared by the deterministic customer-support workflow."""

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

WorkflowIntent = Literal["refund", "escalate", "order_status", "unknown"]
WorkflowStage = Literal[
    "new",
    "identifying_customer",
    "verifying_order",
    "evaluating_policy",
    "awaiting_confirmation",
    "completed",
    "resolved",
    "escalated",
]


class CustomerContext(TypedDict):
    id: int
    name: str
    email: str
    loyalty_tier: str


class OrderContext(TypedDict):
    order_id: str
    product: str
    price: str
    status: str
    condition: str
    refund_status: str


class PolicyContext(TypedDict):
    outcome: str
    reason_code: str
    explanation: str
    policy_rule: str | None
    refund_amount: str | None


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    latest_user_message: NotRequired[str]
    customer_query: NotRequired[str | None]
    order_id: NotRequired[str | None]
    intent: NotRequired[WorkflowIntent]
    requested_action: NotRequired[str]
    stage: NotRequired[WorkflowStage]
    customer: NotRequired[CustomerContext | None]
    order: NotRequired[OrderContext | None]
    policy: NotRequired[PolicyContext | None]
    awaiting_confirmation: NotRequired[bool]
    response_text: NotRequired[str]
    turn_trace: NotRequired[list[str]]
    activity_log: NotRequired[list[str]]
