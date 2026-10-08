"""Analytics for the HBase customer database.

The module deliberately keeps HBase as the source of truth.  Aggregations are
performed while scanning HBase rows; no secondary database or pandas data
frame is used.

Revenue convention
-------------------
``gross_order_value`` includes every order with a valid amount.  ``revenue``
and customer ``total_spending`` count only orders whose status is
``Delivered`` because those orders represent realized revenue.  The CLI shows
both values where that distinction is useful.

Run with the project's conda environment, for example::

    conda run -n hbase python customer_analytics.py
    conda run -n hbase python customer_analytics.py --customer CUST000001
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from contextlib import AbstractContextManager
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional


HBASE_HOST = "localhost"
HBASE_PORT = 9090
HBASE_TIMEOUT_MS = 10_000

CUSTOMERS_TABLE = "customers"
ORDERS_TABLE = "customer_orders"
ACTIVITY_TABLE = "customer_activity"

DELIVERED = "Delivered"
CANCELLED = "Cancelled"
CUSTOMER_ID_PATTERN = re.compile(r"^CUST\d{6}$")

CUSTOMER_PROFILE_COLUMNS = [
    b"profile:name",
    b"profile:email",
    b"profile:phone",
    b"profile:age",
    b"profile:city",
    b"profile:registration_date",
]
CUSTOMER_PREFERENCE_COLUMNS = [b"preferences:category", b"preferences:payment"]
CUSTOMER_SUMMARY_COLUMNS = [b"profile:name", b"profile:city"]
ORDER_COLUMNS = [
    b"order:product",
    b"order:category",
    b"order:amount",
    b"order:date",
    b"order:status",
]
ORDER_AGGREGATION_COLUMNS = [
    b"order:product",
    b"order:category",
    b"order:amount",
    b"order:status",
]
ACTIVITY_COLUMNS = [
    b"activity:type",
    b"activity:device",
    b"activity:product",
]
ACTIVITY_AGGREGATION_COLUMNS = ACTIVITY_COLUMNS


class AnalyticsError(RuntimeError):
    """Base exception for expected analytics failures."""


class HBaseConnectionError(AnalyticsError):
    """Raised when the Thrift connection cannot be opened."""


class HBaseTableError(AnalyticsError):
    """Raised when a required HBase table is unavailable."""


class CustomerNotFoundError(AnalyticsError):
    """Raised when a valid customer ID does not exist in HBase."""


def connect_hbase(
    host: str = HBASE_HOST,
    port: int = HBASE_PORT,
    timeout: int = HBASE_TIMEOUT_MS,
):
    """Open and return one HappyBase connection.

    Importing HappyBase inside this function keeps module import useful for
    tests and gives a clear environment hint when the wrong Python interpreter
    is used.
    """

    try:
        import happybase
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise HBaseConnectionError(
            "happybase is not installed. Run this script with the project's "
            "conda environment, for example: conda run -n hbase python "
            "customer_analytics.py"
        ) from exc

    connection = happybase.Connection(host=host, port=port, timeout=timeout)
    try:
        connection.open()
    except Exception as exc:
        try:
            connection.close()
        except Exception:
            pass
        raise HBaseConnectionError(
            f"Could not connect to HBase Thrift at {host}:{port}: {exc}"
        ) from exc
    return connection


def _as_text(value: Any) -> str:
    """Decode a HappyBase byte value without failing on malformed text."""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _decimal_amount(value: Any) -> Optional[Decimal]:
    """Parse a money value, returning ``None`` for a malformed or missing value."""

    if value is None:
        return None
    try:
        amount = Decimal(_as_text(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    return amount


def _money(value: Decimal) -> str:
    return f"₹{value:,.2f}"


def _plain_decimal(value: Decimal) -> Any:
    """Return an int for whole amounts and a Decimal otherwise."""

    return int(value) if value == value.to_integral_value() else value


def _validate_customer_id(customer_id: str) -> str:
    customer_id = (customer_id or "").strip()
    if not CUSTOMER_ID_PATTERN.fullmatch(customer_id):
        raise ValueError(
            "Invalid customer ID. Expected the format CUST000001 "
            "(CUST followed by six digits)."
        )
    return customer_id


class CustomerAnalytics(AbstractContextManager):
    """Reusable analytics service backed by a single HBase connection."""

    def __init__(
        self,
        connection: Any = None,
        host: str = HBASE_HOST,
        port: int = HBASE_PORT,
        timeout: int = HBASE_TIMEOUT_MS,
    ) -> None:
        self.connection = connection or connect_hbase(host, port, timeout)
        self._owns_connection = connection is None
        self._available_tables = self._load_table_names()
        self._order_cache: Optional[Dict[str, Any]] = None
        self._activity_cache: Optional[Dict[str, Any]] = None
        self._customer_profiles_cache: Optional[Dict[str, Dict[str, str]]] = None

    def __enter__(self) -> "CustomerAnalytics":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        """Close the connection owned by this service."""

        if self._owns_connection and self.connection is not None:
            try:
                self.connection.close()
            finally:
                self.connection = None

    def _load_table_names(self) -> set[str]:
        try:
            table_names = self.connection.tables()
        except Exception as exc:
            self.close()
            raise HBaseConnectionError(f"Could not list HBase tables: {exc}") from exc
        return {_as_text(name) for name in table_names}

    def _table(self, table_name: str):
        if table_name not in self._available_tables:
            raise HBaseTableError(
                f"Required HBase table '{table_name}' was not found. "
                "The analytics script does not create or modify tables."
            )
        return self.connection.table(table_name)

    def _scan(
        self,
        table_name: str,
        columns: Optional[Iterable[bytes]] = None,
        row_prefix: Optional[str] = None,
    ) -> Iterator[tuple[bytes, Mapping[bytes, bytes]]]:
        """Yield selected HBase rows, optionally restricted by row prefix."""

        table = self._table(table_name)
        scan_kwargs: Dict[str, Any] = {}
        if columns:
            scan_kwargs["columns"] = list(columns)
        if row_prefix is not None:
            scan_kwargs["row_prefix"] = row_prefix.encode("utf-8")
        try:
            yield from table.scan(**scan_kwargs)
        except Exception as exc:
            raise AnalyticsError(f"HBase scan failed for '{table_name}': {exc}") from exc

    @staticmethod
    def _customer_id_from_order_key(row_key: bytes) -> str:
        return _as_text(row_key).split("#", 1)[0]

    def _build_order_cache(self) -> Dict[str, Any]:
        """Scan orders once and build all order-related aggregates."""

        if self._order_cache is not None:
            return self._order_cache

        status_counts: Counter[str] = Counter()
        category_counts: Counter[str] = Counter()
        category_gross: defaultdict[str, Decimal] = defaultdict(Decimal)
        category_realized: defaultdict[str, Decimal] = defaultdict(Decimal)
        product_order_counts: Counter[str] = Counter()
        product_gross: defaultdict[str, Decimal] = defaultdict(Decimal)
        product_realized: defaultdict[str, Decimal] = defaultdict(Decimal)
        customer_order_counts: Counter[str] = Counter()
        customer_gross: defaultdict[str, Decimal] = defaultdict(Decimal)
        customer_realized: defaultdict[str, Decimal] = defaultdict(Decimal)

        total_orders = 0
        valid_amount_orders = 0
        gross_order_value = Decimal("0")
        realized_revenue = Decimal("0")
        delivered_order_count = 0
        cancelled_order_count = 0
        malformed_amount_count = 0

        for row_key, data in self._scan(ORDERS_TABLE, ORDER_AGGREGATION_COLUMNS):
            total_orders += 1
            customer_id = self._customer_id_from_order_key(row_key)
            status = _as_text(data.get(b"order:status", "")).strip() or "Unknown"
            category = _as_text(data.get(b"order:category", "")).strip() or "Unknown"
            product = _as_text(data.get(b"order:product", "")).strip() or "Unknown"
            amount = _decimal_amount(data.get(b"order:amount"))

            status_counts[status] += 1
            category_counts[category] += 1
            product_order_counts[product] += 1
            customer_order_counts[customer_id] += 1

            if status == DELIVERED:
                delivered_order_count += 1
            if status == CANCELLED:
                cancelled_order_count += 1

            if amount is None:
                malformed_amount_count += 1
                continue

            valid_amount_orders += 1
            gross_order_value += amount
            category_gross[category] += amount
            product_gross[product] += amount
            customer_gross[customer_id] += amount

            if status == DELIVERED:
                realized_revenue += amount
                category_realized[category] += amount
                product_realized[product] += amount
                customer_realized[customer_id] += amount

        self._order_cache = {
            "total_orders": total_orders,
            "valid_amount_orders": valid_amount_orders,
            "gross_order_value": gross_order_value,
            "realized_revenue": realized_revenue,
            "status_counts": status_counts,
            "category_counts": category_counts,
            "category_gross": category_gross,
            "category_realized": category_realized,
            "product_order_counts": product_order_counts,
            "product_gross": product_gross,
            "product_realized": product_realized,
            "customer_order_counts": customer_order_counts,
            "customer_gross": customer_gross,
            "customer_realized": customer_realized,
            "delivered_order_count": delivered_order_count,
            "cancelled_order_count": cancelled_order_count,
            "malformed_amount_count": malformed_amount_count,
        }
        return self._order_cache

    def _build_activity_cache(self) -> Dict[str, Any]:
        """Scan activities once and build all activity-related aggregates."""

        if self._activity_cache is not None:
            return self._activity_cache

        type_counts: Counter[str] = Counter()
        device_counts: Counter[str] = Counter()
        product_activity_counts: Counter[str] = Counter()
        customer_activity_counts: Counter[str] = Counter()
        total_activities = 0

        for row_key, data in self._scan(ACTIVITY_TABLE, ACTIVITY_AGGREGATION_COLUMNS):
            total_activities += 1
            activity_type = _as_text(data.get(b"activity:type", "")).strip() or "Unknown"
            device = _as_text(data.get(b"activity:device", "")).strip() or "Unknown"
            product = _as_text(data.get(b"activity:product", "")).strip()
            customer_id = _as_text(row_key).split("#", 1)[0]

            type_counts[activity_type] += 1
            device_counts[device] += 1
            customer_activity_counts[customer_id] += 1
            if product:
                product_activity_counts[product] += 1

        self._activity_cache = {
            "total_activities": total_activities,
            "type_counts": type_counts,
            "device_counts": device_counts,
            "product_activity_counts": product_activity_counts,
            "customer_activity_counts": customer_activity_counts,
        }
        return self._activity_cache

    def _customer_profiles(self) -> Dict[str, Dict[str, str]]:
        if self._customer_profiles_cache is None:
            profiles: Dict[str, Dict[str, str]] = {}
            for row_key, data in self._scan(CUSTOMERS_TABLE, CUSTOMER_SUMMARY_COLUMNS):
                profiles[_as_text(row_key)] = {
                    "name": _as_text(data.get(b"profile:name", "")).strip(),
                    "city": _as_text(data.get(b"profile:city", "")).strip(),
                }
            self._customer_profiles_cache = profiles
        return self._customer_profiles_cache

    def get_overall_statistics(self) -> Dict[str, Any]:
        """Return overall customer, order, activity, and revenue statistics."""

        orders = self._build_order_cache()
        activities = self._build_activity_cache()
        total_customers = sum(
            1 for _ in self._scan(CUSTOMERS_TABLE, [b"profile:name"])
        )
        total_orders = orders["total_orders"]
        valid_count = orders["valid_amount_orders"]
        delivered = orders["delivered_order_count"]
        cancelled = orders["cancelled_order_count"]
        pending = total_orders - delivered - cancelled

        return {
            "total_customers": total_customers,
            "total_orders": total_orders,
            "total_activities": activities["total_activities"],
            "gross_order_value": _plain_decimal(orders["gross_order_value"]),
            "total_revenue": _plain_decimal(orders["realized_revenue"]),
            "average_order_value": _plain_decimal(
                orders["gross_order_value"] / valid_count if valid_count else Decimal("0")
            ),
            "average_delivered_order_value": _plain_decimal(
                orders["realized_revenue"] / delivered if delivered else Decimal("0")
            ),
            "delivered_orders": delivered,
            "cancelled_orders": cancelled,
            "pending_orders": max(pending, 0),
            "malformed_amount_orders": orders["malformed_amount_count"],
        }

    def get_orders_by_status(self) -> Dict[str, int]:
        return dict(self._build_order_cache()["status_counts"])

    def get_orders_by_category(self) -> Dict[str, int]:
        return dict(self._build_order_cache()["category_counts"])

    def get_revenue_by_category(self) -> Dict[str, Dict[str, Any]]:
        orders = self._build_order_cache()
        categories = set(orders["category_counts"])
        return {
            category: {
                "order_count": orders["category_counts"][category],
                "gross_order_value": _plain_decimal(
                    orders["category_gross"][category]
                ),
                "realized_revenue": _plain_decimal(
                    orders["category_realized"][category]
                ),
                "average_order_value": _plain_decimal(
                    orders["category_gross"][category]
                    / orders["category_counts"][category]
                    if orders["category_counts"][category]
                    else Decimal("0")
                ),
            }
            for category in sorted(categories)
        }

    def get_top_products(self, limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        orders = self._build_order_cache()
        by_orders = [
            {
                "product": product,
                "order_count": count,
                "revenue": _plain_decimal(orders["product_realized"][product]),
            }
            for product, count in orders["product_order_counts"].most_common(limit)
        ]
        by_revenue = [
            {
                "product": product,
                "revenue": _plain_decimal(amount),
                "order_count": orders["product_order_counts"][product],
            }
            for product, amount in sorted(
                orders["product_realized"].items(),
                key=lambda item: (-item[1], item[0]),
            )[:limit]
        ]
        return {"by_order_count": by_orders, "by_revenue": by_revenue}

    def get_customers_by_city(self) -> Dict[str, int]:
        cities: Counter[str] = Counter()
        for profile in self._customer_profiles().values():
            cities[profile.get("city") or "Unknown"] += 1
        return dict(cities)

    def get_customer_directory(
        self,
        search: str = "",
        city: str = "",
        category: str = "",
        min_orders: int = 0,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Return filterable customer rows with order and activity summaries.

        The customer table is scanned with only the columns required by the
        directory. Order/activity totals reuse the process-level analytics
        caches, so repeated filter changes do not rescan those tables.
        """

        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if offset < 0:
            raise ValueError("offset must not be negative")
        if min_orders < 0:
            raise ValueError("min_orders must not be negative")

        profiles: List[Dict[str, str]] = []
        available_cities: set[str] = set()
        available_categories: set[str] = set()
        directory_columns = [
            b"profile:name",
            b"profile:city",
            b"preferences:category",
        ]
        for row_key, data in self._scan(CUSTOMERS_TABLE, directory_columns):
            profile = {
                "customer_id": _as_text(row_key),
                "name": _as_text(data.get(b"profile:name", "")).strip() or "Unknown",
                "city": _as_text(data.get(b"profile:city", "")).strip() or "Unknown",
                "category": _as_text(data.get(b"preferences:category", "")).strip()
                or "Unknown",
            }
            profiles.append(profile)
            available_cities.add(profile["city"])
            available_categories.add(profile["category"])

        orders = self._build_order_cache()
        activities = self._build_activity_cache()
        normalized_search = (search or "").strip().lower()
        normalized_city = (city or "").strip().lower()
        normalized_category = (category or "").strip().lower()
        filtered: List[Dict[str, Any]] = []

        for profile in profiles:
            customer_id = profile["customer_id"]
            if normalized_search and normalized_search not in (
                customer_id.lower(),
                profile["name"].lower(),
            ):
                continue
            if normalized_city and profile["city"].lower() != normalized_city:
                continue
            if normalized_category and profile["category"].lower() != normalized_category:
                continue
            order_count = orders["customer_order_counts"][customer_id]
            if order_count < min_orders:
                continue
            filtered.append(
                {
                    "customer_id": customer_id,
                    "name": profile["name"],
                    "city": profile["city"],
                    "category": profile["category"],
                    "order_count": order_count,
                    "total_spending": _plain_decimal(
                        orders["customer_realized"][customer_id]
                    ),
                    "activity_count": activities["customer_activity_counts"][customer_id],
                }
            )

        filtered.sort(
            key=lambda item: (
                -orders["customer_realized"][item["customer_id"]],
                item["customer_id"],
            )
        )
        total = len(filtered)
        return {
            "items": filtered[offset : offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
            "available_cities": sorted(available_cities),
            "available_categories": sorted(available_categories),
        }

    def _customer_rankings(self, limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        orders = self._build_order_cache()
        activities = self._build_activity_cache()
        profiles = self._customer_profiles()

        def customer_record(customer_id: str) -> Dict[str, Any]:
            profile = profiles.get(customer_id, {})
            return {
                "customer_id": customer_id,
                "name": profile.get("name", "Unknown"),
                "city": profile.get("city", "Unknown"),
                "order_count": orders["customer_order_counts"][customer_id],
                "total_spending": _plain_decimal(
                    orders["customer_realized"][customer_id]
                ),
                "gross_spending": _plain_decimal(orders["customer_gross"][customer_id]),
                "activity_count": activities["customer_activity_counts"][customer_id],
            }

        spending_ids = sorted(
            orders["customer_realized"],
            key=lambda customer_id: (
                -orders["customer_realized"][customer_id],
                customer_id,
            ),
        )[:limit]
        order_ids = sorted(
            orders["customer_order_counts"],
            key=lambda customer_id: (
                -orders["customer_order_counts"][customer_id],
                customer_id,
            ),
        )[:limit]
        active_ids = sorted(
            activities["customer_activity_counts"],
            key=lambda customer_id: (
                -activities["customer_activity_counts"][customer_id],
                customer_id,
            ),
        )[:limit]

        return {
            "by_total_spending": [customer_record(cid) for cid in spending_ids],
            "by_order_count": [customer_record(cid) for cid in order_ids],
            "most_active": [customer_record(cid) for cid in active_ids],
        }

    def get_top_customers(self, limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "by_total_spending": self._customer_rankings(limit)["by_total_spending"],
            "by_order_count": self._customer_rankings(limit)["by_order_count"],
        }

    def get_average_spending_per_customer(self) -> Decimal:
        total_customers = len(self._customer_profiles())
        revenue = self._build_order_cache()["realized_revenue"]
        return revenue / total_customers if total_customers else Decimal("0")

    def get_activity_statistics(self) -> Dict[str, Any]:
        activities = self._build_activity_cache()
        return {
            "total_activities": activities["total_activities"],
            "by_type": dict(activities["type_counts"]),
            "by_device": dict(activities["device_counts"]),
            "product_activity_counts": dict(activities["product_activity_counts"]),
            "top_products_by_activity": [
                {"product": product, "activity_count": count}
                for product, count in activities["product_activity_counts"].most_common(10)
            ],
            "top_active_customers": self._customer_rankings(10)["most_active"],
        }

    def get_most_active_customers(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self._customer_rankings(limit)["most_active"]

    def _read_customer_profile(self, customer_id: str) -> Dict[str, Any]:
        customer_table = self._table(CUSTOMERS_TABLE)
        try:
            profile_row = customer_table.row(
                customer_id.encode("utf-8"),
                columns=CUSTOMER_PROFILE_COLUMNS + CUSTOMER_PREFERENCE_COLUMNS,
            )
        except Exception as exc:
            raise AnalyticsError(f"Could not read customer '{customer_id}': {exc}") from exc
        if not profile_row:
            raise CustomerNotFoundError(f"Customer '{customer_id}' was not found in HBase.")

        profile = {
            key.split(":", 1)[1]: _as_text(profile_row.get(key.encode("utf-8"), ""))
            for key in (
                "profile:name",
                "profile:email",
                "profile:phone",
                "profile:age",
                "profile:city",
                "profile:registration_date",
            )
        }
        preferences = {
            key.split(":", 1)[1]: _as_text(profile_row.get(key.encode("utf-8"), ""))
            for key in ("preferences:category", "preferences:payment")
        }
        return {
            "customer_id": customer_id,
            "profile": profile,
            "preferences": preferences,
        }

    def get_customer_profile(self, customer_id: str) -> Dict[str, Any]:
        """Read only profile and preference columns for one customer."""

        return self._read_customer_profile(_validate_customer_id(customer_id))

    def _read_customer_orders(self, customer_id: str) -> Dict[str, Any]:
        """Read one customer's orders with a row-prefix scan."""

        order_history: List[Dict[str, Any]] = []
        delivered_total = Decimal("0")
        gross_total = Decimal("0")
        delivered_count = 0
        cancelled_count = 0
        pending_count = 0
        for row_key, data in self._scan(
            ORDERS_TABLE, ORDER_COLUMNS, row_prefix=f"{customer_id}#"
        ):
            amount = _decimal_amount(data.get(b"order:amount"))
            status = _as_text(data.get(b"order:status", "")).strip() or "Unknown"
            if amount is not None:
                gross_total += amount
                if status == DELIVERED:
                    delivered_total += amount
            if status == DELIVERED:
                delivered_count += 1
            elif status == CANCELLED:
                cancelled_count += 1
            else:
                pending_count += 1

            row_key_text = _as_text(row_key)
            order_id = row_key_text.split("#", 1)[1] if "#" in row_key_text else row_key_text
            order_history.append(
                {
                    "order_id": order_id,
                    "product": _as_text(data.get(b"order:product", "")),
                    "category": _as_text(data.get(b"order:category", "")),
                    "amount": _plain_decimal(amount) if amount is not None else None,
                    "date": _as_text(data.get(b"order:date", "")),
                    "status": status,
                }
            )

        order_count = len(order_history)
        return {
            "customer_id": customer_id,
            "orders": order_history,
            "order_summary": {
                "order_count": order_count,
                "gross_order_value": _plain_decimal(gross_total),
                "total_spending": _plain_decimal(delivered_total),
                "average_order_value": _plain_decimal(
                    gross_total / order_count if order_count else Decimal("0")
                ),
                "delivered_order_count": delivered_count,
                "cancelled_order_count": cancelled_count,
                "pending_order_count": pending_count,
            },
        }

    def get_customer_orders(self, customer_id: str) -> Dict[str, Any]:
        """Read only one customer's orders using a row-prefix scan."""

        return self._read_customer_orders(_validate_customer_id(customer_id))

    def _read_customer_activity(self, customer_id: str) -> Dict[str, Any]:
        """Read one customer's activities with a row-prefix scan."""

        activity_history: List[Dict[str, Any]] = []
        activity_counts: Counter[str] = Counter()
        for row_key, data in self._scan(
            ACTIVITY_TABLE, ACTIVITY_COLUMNS, row_prefix=f"{customer_id}#"
        ):
            row_key_text = _as_text(row_key)
            parts = row_key_text.split("#")
            timestamp = parts[1] if len(parts) > 1 else ""
            activity_id = parts[2] if len(parts) > 2 else ""
            activity_type = _as_text(data.get(b"activity:type", "")).strip() or "Unknown"
            activity_counts[activity_type] += 1
            activity_history.append(
                {
                    "timestamp": timestamp,
                    "activity_id": activity_id,
                    "type": activity_type,
                    "device": _as_text(data.get(b"activity:device", "")),
                    "product": _as_text(data.get(b"activity:product", "")),
                }
            )

        return {
            "customer_id": customer_id,
            "activity_summary": {
                "total_activities": len(activity_history),
                "by_type": dict(activity_counts),
            },
            "activities": activity_history,
        }

    def get_customer_activity(self, customer_id: str) -> Dict[str, Any]:
        """Read only one customer's activity rows using a row-prefix scan."""

        return self._read_customer_activity(_validate_customer_id(customer_id))

    def get_customer_360(self, customer_id: str) -> Dict[str, Any]:
        """Return profile, preferences, order history, and activity history."""

        customer_id = _validate_customer_id(customer_id)
        profile = self._read_customer_profile(customer_id)
        orders = self._read_customer_orders(customer_id)
        activities = self._read_customer_activity(customer_id)
        return {
            "customer_id": customer_id,
            "profile": profile["profile"],
            "preferences": profile["preferences"],
            "order_summary": orders["order_summary"],
            "order_history": orders["orders"],
            "activity_summary": activities["activity_summary"],
            "activity_history": activities["activities"],
        }


# Small module-level wrappers keep the requested function-oriented API while
# allowing the CLI to reuse one CustomerAnalytics instance for all sections.
def _one_shot(method_name: str, *args: Any, **kwargs: Any) -> Any:
    with CustomerAnalytics() as analytics:
        return getattr(analytics, method_name)(*args, **kwargs)


def get_overall_statistics() -> Dict[str, Any]:
    return _one_shot("get_overall_statistics")


def get_orders_by_status() -> Dict[str, int]:
    return _one_shot("get_orders_by_status")


def get_orders_by_category() -> Dict[str, int]:
    return _one_shot("get_orders_by_category")


def get_revenue_by_category() -> Dict[str, Dict[str, Any]]:
    return _one_shot("get_revenue_by_category")


def get_top_products(limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
    return _one_shot("get_top_products", limit)


def get_customers_by_city() -> Dict[str, int]:
    return _one_shot("get_customers_by_city")


def get_top_customers(limit: int = 10) -> Dict[str, List[Dict[str, Any]]]:
    return _one_shot("get_top_customers", limit)


def get_average_spending_per_customer() -> Decimal:
    return _one_shot("get_average_spending_per_customer")


def get_activity_statistics() -> Dict[str, Any]:
    return _one_shot("get_activity_statistics")


def get_most_active_customers(limit: int = 10) -> List[Dict[str, Any]]:
    return _one_shot("get_most_active_customers", limit)


def get_customer_360(customer_id: str) -> Dict[str, Any]:
    return _one_shot("get_customer_360", customer_id)


def _print_mapping(mapping: Mapping[str, Any], indent: str = "  ") -> None:
    for key, value in mapping.items():
        if isinstance(value, Mapping):
            print(f"{indent}{key}:")
            _print_mapping(value, indent + "  ")
        else:
            print(f"{indent}{key}: {value}")


def _print_overview(analytics: CustomerAnalytics) -> None:
    stats = analytics.get_overall_statistics()
    print("\n" + "=" * 54)
    print("HBASE CUSTOMER ANALYTICS DASHBOARD")
    print("=" * 54)
    print(f"Customers:                    {stats['total_customers']:,}")
    print(f"Orders:                       {stats['total_orders']:,}")
    print(f"Activities:                   {stats['total_activities']:,}")
    print(f"Gross order value:            {_money(Decimal(str(stats['gross_order_value'])))}")
    print(f"Realized revenue (Delivered): {_money(Decimal(str(stats['total_revenue'])))}")
    print(f"Average order value:          {_money(Decimal(str(stats['average_order_value'])))}")
    print(f"Delivered orders:             {stats['delivered_orders']:,}")
    print(f"Cancelled orders:             {stats['cancelled_orders']:,}")
    print(f"Pending/non-delivered:        {stats['pending_orders']:,}")
    if stats["malformed_amount_orders"]:
        print(f"Skipped malformed amounts:    {stats['malformed_amount_orders']:,}")


def _print_orders(analytics: CustomerAnalytics) -> None:
    cache = analytics._build_order_cache()
    print("\nORDER ANALYTICS")
    print("-" * 54)
    print("Orders by status:")
    for status, count in cache["status_counts"].most_common():
        print(f"  {status:<18} {count:,}")
    print("\nRevenue by category (realized / gross):")
    for category, values in analytics.get_revenue_by_category().items():
        print(
            f"  {category:<18} {_money(Decimal(str(values['realized_revenue'])))}"
            f" / {_money(Decimal(str(values['gross_order_value'])))}"
        )
    print("\nTop products by order count:")
    for item in analytics.get_top_products()["by_order_count"][:10]:
        print(f"  {item['product']:<24} {item['order_count']:,}")
    print("Top products by realized revenue:")
    for item in analytics.get_top_products()["by_revenue"][:10]:
        print(f"  {item['product']:<24} {_money(Decimal(str(item['revenue'])))}")


def _print_customers(analytics: CustomerAnalytics) -> None:
    print("\nCUSTOMER ANALYTICS")
    print("-" * 54)
    print("Customers by city:")
    for city, count in sorted(analytics.get_customers_by_city().items()):
        print(f"  {city:<18} {count:,}")
    rankings = analytics._customer_rankings(10)
    print("\nTop customers by realized spending:")
    for item in rankings["by_total_spending"]:
        print(
            f"  {item['customer_id']} | {item['name'][:22]:<22} | "
            f"{item['city']:<12} | {item['order_count']:>2} orders | "
            f"{_money(Decimal(str(item['total_spending'])))}"
        )
    print(
        f"\nAverage spending per customer: "
        f"{_money(analytics.get_average_spending_per_customer())}"
    )


def _print_activities(analytics: CustomerAnalytics) -> None:
    stats = analytics.get_activity_statistics()
    print("\nACTIVITY ANALYTICS")
    print("-" * 54)
    print("Activities by type:")
    for activity_type, count in sorted(stats["by_type"].items()):
        print(f"  {activity_type:<18} {count:,}")
    print("Activities by device:")
    for device, count in sorted(stats["by_device"].items()):
        print(f"  {device:<18} {count:,}")
    print("Top products by activity:")
    for item in stats["top_products_by_activity"]:
        print(f"  {item['product']:<24} {item['activity_count']:,}")
    print("Top active customers:")
    for item in stats["top_active_customers"]:
        print(f"  {item['customer_id']} | {item['name'][:22]:<22} | {item['activity_count']:,} activities")


def _print_customer_360(analytics: CustomerAnalytics, customer_id: str) -> None:
    result = analytics.get_customer_360(customer_id)
    profile = result["profile"]
    summary = result["order_summary"]
    activity = result["activity_summary"]
    print("\n" + "=" * 54)
    print("CUSTOMER 360")
    print("=" * 54)
    print(f"Customer ID: {result['customer_id']}")
    print(f"Name:        {profile.get('name', '')}")
    print(f"Email:       {profile.get('email', '')}")
    print(f"City:        {profile.get('city', '')}")
    print(f"Orders:      {summary['order_count']}")
    print(f"Total Spending (Delivered): {_money(Decimal(str(summary['total_spending'])))}")
    print(f"Average Order Value:        {_money(Decimal(str(summary['average_order_value'])))}")
    print("\nActivity Summary:")
    for activity_type, count in sorted(activity["by_type"].items()):
        print(f"  {activity_type.replace('_', ' ').title():<18} {count}")
    print(f"\nOrder history:    {len(result['order_history'])} rows")
    print(f"Activity history: {len(result['activity_history'])} rows")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze the existing Apache HBase customer database."
    )
    parser.add_argument("--overview", action="store_true", help="show overall statistics")
    parser.add_argument("--orders", action="store_true", help="show order analytics")
    parser.add_argument("--customers", action="store_true", help="show customer analytics")
    parser.add_argument("--activities", action="store_true", help="show activity analytics")
    parser.add_argument(
        "--customer",
        metavar="CUSTOMER_ID",
        help="show Customer 360, for example CUST000001",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    sections_requested = any((args.overview, args.orders, args.customers, args.activities))
    if args.customer and sections_requested:
        # A requested section plus --customer is useful in a presentation, so
        # print both using the same connection.
        pass

    try:
        with CustomerAnalytics() as analytics:
            if not sections_requested and not args.customer:
                _print_overview(analytics)
                _print_orders(analytics)
                _print_customers(analytics)
                _print_activities(analytics)
            else:
                if args.overview:
                    _print_overview(analytics)
                if args.orders:
                    _print_orders(analytics)
                if args.customers:
                    _print_customers(analytics)
                if args.activities:
                    _print_activities(analytics)
            if args.customer:
                _print_customer_360(analytics, args.customer)
    except (AnalyticsError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
