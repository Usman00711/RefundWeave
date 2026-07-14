from uuid import uuid4

import chainlit as cl
from langchain_core.messages import HumanMessage

from agent import tracer
from agent.graph import WORKFLOW_LABELS, build_graph

CUSTOMER_ERROR_MESSAGE = (
    "⚠️ I couldn't complete that request right now. Please try again in a moment."
)

@cl.on_chat_start
async def on_chat_start():
    cl.user_session.set("thread_id", str(uuid4()))
    await cl.Message(
        content=(
            "👟 **Welcome to Sole Syntax Customer Support!**\n\n"
            "I'm **Sole**, your AI support agent. I can help you with refund and return requests.\n\n"
            "To get started, please share:\n"
            "- Your **email address** or **full name**\n"
            "- Your **Order ID** (e.g. `ORD-001`)\n"
            "- A brief description of your issue\n\n"
            "*Refunds are never executed until you explicitly confirm them.*"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    thread_id = cl.user_session.get("thread_id") or str(uuid4())
    cl.user_session.set("thread_id", thread_id)
    config = {"configurable": {"thread_id": thread_id}}
    tracer.log_session_start(message.content)

    try:
        result = await build_graph().ainvoke(
            {"messages": [HumanMessage(content=message.content)]},
            config=config,
        )
        activities = result.get("activity_log", [])
        for index, node in enumerate(result.get("turn_trace", [])):
            if node not in WORKFLOW_LABELS:
                continue
            step = cl.Step(name=f"✓ {WORKFLOW_LABELS[node]}", type="tool")
            step.output = activities[index] if index < len(activities) else "Completed safely."
            await step.send()

        final_text = result.get("response_text", "")
        if not final_text:
            raise RuntimeError("Workflow completed without a customer response.")
        tracer.log_agent_response(final_text)
        await cl.Message(content=final_text).send()
    except Exception as exc:
        tracer.log_error(f"{type(exc).__name__}: {exc}")
        await cl.Message(content=CUSTOMER_ERROR_MESSAGE).send()
        return

    tracer.log_session_end()
