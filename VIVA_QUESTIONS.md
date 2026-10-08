# Viva Questions and Short Answers

## HBase fundamentals

**What is HBase?**  HBase is a distributed, column-family NoSQL database built
for random, scalable reads and writes over large sparse tables.

**Why is HBase NoSQL?**  It does not require a relational schema with joins and
uses row keys, column families, and cells instead of fixed relational rows.

**HBase vs MySQL?**  MySQL is relational and strong at joins and transactions;
HBase is designed for distributed wide-table access by row key at scale.

**HBase vs MongoDB?**  MongoDB stores JSON-like documents; HBase stores sorted
rows with column families and is closely integrated with the Hadoop ecosystem.

**What is a column family?**  A named group of columns physically organized
together in an HBase table. Families should be chosen around access patterns.

**What is a row key?**  The unique sorted key used to locate and order a row.

**What is a region?**  A horizontal range of a table's row-key space.

**What is a RegionServer?**  A server process that hosts regions and serves
reads and writes for them.

**What is HMaster?**  The service that coordinates region assignment, table
operations, and cluster management.

**What is ZooKeeper?**  A coordination service used for discovery, liveness,
and cluster state.

**What is an HFile?**  A persistent sorted storage file used by HBase after
data is flushed and compacted.

**What is WAL?**  The write-ahead log records updates before persistence so
HBase can recover writes after a failure.

## Project-specific questions

**Why choose HBase?**  Customer histories are semi-structured and naturally
retrieved by customer ID, which fits HBase row keys, sparse columns, and scans.

**Why three tables?**  Each table supports a clear access pattern: profile by
customer, orders by customer prefix, and activity by customer/time prefix.

**Why these column families?**  Profile and preferences are separated because
they represent distinct groups of customer attributes; child tables keep their
own family for focused reads.

**Why this row-key design?**  Starting child keys with the customer ID keeps
that customer's rows together and enables prefix scans.

**Why use prefix scans?**  They retrieve a customer's related rows directly
from the sorted key range without scanning all customers.

**How does HBase scale?**  Tables are split into regions and regions are
distributed across RegionServers.

**What happens when data grows?**  Regions can split and move, but schema,
row-key distribution, compaction, capacity, and scan patterns must be managed.

**What is hotspotting?**  Uneven traffic caused by keys that repeatedly target
the same region or narrow key range.

**How can hotspotting be reduced?**  Use a suitable hash/salt prefix, reverse
timestamps, or another key design that spreads the workload while preserving
the required lookup path.

**Why not use joins?**  HBase favors denormalized access paths. The application
reads the related rows it needs instead of relying on relational joins.

**How is Customer 360 implemented?**  It reads one profile row and performs
customer-prefix scans on the orders and activity tables, then returns a
structured combined result.

**How much data was generated?**  Approximately 10,000 customers, 50,000
orders, and 100,000 activities; the exact current counts are measured from
HBase rather than assumed.

**How was performance tested?**  `time.perf_counter()` measures direct lookup,
two prefix scans, 100 customer lookups, and broad analytics scans against the
live Thrift endpoint.

**What are the current Docker limitations?**  It is a single-node development
setup, so it cannot prove distributed throughput, failover, or production
hotspot behavior.

**How would you deploy this in production?**  Use multiple RegionServers,
durable HDFS, ZooKeeper quorum, security, monitoring, backups, capacity
planning, and measured row-key/region design.
