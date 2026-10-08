"""Measure real HappyBase operations against the existing HBase tables."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Callable, Iterable, Optional, Tuple

from customer_analytics import (
    ACTIVITY_TABLE,
    CUSTOMERS_TABLE,
    HBaseConnectionError,
    ORDERS_TABLE,
    CustomerAnalytics,
)


DEFAULT_CUSTOMER_ID = "CUST000001"


def _timed(operation: Callable[[], int]) -> Tuple[int, float]:
    started = time.perf_counter()
    rows = operation()
    elapsed = time.perf_counter() - started
    return rows, elapsed


def _count_scan(table, columns: Iterable[bytes], row_prefix: Optional[str] = None) -> int:
    kwargs = {"columns": list(columns)}
    if row_prefix is not None:
        kwargs["row_prefix"] = row_prefix.encode("utf-8")
    return sum(1 for _ in table.scan(**kwargs))


def run_benchmark(customer_id: str, sample_size: int) -> dict[str, object]:
    """Run all benchmarks over one shared HBase connection."""

    with CustomerAnalytics() as analytics:
        connection = analytics.connection
        customers = connection.table(CUSTOMERS_TABLE)
        orders = connection.table(ORDERS_TABLE)
        activities = connection.table(ACTIVITY_TABLE)

        customer_rows, customer_seconds = _timed(
            lambda: 1
            if customers.row(
                customer_id.encode("utf-8"),
                columns=[b"profile:name", b"profile:city"],
            )
            else 0
        )

        order_rows, order_seconds = _timed(
            lambda: _count_scan(
                orders,
                [b"order:product", b"order:amount", b"order:status"],
                row_prefix=f"{customer_id}#",
            )
        )

        activity_rows, activity_seconds = _timed(
            lambda: _count_scan(
                activities,
                [b"activity:type", b"activity:device", b"activity:product"],
                row_prefix=f"{customer_id}#",
            )
        )

        sample_ids = [f"CUST{i:06d}" for i in range(1, sample_size + 1)]

        def multiple_lookups() -> int:
            rows = 0
            for sample_id in sample_ids:
                if customers.row(sample_id.encode("utf-8"), columns=[b"profile:name"]):
                    rows += 1
            return rows

        multiple_rows, multiple_seconds = _timed(multiple_lookups)

        def analytics_scan() -> int:
            rows = 0
            rows += _count_scan(orders, [b"order:category", b"order:amount", b"order:status"])
            rows += _count_scan(activities, [b"activity:type", b"activity:device", b"activity:product"])
            rows += _count_scan(customers, [b"profile:name", b"profile:city"])
            return rows

        analytics_rows, analytics_seconds = _timed(analytics_scan)

    return {
        "customer_lookup": {"rows": customer_rows, "seconds": customer_seconds},
        "order_prefix_scan": {"rows": order_rows, "seconds": order_seconds},
        "activity_prefix_scan": {"rows": activity_rows, "seconds": activity_seconds},
        "multiple_lookups": {
            "rows": multiple_rows,
            "seconds": multiple_seconds,
            "sample_size": sample_size,
        },
        "analytics_scan": {"rows": analytics_rows, "seconds": analytics_seconds},
    }


def _print_result(results: dict[str, object], customer_id: str) -> None:
    print("=" * 40)
    print("HBASE PERFORMANCE TEST")
    print("=" * 40)
    print(f"Customer ID: {customer_id}")
    print("\nCustomer Lookup")
    item = results["customer_lookup"]
    print(f"Rows: {item['rows']}")
    print(f"Time: {item['seconds'] * 1000:.2f} ms")

    print("\nCustomer Order Prefix Scan")
    item = results["order_prefix_scan"]
    print(f"Rows: {item['rows']}")
    print(f"Time: {item['seconds'] * 1000:.2f} ms")

    print("\nCustomer Activity Prefix Scan")
    item = results["activity_prefix_scan"]
    print(f"Rows: {item['rows']}")
    print(f"Time: {item['seconds'] * 1000:.2f} ms")

    print(f"\n{results['multiple_lookups']['sample_size']} Customer Lookups")
    item = results["multiple_lookups"]
    average_ms = item["seconds"] * 1000 / item["sample_size"] if item["sample_size"] else 0
    print(f"Rows: {item['rows']}")
    print(f"Total Time: {item['seconds'] * 1000:.2f} ms")
    print(f"Average: {average_ms:.2f} ms/customer")

    print("\nAnalytics Scan")
    item = results["analytics_scan"]
    print(f"Rows: {item['rows']}")
    print(f"Time: {item['seconds']:.3f} seconds")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customer", default=DEFAULT_CUSTOMER_ID)
    parser.add_argument("--sample-size", type=int, default=100)
    args = parser.parse_args(argv)
    if args.sample_size < 1:
        parser.error("--sample-size must be at least 1")

    try:
        results = run_benchmark(args.customer, args.sample_size)
        _print_result(results, args.customer)
    except (HBaseConnectionError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
