import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from api.dependencies import get_support_service
from api.main import create_app
from application.support_service import SupportService
from infrastructure.models import Order
from tests.db_helpers import add_customer, add_order, create_test_database, get_order_status


@pytest.fixture
def api_context(tmp_path):
    db_path = tmp_path / "api.db"
    database_url = create_test_database(db_path)
    add_customer(database_url, tier="Gold")
    add_order(database_url, days_ago=20)

    app = create_app()
    app.dependency_overrides[get_support_service] = lambda: SupportService(database_url)
    with TestClient(app) as client:
        yield client, database_url


def test_health_reports_database_readiness(api_context):
    client, _db_path = api_context

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ready", "version": "v1"}
    assert response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "camera=()" in response.headers["permissions-policy"]


def test_request_id_is_preserved_when_valid(api_context):
    client, _db_path = api_context

    response = client.get("/api/v1/health", headers={"X-Request-ID": "portfolio-demo-123"})

    assert response.headers["x-request-id"] == "portfolio-demo-123"


def test_invalid_request_id_is_replaced(api_context):
    client, _db_path = api_context

    response = client.get("/api/v1/health", headers={"X-Request-ID": "unsafe value"})

    assert response.headers["x-request-id"] != "unsafe value"
    assert len(response.headers["x-request-id"]) == 36


def test_internal_metrics_report_route_and_status(api_context):
    client, _db_path = api_context
    client.get("/api/v1/health")

    response = client.get("/internal/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "refundweave_http_requests_total" in response.text
    assert 'route="/api/v1/health"' in response.text
    assert 'status="200"' in response.text


def test_customer_lookup_returns_typed_public_fields(api_context):
    client, _db_path = api_context

    response = client.post("/api/v1/customers/lookup", json={"query": "alice@example.com"})

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "name": "Alice Johnson",
        "email": "alice@example.com",
        "loyalty_tier": "Gold",
        "annual_spend": "100.00",
    }


def test_missing_customer_uses_safe_error_contract(api_context):
    client, _db_path = api_context

    response = client.post("/api/v1/customers/lookup", json={"query": "missing@example.com"})

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "customer_not_found",
            "message": "No matching customer was found.",
        }
    }


def test_order_lookup_requires_matching_customer(api_context):
    client, _db_path = api_context
    payload = {"customer_query": "Mallory", "order_id": "ORD-TEST"}

    response = client.post("/api/v1/orders/lookup", json=payload)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "order_not_found"
    assert "Alice" not in response.text


def test_policy_endpoint_returns_structured_decision(api_context):
    client, _db_path = api_context

    response = client.post(
        "/api/v1/refunds/eligibility",
        json={"customer_query": "Alice Johnson", "order_id": "ord-test"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "eligible"
    assert body["reason_code"] == "eligible_standard"
    assert body["refund_amount"] == "99.99"
    assert body["return_window_days"] == 45


def test_refund_requires_explicit_confirmation(api_context):
    client, db_path = api_context

    response = client.post(
        "/api/v1/refunds/ORD-TEST/confirm",
        json={"customer_query": "Alice Johnson", "confirmed": False},
    )

    assert response.status_code == 422
    assert get_order_status(db_path) == "none"


def test_refund_confirmation_is_typed_and_idempotent(api_context):
    client, db_path = api_context
    payload = {"customer_query": "Alice Johnson", "confirmed": True}

    first = client.post("/api/v1/refunds/ORD-TEST/confirm", json=payload)
    second = client.post("/api/v1/refunds/ORD-TEST/confirm", json=payload)

    assert first.status_code == 200
    assert first.json()["status"] == "approved"
    assert first.json()["decision"]["refund_amount"] == "99.99"
    assert second.status_code == 200
    assert second.json()["status"] == "blocked"
    assert second.json()["decision"]["reason_code"] == "already_refunded"
    assert get_order_status(db_path) == "approved"


def test_ineligible_refund_confirmation_is_blocked(api_context):
    client, db_path = api_context
    with Session(create_engine(db_path)) as session, session.begin():
        session.execute(update(Order).where(Order.order_id == "ORD-TEST").values(condition="worn"))

    response = client.post(
        "/api/v1/refunds/ORD-TEST/confirm",
        json={"customer_query": "Alice Johnson", "confirmed": True},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
    assert response.json()["decision"]["reason_code"] == "item_not_unworn"
    assert get_order_status(db_path) == "none"


def test_invalid_order_id_is_rejected_before_database_access(api_context):
    client, _db_path = api_context

    response = client.post(
        "/api/v1/orders/lookup",
        json={"customer_query": "Alice Johnson", "order_id": "unsafe"},
    )

    assert response.status_code == 422


def test_openapi_contains_versioned_contracts(api_context):
    client, _db_path = api_context

    document = client.get("/api/openapi.json").json()

    assert document["info"]["version"] == "0.1.0"
    assert "/api/v1/refunds/{order_id}/confirm" in document["paths"]
    assert "PolicyDecisionResponse" in document["components"]["schemas"]
    assert "ErrorResponse" in document["components"]["schemas"]


def test_cors_allows_angular_development_origin(api_context):
    client, _db_path = api_context

    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:4200",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:4200"


def test_database_errors_do_not_expose_internal_details(tmp_path):
    class BrokenService(SupportService):
        def is_ready(self):
            raise OperationalError("SELECT secret", {}, RuntimeError("secret database details"))

    app = create_app()
    database_url = f"sqlite+pysqlite:///{tmp_path / 'db'}"
    app.dependency_overrides[get_support_service] = lambda: BrokenService(database_url)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert "secret" not in response.text


def test_health_is_unhealthy_when_schema_is_missing(tmp_path):
    db_path = tmp_path / "empty.db"
    database_url = f"sqlite+pysqlite:///{db_path}"
    app = create_app()
    app.dependency_overrides[get_support_service] = lambda: SupportService(database_url)

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
