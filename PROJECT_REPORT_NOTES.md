# Project Report Notes

## Abstract

This project designs and implements a NoSQL customer database using Apache
HBase. Customer profiles, orders, and activity events are stored in separate
tables with row keys designed around customer-specific access. HappyBase
connects Python applications to HBase Thrift. An analytics module, performance
benchmark, FastAPI backend, and React dashboard demonstrate how the data can be
queried and presented while keeping HBase as the source of truth.

## Introduction

Modern customer systems combine structured profile attributes with changing
order and event data. A useful system must support large, semi-structured
datasets and frequent retrieval of one customer's history. This project
explores those requirements with HBase's sorted row-key model and column
families.

## Problem Statement

Build a customer data system that stores profiles, orders, and activity, allows
customer-specific retrieval, supports analytics, and demonstrates scalable
NoSQL design without depending on relational joins.

## Objectives

1. Design an HBase schema for three related access patterns.
2. Populate and query customer, order, and activity data.
3. Use prefix scans for Customer 360 retrieval.
4. Calculate operational and business analytics.
5. Measure real HBase operation timings.
6. Expose the data through an API and dashboard.
7. Explain row-key scalability and hotspotting.

## Existing System

A conventional relational design would use tables and joins for customers,
orders, and activities. Joins are useful, but very large event histories can
require additional partitioning and scaling design. A document-only approach
can simplify aggregation but may duplicate or index data differently.

## Proposed System

The proposed system uses Apache HBase tables designed around access patterns:
one table for profiles, one for orders, and one for activities. Python uses
HappyBase over HBase Thrift. FastAPI provides HTTP endpoints and the React
dashboard calls those endpoints.

## Why HBase

HBase provides a distributed, sorted key-value data model on top of the Hadoop
ecosystem. It supports column families, sparse rows, random reads by row key,
and ordered scans. These properties fit customer histories and semi-structured
activity events. The current project demonstrates the model in a single-node
Docker environment; it does not claim a production cluster deployment.

## System Architecture

```text
Browser dashboard
       ↓ HTTP/JSON
FastAPI service
       ↓ HappyBase / Thrift
Apache HBase
       ↓
Docker development environment
```

## Database Design

### `customers`

Row key: `customer_id`, for example `CUST000001`.

Families: `profile` and `preferences`.

### `customer_orders`

Row key: `customer_id#order_id`.

Family: `order`, with product, category, amount, date, and status columns.

### `customer_activity`

Row key: `customer_id#timestamp#activity_id`.

Family: `activity`, with type, device, and optional product columns.

## Row-Key Design

The customer ID is the first component of child-table keys. A prefix scan on
`CUST000001#` retrieves only that customer's orders or activities. This is
efficient for Customer 360 access, but a distributed workload must consider
write concentration and hotspotting. `row_key_scalability_demo.py` shows a
deterministic hash prefix without changing the active tables.

## Data Generation

The existing scripts generate approximately 10,000 customers, 50,000 orders,
and 100,000 activities. The analytics and benchmark scripts never regenerate
that data. The active database is treated as the source of truth.

## Query Operations

- Direct customer row lookup uses `table.row()`.
- Customer order and activity histories use `table.scan()` with a row prefix.
- Analytics use selected columns while scanning each table.
- The API uses targeted scans for customer endpoints and reuses one HBase
  connection per backend process.

## Analytics

The analytics layer calculates overall totals, order status/category metrics,
realized revenue, product rankings, city counts, customer rankings, activity
counts, and Customer 360 output. Delivered orders count as realized revenue;
gross order value is kept separately.

## Scalability

HBase scales through regions and RegionServers. The current key design favors
customer-local reads. A salted/hash-prefixed alternative can spread leading
key prefixes, but it adds lookup complexity and can make global scans less
natural. See `SCALABILITY.md` for the detailed discussion.

## Performance Testing

`hbase_performance_test.py` measures a direct lookup, customer order prefix
scan, customer activity prefix scan, multiple customer lookups, and the broad
analytics scans. It uses `time.perf_counter()` and prints measured rows and
elapsed time; results depend on the local Docker, Thrift, and machine state.

## Results

At the implementation validation point, the live database returned 10,000
customers, 50,292 orders, and 99,712 activities. `CUST000001` returned 8
orders and 12 activities. These values are observations of the current local
database, not hardcoded application output; rerun the scripts for updated
values and timings.

## Limitations

- Single-node Docker HBase does not demonstrate distributed production
  throughput, high availability, or failover.
- Broad analytics scans become more expensive as the dataset grows.
- The API does not yet provide authentication, pagination, or precomputed
  analytics storage.
- The salted-key example is a design demonstration, not a migration of the
  existing schema.

## Future Scope

- Add pagination and date filters for histories.
- Add authentication and role-based access.
- Add scheduled/precomputed aggregates for large analytics workloads.
- Test with a multi-RegionServer cluster and measure region distribution.
- Add monitoring, retries, connection pooling, and production deployment
  configuration.

## Conclusion

The project demonstrates an HBase-centered customer system from storage and
row-key design through analytics, HTTP APIs, and a dashboard. It shows how
prefix scans and column-family selection support customer-centric access while
making the limitations of a single-node development environment explicit.
