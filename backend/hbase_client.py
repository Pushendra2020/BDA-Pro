"""FastAPI dependency helpers for one HBase analytics service per process."""

from __future__ import annotations

from fastapi import Request

from customer_analytics import CustomerAnalytics


def get_analytics(request: Request) -> CustomerAnalytics:
    """Return the connection/service created by the FastAPI lifespan."""

    return request.app.state.analytics
