"""Small response models for the public API surface."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel


class CustomerProfileResponse(BaseModel):
    customer_id: str
    profile: Dict[str, str]
    preferences: Dict[str, str]


class CustomerOrdersResponse(BaseModel):
    customer_id: str
    order_summary: Dict[str, Any]
    orders: List[Dict[str, Any]]


class CustomerActivityResponse(BaseModel):
    customer_id: str
    activity_summary: Dict[str, Any]
    activities: List[Dict[str, Any]]


class Customer360Response(BaseModel):
    customer_id: str
    profile: Dict[str, str]
    preferences: Dict[str, str]
    order_summary: Dict[str, Any]
    order_history: List[Dict[str, Any]]
    activity_summary: Dict[str, Any]
    activity_history: List[Dict[str, Any]]


class CustomerDirectoryItem(BaseModel):
    customer_id: str
    name: str
    city: str
    category: str
    order_count: int
    total_spending: Any
    activity_count: int


class CustomerDirectoryResponse(BaseModel):
    items: List[CustomerDirectoryItem]
    total: int
    limit: int
    offset: int
    available_cities: List[str]
    available_categories: List[str]
