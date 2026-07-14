"""Explicit LangGraph workflow with deterministic safety and confirmation gates."""

import re
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph

from agent.interpreter import OpenRouterRequestInterpreter, RequestInterpreter
from agent.state import AgentState
from application.support_service import SupportService
from domain.refunds import PolicyDecision
from infrastructure.database import get_database_url

load_dotenv()

CONFIRMATION_PHRASES = {
    "confirm",
    "confirm refund",
    "please confirm",
    "proceed",
    "proceed with refund",
    "yes",
    "yes confirm",
    "yes confirm refund",
    "yes please",
}
CANCELLATION_PHRASES = {"cancel", "cancel refund", "do not proceed", "no", "no thanks", "stop"}
WORKFLOW_LABELS = {
    "interpret_request": "Understand request",
    "identify_customer": "Identify customer",
    "verify_order": "Verify order ownership",
    "evaluate_policy": "Evaluate refund policy",
    "request_confirmation": "Wait for confirmation",
    "execute_refund": "Execute confirmed refund",
    "policy_response": "Explain policy decision",
    "escalate": "Escalate to supervisor",
}


def _normalized_phrase(message: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", message.casefold()).split())


def _last_user_message(state: AgentState) -> str:
    for item in reversed(state.get("messages", [])):
        if isinstance(item, HumanMessage):
            return str(item.content)
    return ""


def _append(state: AgentState, node: str, activity: str) -> dict:
    return {
        "turn_trace": [*state.get("turn_trace", []), node],
        "activity_log": [*state.get("activity_log", []), activity],
    }


def _policy_context(decision: PolicyDecision) -> dict:
    return {
        "outcome": decision.outcome.value,
        "reason_code": decision.reason_code.value,
        "explanation": decision.explanation,
        "policy_rule": decision.policy_rule,
        "refund_amount": str(decision.refund_amount) if decision.refund_amount is not None else None,
    }


def create_workflow(
    *,
    service: SupportService,
    interpreter: RequestInterpreter,
    checkpointer=None,
):
    """Compile an injectable workflow for production and deterministic tests."""

    def interpret_request(state: AgentState):
        message = _last_user_message(state)
        phrase = _normalized_phrase(message)
        base = {
            "latest_user_message": message,
            "turn_trace": ["interpret_request"],
            "activity_log": ["Interpreted the request without granting action authority."],
            "response_text": "",
        }

        if state.get("awaiting_confirmation"):
            if phrase in CONFIRMATION_PHRASES:
                return {**base, "requested_action": "execute_refund"}
            if phrase in CANCELLATION_PHRASES:
                return {
                    **base,
                    "requested_action": "respond",
                    "awaiting_confirmation": False,
                    "stage": "resolved",
                    "response_text": "No problem — the refund was cancelled and no changes were made.",
                }
            if any(word in phrase for word in ("human", "supervisor", "escalate")):
                return {**base, "requested_action": "escalate", "intent": "escalate"}
            return {
                **base,
                "requested_action": "respond",
                "stage": "awaiting_confirmation",
                "awaiting_confirmation": True,
                "response_text": (
                    "I have not processed the refund. Reply **confirm refund** to approve it, "
                    "or **cancel** to stop."
                ),
            }

        understanding = interpreter.interpret(message)
        customer_query = understanding.customer_query or state.get("customer_query")
        order_id = understanding.order_id or state.get("order_id")
        context_changed = (
            understanding.customer_query is not None
            and understanding.customer_query.casefold()
            != str(state.get("customer_query") or "").casefold()
        ) or (
            understanding.order_id is not None
            and understanding.order_id.casefold() != str(state.get("order_id") or "").casefold()
        )
        action = "escalate" if understanding.intent == "escalate" else "evaluate"
        updates = {
            **base,
            "customer_query": customer_query,
            "order_id": order_id,
            "intent": understanding.intent,
            "requested_action": action,
            "awaiting_confirmation": False,
            "stage": "new",
        }
        if context_changed:
            updates.update({"customer": None, "order": None, "policy": None})
        if not customer_query or not order_id:
            missing = []
            if not customer_query:
                missing.append("your full name or email address")
            if not order_id:
                missing.append("your Order ID")
            updates["requested_action"] = "respond"
            updates["response_text"] = f"Please provide {' and '.join(missing)} so I can continue."
        return updates

    def route_after_interpret(state: AgentState):
        action = state.get("requested_action")
        if action == "execute_refund":
            return "execute_refund"
        if action == "respond":
            return END
        return "identify_customer"

    def identify_customer(state: AgentState):
        customer = service.lookup_customer(str(state.get("customer_query") or ""))
        update = _append(state, "identify_customer", "Looked up the customer record.")
        update["stage"] = "identifying_customer"
        if customer is None:
            update.update(
                {
                    "customer": None,
                    "requested_action": "respond",
                    "response_text": (
                        "I couldn't find that customer. Check the full name or email address and try again."
                    ),
                }
            )
        else:
            update["customer_query"] = customer.email
            update["customer"] = {
                "id": customer.id,
                "name": customer.name,
                "email": customer.email,
                "loyalty_tier": customer.loyalty_tier,
            }
        return update

    def route_after_customer(state: AgentState):
        return END if state.get("customer") is None else "verify_order"

    def verify_order(state: AgentState):
        order = service.get_order(
            customer_query=str(state.get("customer_query") or ""),
            order_id=str(state.get("order_id") or ""),
        )
        update = _append(state, "verify_order", "Verified that the order belongs to the customer.")
        update["stage"] = "verifying_order"
        if order is None:
            update.update(
                {
                    "order": None,
                    "requested_action": "respond",
                    "response_text": (
                        "I couldn't verify that Order ID for this customer. No refund action was taken."
                    ),
                }
            )
        else:
            update["order_id"] = order.order_id
            update["order"] = {
                "order_id": order.order_id,
                "product": order.product,
                "price": str(order.price),
                "status": order.status,
                "condition": order.condition,
                "refund_status": order.refund_status,
            }
        return update

    def route_after_order(state: AgentState):
        return END if state.get("order") is None else "evaluate_policy"

    def evaluate_policy(state: AgentState):
        decision = service.evaluate_refund(
            customer_query=str(state.get("customer_query") or ""),
            order_id=str(state.get("order_id") or ""),
        )
        return {
            **_append(state, "evaluate_policy", "Evaluated trusted order facts against policy."),
            "stage": "evaluating_policy",
            "policy": _policy_context(decision),
        }

    def route_after_policy(state: AgentState):
        if state.get("requested_action") == "escalate":
            return "escalate"
        policy = state.get("policy") or {}
        return "request_confirmation" if policy.get("outcome") == "eligible" else "policy_response"

    def request_confirmation(state: AgentState):
        order = state.get("order") or {}
        policy = state.get("policy") or {}
        amount = policy.get("refund_amount") or order.get("price") or "the order amount"
        return {
            **_append(state, "request_confirmation", "Paused before mutation for customer confirmation."),
            "stage": "awaiting_confirmation",
            "awaiting_confirmation": True,
            "response_text": (
                f"Order **{order.get('order_id')}** for **{order.get('product')}** is eligible for a "
                f"**${amount}** refund. {policy.get('explanation')}\n\n"
                "No change has been made yet. Reply **confirm refund** to proceed, or **cancel**."
            ),
        }

    def policy_response(state: AgentState):
        policy = state.get("policy") or {}
        review = policy.get("outcome") == "review_required"
        heading = "Human review is required" if review else "This refund is not eligible"
        rule = f" Policy rule: {policy.get('policy_rule')}." if policy.get("policy_rule") else ""
        return {
            **_append(state, "policy_response", "Returned the policy decision without mutating the order."),
            "stage": "resolved",
            "awaiting_confirmation": False,
            "response_text": (
                f"**{heading}.** {policy.get('explanation')}{rule} "
                "No order changes were made. You can ask me to escalate this to a human supervisor."
            ),
        }

    def execute_refund(state: AgentState):
        result = service.process_refund(
            customer_query=str(state.get("customer_query") or ""),
            order_id=str(state.get("order_id") or ""),
        )
        approved = result.status.value == "approved"
        if approved:
            response = (
                f"Refund approved for **{result.decision.order_id}** — "
                f"**${result.decision.refund_amount}**. The transaction and audit event were saved."
            )
        else:
            response = (
                f"The refund was not processed because the latest policy check returned "
                f"**{result.decision.reason_code.value}**. {result.decision.explanation}"
            )
        return {
            **_append(state, "execute_refund", "Rechecked policy and executed the confirmed transaction."),
            "stage": "completed" if approved else "resolved",
            "awaiting_confirmation": False,
            "policy": _policy_context(result.decision),
            "response_text": response,
        }

    def escalate(state: AgentState):
        result = service.escalate(
            customer_query=str(state.get("customer_query") or ""),
            order_id=str(state.get("order_id") or ""),
            issue_summary=state.get("latest_user_message", "Customer requested human review."),
        )
        if result.created:
            response = (
                f"I've opened supervisor ticket **{result.ticket_id}** for order "
                f"**{result.decision.order_id}**."
            )
        else:
            response = "I couldn't create an escalation because the customer and order were not verified."
        return {
            **_append(state, "escalate", "Created a human-review ticket after ownership verification."),
            "stage": "escalated" if result.created else "resolved",
            "awaiting_confirmation": False,
            "policy": _policy_context(result.decision),
            "response_text": response,
        }

    graph = StateGraph(AgentState)
    graph.add_node("interpret_request", interpret_request)
    graph.add_node("identify_customer", identify_customer)
    graph.add_node("verify_order", verify_order)
    graph.add_node("evaluate_policy", evaluate_policy)
    graph.add_node("request_confirmation", request_confirmation)
    graph.add_node("policy_response", policy_response)
    graph.add_node("execute_refund", execute_refund)
    graph.add_node("escalate", escalate)
    graph.set_entry_point("interpret_request")
    graph.add_conditional_edges("interpret_request", route_after_interpret)
    graph.add_conditional_edges("identify_customer", route_after_customer)
    graph.add_conditional_edges("verify_order", route_after_order)
    graph.add_conditional_edges("evaluate_policy", route_after_policy)
    graph.add_edge("request_confirmation", END)
    graph.add_edge("policy_response", END)
    graph.add_edge("execute_refund", END)
    graph.add_edge("escalate", END)
    return graph.compile(checkpointer=checkpointer)


@lru_cache(maxsize=1)
def build_graph():
    """Build the production workflow once with session-level checkpoint persistence."""
    return create_workflow(
        service=SupportService(get_database_url()),
        interpreter=OpenRouterRequestInterpreter(),
        checkpointer=InMemorySaver(),
    )
