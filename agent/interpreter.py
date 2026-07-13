"""Narrow language-model boundary for extracting request identifiers and intent."""

import json
import re
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from agent.config import load_model_settings
from agent.prompts import EXTRACTION_PROMPT
from agent.state import WorkflowIntent


class RequestUnderstanding(BaseModel):
    customer_query: str | None = None
    order_id: str | None = None
    intent: WorkflowIntent = "unknown"


class RequestInterpreter(Protocol):
    def interpret(self, message: str) -> RequestUnderstanding: ...


class OpenRouterRequestInterpreter:
    """Use the model only for understanding language, never for authorization."""

    def __init__(self, model: ChatOpenAI | None = None):
        if model is None:
            settings = load_model_settings()
            model = ChatOpenAI(
                model=settings.model,
                openai_api_key=settings.api_key,
                openai_api_base=settings.base_url,
                temperature=0,
            )
        self.model = model

    def interpret(self, message: str) -> RequestUnderstanding:
        fallback = extract_request_fields(message)
        try:
            response = self.model.invoke(
                [SystemMessage(content=EXTRACTION_PROMPT), HumanMessage(content=message)]
            )
            content = response.content
            if not isinstance(content, str):
                return fallback
            raw = content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
            parsed = RequestUnderstanding.model_validate(json.loads(raw))
            return RequestUnderstanding(
                customer_query=parsed.customer_query or fallback.customer_query,
                order_id=_normalize_order_id(parsed.order_id) or fallback.order_id,
                intent=parsed.intent if parsed.intent != "unknown" else fallback.intent,
            )
        except Exception:
            return fallback


def _normalize_order_id(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(
        r"\bORD(?:\s*-\s*|\s+)([A-Z0-9]+)\b",
        value,
        flags=re.IGNORECASE,
    )
    return f"ORD-{match.group(1).upper()}" if match else None


def extract_request_fields(message: str) -> RequestUnderstanding:
    """Conservative fallback when a model cannot return valid structured data."""
    email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", message)
    order_id = _normalize_order_id(message)
    name_match = re.search(
        r"(?:my name is|i am|i'm|customer is)\s+([A-Za-z]+(?:\s+[A-Za-z]+){1,2})",
        message,
        flags=re.IGNORECASE,
    )
    customer_query = email_match.group(0) if email_match else None
    if customer_query is None and name_match:
        customer_query = name_match.group(1).strip()

    normalized = message.casefold()
    if any(word in normalized for word in ("human", "supervisor", "escalat")):
        intent: WorkflowIntent = "escalate"
    elif any(word in normalized for word in ("refund", "return")):
        intent = "refund"
    elif any(word in normalized for word in ("order status", "order detail", "where is")):
        intent = "order_status"
    else:
        intent = "unknown"
    return RequestUnderstanding(
        customer_query=customer_query,
        order_id=order_id,
        intent=intent,
    )
