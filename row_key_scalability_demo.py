"""Demonstrate deterministic salted row keys without changing HBase tables."""

from __future__ import annotations

import hashlib
from typing import Iterable, Tuple


def customer_salt(customer_id: str, salt_width: int = 2) -> str:
    """Return a deterministic hexadecimal prefix derived from a customer ID."""

    if salt_width < 1:
        raise ValueError("salt_width must be positive")
    digest = hashlib.sha1(customer_id.encode("utf-8")).hexdigest().upper()
    return digest[:salt_width]


def salted_order_key(customer_id: str, order_id: str, salt_width: int = 2) -> str:
    return f"{customer_salt(customer_id, salt_width)}#{customer_id}#{order_id}"


def normal_order_key(customer_id: str, order_id: str) -> str:
    return f"{customer_id}#{order_id}"


def demonstrate(rows: Iterable[Tuple[str, str]]) -> None:
    print("=" * 54)
    print("HBASE ROW-KEY SCALABILITY DEMONSTRATION")
    print("=" * 54)
    print("Current key -> salted demonstration key")
    for customer_id, order_id in rows:
        normal = normal_order_key(customer_id, order_id)
        salted = salted_order_key(customer_id, order_id)
        print(f"{normal:<32} -> {salted}")
        print(f"  Calculated salt for lookup: {customer_salt(customer_id)}")

    print("\nThe existing project key keeps a customer's rows adjacent, so a prefix")
    print("scan on CUST000001# efficiently retrieves that customer's orders.")
    print("A salted key spreads the leading bytes across the keyspace, reducing")
    print("theoretical write concentration in a distributed RegionServer cluster.")
    print("The salt is deterministic, so a lookup can calculate the required")
    print("prefix before scanning. This demonstration does not write to HBase.")


if __name__ == "__main__":
    demonstrate(
        [
            ("CUST000001", "ORD00000001"),
            ("CUST000002", "ORD00000002"),
            ("CUST000003", "ORD00000003"),
        ]
    )
