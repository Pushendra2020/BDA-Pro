"""Live integration tests for the FastAPI/HBase API.

These tests intentionally use the running local HBase service. They are not a
replacement for unit tests, and they must be run with the hbase conda env.
"""

from fastapi.testclient import TestClient

from backend.main import app


def test_customer_profile() -> None:
    with TestClient(app) as client:
        response = client.get("/api/customers/CUST000001")
    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == "CUST000001"
    assert "profile" in body and "preferences" in body


def test_customer_directory_and_filters() -> None:
    with TestClient(app) as client:
        response = client.get("/api/customers?city=Ahmedabad&min_orders=5&limit=5")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= len(body["items"])
    assert len(body["items"]) <= 5
    assert all(item["city"] == "Ahmedabad" for item in body["items"])
    assert all(item["order_count"] >= 5 for item in body["items"])
    assert "available_categories" in body


def test_customer_orders() -> None:
    with TestClient(app) as client:
        response = client.get("/api/customers/CUST000001/orders")
    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == "CUST000001"
    assert body["order_summary"]["order_count"] == len(body["orders"])


def test_customer_activity() -> None:
    with TestClient(app) as client:
        response = client.get("/api/customers/CUST000001/activity")
    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == "CUST000001"
    assert body["activity_summary"]["total_activities"] == len(body["activities"])


def test_customer_360() -> None:
    with TestClient(app) as client:
        response = client.get("/api/customers/CUST000001/360")
    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == "CUST000001"
    assert "order_history" in body and "activity_history" in body


def test_analytics_endpoints() -> None:
    paths = [
        "/api/analytics/overview",
        "/api/analytics/categories",
        "/api/analytics/top-customers",
        "/api/analytics/activity",
    ]
    with TestClient(app) as client:
        responses = [client.get(path) for path in paths]
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["total_customers"] > 0
    assert responses[1].json()["categories"]
    assert responses[2].json()["customers"]
    assert responses[3].json()["by_type"]


def test_invalid_customer_returns_not_found() -> None:
    with TestClient(app) as client:
        response = client.get("/api/customers/INVALID_ID")
    assert response.status_code == 404
