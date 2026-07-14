"""Version 1 support API routes."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import StreamingResponse

from api.chat import stream_workflow
from api.dependencies import get_chat_graph, get_support_service
from api.errors import ApiError
from api.schemas import (
    ChatStreamRequest,
    CustomerLookupRequest,
    CustomerResponse,
    ErrorResponse,
    HealthResponse,
    OrderId,
    OrderResponse,
    OwnedOrderRequest,
    PolicyDecisionResponse,
    RefundConfirmationRequest,
    RefundConfirmationResponse,
)
from api.security import enforce_chat_rate_limit
from application.support_service import SupportService

router = APIRouter(prefix="/api/v1")
Service = Annotated[SupportService, Depends(get_support_service)]
ChatGraph = Annotated[object, Depends(get_chat_graph)]
NOT_FOUND_RESPONSE = {404: {"model": ErrorResponse, "description": "Record not found"}}


@router.post(
    "/chat/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-Sent Events containing workflow progress and the final message.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
    tags=["chat"],
)
async def chat_stream(
    request: ChatStreamRequest,
    _rate_limit: Annotated[None, Depends(enforce_chat_rate_limit)],
    graph: ChatGraph,
) -> StreamingResponse:
    thread_id = str(request.thread_id or uuid4())
    return StreamingResponse(
        stream_workflow(
            graph=graph,
            message=request.message,
            thread_id=thread_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health", response_model=HealthResponse, tags=["operations"])
def health(response: Response, service: Service) -> HealthResponse:
    ready = service.is_ready()
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if ready else "unhealthy",
        database="ready" if ready else "unavailable",
        version="v1",
    )


@router.post(
    "/customers/lookup",
    response_model=CustomerResponse,
    responses=NOT_FOUND_RESPONSE,
    tags=["customers"],
)
def lookup_customer(request: CustomerLookupRequest, service: Service) -> CustomerResponse:
    customer = service.lookup_customer(request.query)
    if customer is None:
        raise ApiError(404, "customer_not_found", "No matching customer was found.")
    return CustomerResponse.model_validate(customer)


@router.post(
    "/orders/lookup",
    response_model=OrderResponse,
    responses=NOT_FOUND_RESPONSE,
    tags=["orders"],
)
def lookup_order(request: OwnedOrderRequest, service: Service) -> OrderResponse:
    order = service.get_order(
        customer_query=request.customer_query,
        order_id=request.order_id,
    )
    if order is None:
        raise ApiError(
            404,
            "order_not_found",
            "No matching customer and order record was found.",
        )
    return OrderResponse.model_validate(order)


@router.post(
    "/refunds/eligibility",
    response_model=PolicyDecisionResponse,
    responses=NOT_FOUND_RESPONSE,
    tags=["refunds"],
)
def check_eligibility(
    request: OwnedOrderRequest,
    service: Service,
) -> PolicyDecisionResponse:
    order = service.get_order(
        customer_query=request.customer_query,
        order_id=request.order_id,
    )
    if order is None:
        raise ApiError(
            404,
            "order_not_found",
            "No matching customer and order record was found.",
        )
    decision = service.evaluate_refund(
        customer_query=request.customer_query,
        order_id=request.order_id,
    )
    return PolicyDecisionResponse.model_validate(decision)


@router.post(
    "/refunds/{order_id}/confirm",
    response_model=RefundConfirmationResponse,
    responses=NOT_FOUND_RESPONSE,
    tags=["refunds"],
)
def confirm_refund(
    order_id: OrderId,
    request: RefundConfirmationRequest,
    service: Service,
) -> RefundConfirmationResponse:
    order = service.get_order(
        customer_query=request.customer_query,
        order_id=order_id,
    )
    if order is None:
        raise ApiError(
            404,
            "order_not_found",
            "No matching customer and order record was found.",
        )
    result = service.process_refund(
        customer_query=request.customer_query,
        order_id=order_id,
    )
    return RefundConfirmationResponse(
        status=result.status,
        message=result.message,
        decision=PolicyDecisionResponse.model_validate(result.decision),
    )
