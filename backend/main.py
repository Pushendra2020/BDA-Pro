"""FastAPI application exposing the HBase customer database."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from threading import Lock
from typing import Any, Callable, TypeVar

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from customer_analytics import AnalyticsError, CustomerAnalytics, CustomerNotFoundError
from backend.hbase_client import get_analytics
from backend.models import (
    Customer360Response,
    CustomerActivityResponse,
    CustomerDirectoryResponse,
    CustomerOrdersResponse,
    CustomerProfileResponse,
)
from backend.services import activity_service, analytics_service, customer_service, order_service


T = TypeVar("T")
HBASE_REQUEST_LOCK = Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.analytics = CustomerAnalytics()
    try:
        yield
    finally:
        app.state.analytics.close()


app = FastAPI(
    title="HBase Customer Analytics API",
    version="1.0.0",
    description="Customer profile, order, activity, and analytics endpoints backed by Apache HBase.",
    lifespan=lifespan,
)

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _call(operation: Callable[[], T]) -> T:
    # HappyBase's Thrift connection is reused by the process, but it is not
    # safe for concurrent requests. The lock keeps the connection reusable
    # while preventing dashboard Promise.all calls from interleaving frames.
    with HBASE_REQUEST_LOCK:
        try:
            return operation()
        except CustomerNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            # Invalid customer IDs are presented as a not-found resource to
            # keep the public customer API simple and avoid exposing key
            # validation.
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except AnalyticsError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/health")
def health(analytics: CustomerAnalytics = Depends(get_analytics)) -> dict[str, str]:
    return {"status": "ok", "database": "hbase"}


@app.get("/api/customers", response_model=CustomerDirectoryResponse)
def customer_directory(
    search: str = Query(default="", max_length=100),
    city: str = Query(default="", max_length=100),
    category: str = Query(default="", max_length=100),
    min_orders: int = Query(default=0, ge=0, le=1000),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    analytics: CustomerAnalytics = Depends(get_analytics),
):
    return _call(
        lambda: analytics.get_customer_directory(
            search=search,
            city=city,
            category=category,
            min_orders=min_orders,
            limit=limit,
            offset=offset,
        )
    )


@app.get("/api/customers/{customer_id}", response_model=CustomerProfileResponse)
def customer_profile(
    customer_id: str,
    analytics: CustomerAnalytics = Depends(get_analytics),
):
    return _call(lambda: customer_service.get_profile(analytics, customer_id))


@app.get("/api/customers/{customer_id}/orders", response_model=CustomerOrdersResponse)
def customer_orders(
    customer_id: str,
    analytics: CustomerAnalytics = Depends(get_analytics),
):
    return _call(lambda: order_service.get_customer_orders(analytics, customer_id))


@app.get("/api/customers/{customer_id}/activity", response_model=CustomerActivityResponse)
def customer_activity(
    customer_id: str,
    analytics: CustomerAnalytics = Depends(get_analytics),
):
    return _call(lambda: activity_service.get_customer_activity(analytics, customer_id))


@app.get("/api/customers/{customer_id}/360", response_model=Customer360Response)
def customer_360(
    customer_id: str,
    analytics: CustomerAnalytics = Depends(get_analytics),
):
    return _call(lambda: customer_service.get_customer_360(analytics, customer_id))


@app.get("/api/analytics/overview")
def analytics_overview(
    analytics: CustomerAnalytics = Depends(get_analytics),
) -> dict[str, Any]:
    return _call(lambda: analytics_service.get_overview(analytics))


@app.get("/api/analytics/categories")
def analytics_categories(
    analytics: CustomerAnalytics = Depends(get_analytics),
) -> dict[str, Any]:
    return _call(lambda: analytics_service.get_categories(analytics))


@app.get("/api/analytics/top-customers")
def analytics_top_customers(
    analytics: CustomerAnalytics = Depends(get_analytics),
) -> dict[str, Any]:
    return _call(lambda: analytics_service.get_top_customers(analytics))


@app.get("/api/analytics/activity")
def analytics_activity(
    analytics: CustomerAnalytics = Depends(get_analytics),
) -> dict[str, Any]:
    return _call(lambda: analytics_service.get_activity(analytics))
