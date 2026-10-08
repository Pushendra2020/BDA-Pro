# Design and Implementation of a Scalable NoSQL Customer Database Using Apache HBase

## Problem statement

Customer systems combine profiles, orders, and event activity. The data is
semi-structured, grows over time, and is commonly queried by customer ID. This
project stores those access patterns in Apache HBase and adds analytics,
performance measurements, an API, and a small dashboard.

## Objectives

- Design a NoSQL schema using HBase.
- Store customer profiles, orders, and customer activity.
- Retrieve customer history with row-prefix scans.
- Calculate business and activity analytics from HBase.
- Demonstrate row-key and scalability trade-offs.
- Provide a FastAPI layer and a React/Vite dashboard.

## Architecture

```text
React + Vite + Tailwind CSS
            ↓
          FastAPI
            ↓
         HappyBase
            ↓
           HBase
            ↓
          Docker
```

HBase remains the source of truth. The analytics module aggregates scan
results in process; it does not copy the database to another database or
replace HBase with a relational store.

## HBase schema

| Table | Row key | Column families | Main use |
|---|---|---|---|
| `customers` | `customer_id` | `profile`, `preferences` | Customer profile and preferences |
| `customer_orders` | `customer_id#order_id` | `order` | Customer order history |
| `customer_activity` | `customer_id#timestamp#activity_id` | `activity` | Customer event history |

The existing dataset is approximately 10,000 customers, 50,000 orders, and
100,000 activities. Run the performance script for current live row counts.

## Analytics

`customer_analytics.py` provides:

- Overall counts, gross order value, delivered revenue, average order value,
  delivered/cancelled/pending order counts.
- Orders by status and category.
- Gross and realized revenue by category.
- Top products by order count and realized revenue.
- Customers by city and ranked customers by spending/order count.
- Activity counts by type, device, and product.
- Customer 360 profile, preferences, order summary/history, and activity
  summary/history.

Delivered orders are treated as realized revenue. Gross order value is shown
separately and includes all valid order amounts.

## Performance and scalability

Run:

```powershell
conda run -n hbase python hbase_performance_test.py
conda run -n hbase python row_key_scalability_demo.py
```

See [SCALABILITY.md](SCALABILITY.md) for HBase architecture, prefix scans,
hotspotting, and the salted-key demonstration.

## API

Start the backend from this directory:

```powershell
conda activate hbase
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

Endpoints:

```text
GET /api/customers?search=&city=&category=&min_orders=&limit=&offset=
GET /api/customers/{customer_id}
GET /api/customers/{customer_id}/orders
GET /api/customers/{customer_id}/activity
GET /api/customers/{customer_id}/360
GET /api/analytics/overview
GET /api/analytics/categories
GET /api/analytics/top-customers
GET /api/analytics/activity
```

The customer-directory endpoint supports server-side search, city/category
filters, minimum-order filtering, and pagination. The dashboard's Customers
page displays those results in a responsive table; each row can open the
existing Customer 360 view.

## Dashboard

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`. The frontend
loads live API values, displays overview/category/activity analytics, ranks top
customers, and searches for a Customer 360 record.

## Running analytics directly

```powershell
conda run -n hbase python customer_analytics.py
conda run -n hbase python customer_analytics.py --overview
conda run -n hbase python customer_analytics.py --customer CUST000001
```

The HBase Docker/Thrift service must already be available at
`localhost:9090`. This repository does not recreate or populate the existing
database.

## Documentation and viva material

- [PROJECT_REPORT_NOTES.md](PROJECT_REPORT_NOTES.md)
- [VIVA_QUESTIONS.md](VIVA_QUESTIONS.md)

## Limitations

The current HBase instance is a single-node Docker development environment.
It is suitable for demonstrating schema, query, and application behavior, but
does not prove production distributed throughput, failover, or cluster-scale
latency.
