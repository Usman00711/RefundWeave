"""Version 1 support API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from api.dependencies import get_support_service
from api.errors import ApiError
from api.schemas import (
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
from application.support_service import SupportService

router = APIRouter(prefix="/api/v1")
Service = Annotated[SupportService, Depends(get_support_service)]
NOT_FOUND_RESPONSE = {404: {"model": ErrorResponse, "description": "Record not found"}}


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
