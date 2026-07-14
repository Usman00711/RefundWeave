"""Server-Sent Event transport for the conversational LangGraph workflow."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage

from agent.graph import WORKFLOW_LABELS

logger = logging.getLogger(__name__)


def encode_sse(event: str, data: dict[str, Any], *, sequence: int) -> str:
    """Encode one JSON payload as a standards-compliant SSE frame."""
    payload = {"sequence": sequence, **data}
    serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return f"id: {sequence}\nevent: {event}\ndata: {serialized}\n\n"


async def stream_workflow(
    *,
    graph,
    message: str,
    thread_id: str,
) -> AsyncIterator[str]:
    """Stream public workflow progress without exposing internal graph state."""
    sequence = 1
    yield encode_sse("session", {"thread_id": thread_id}, sequence=sequence)
    config = {"configurable": {"thread_id": thread_id}}
    response_text = ""
    stage = "new"
    awaiting_confirmation = False

    try:
        async for update in graph.astream(
            {"messages": [HumanMessage(content=message)]},
            config=config,
            stream_mode="updates",
        ):
            if not isinstance(update, dict):
                continue
            for node, values in update.items():
                if not isinstance(values, dict):
                    continue
                stage = values.get("stage", stage)
                awaiting_confirmation = values.get(
                    "awaiting_confirmation",
                    awaiting_confirmation,
                )
                if values.get("response_text"):
                    response_text = values["response_text"]

                sequence += 1
                activities = values.get("activity_log") or []
                yield encode_sse(
                    "workflow_step",
                    {
                        "thread_id": thread_id,
                        "node": node,
                        "label": WORKFLOW_LABELS.get(node, "Process request"),
                        "stage": stage,
                        "detail": activities[-1] if activities else "Workflow step completed.",
                    },
                    sequence=sequence,
                )

        if not response_text:
            raise RuntimeError("Workflow completed without a customer response.")

        sequence += 1
        yield encode_sse(
            "message",
            {
                "thread_id": thread_id,
                "message": response_text,
                "stage": stage,
                "awaiting_confirmation": awaiting_confirmation,
            },
            sequence=sequence,
        )
        sequence += 1
        yield encode_sse(
            "done",
            {"thread_id": thread_id},
            sequence=sequence,
        )
    except Exception as exc:
        logger.exception("Streaming workflow failed", exc_info=exc)
        sequence += 1
        yield encode_sse(
            "error",
            {
                "thread_id": thread_id,
                "code": "workflow_failed",
                "message": "The chat request could not be completed.",
            },
            sequence=sequence,
        )
