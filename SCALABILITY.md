# HBase Scalability Notes

This project demonstrates an HBase-backed customer database in a Docker
development environment. The current setup is a single-node environment, so
the scalability discussion below describes HBase's architecture and design
trade-offs without claiming production-cluster measurements.

## HBase architecture

```text
HBase
├── HMaster
├── RegionServer
├── Regions
├── HFiles
└── ZooKeeper
```

- **HMaster** coordinates table and region-management operations. It assigns
  regions and monitors RegionServers; it is not on the normal data path for
  every read.
- **RegionServer** serves reads and writes for the regions assigned to it.
- **Regions** are horizontal partitions of a table's sorted row-key space. A
  large table can be split into multiple regions and distributed across
  RegionServers.
- **HFiles** are the persistent, sorted files written to HDFS in a production
  deployment. MemStores and write-ahead logs protect and stage updates before
  compaction produces HFiles.
- **ZooKeeper** coordinates cluster state, discovery, and liveness information
  used by HBase services.

## Current row-key design

The existing tables use these keys:

```text
customers:
CUST000001

customer_orders:
CUST000001#ORD00000001

customer_activity:
CUST000001#timestamp#activity_id
```

The customer ID is the leading portion of both child-table keys. Therefore the
application can retrieve one customer's related rows with a prefix scan such
as `CUST000001#` instead of scanning and filtering the complete table. This is
why the Customer 360 code uses targeted HBase prefix scans.

The trade-off is that rows for one customer are intentionally colocated in the
sorted keyspace. That makes customer-specific reads simple and efficient, but
it can concentrate traffic if one customer receives a very large number of
writes.

## Hotspotting

HBase writes are ordered by row key within regions. Sequential or highly
ordered keys can repeatedly target the region containing the newest key range.
In a distributed cluster this can create a hotspot: one RegionServer does most
of the write work while other servers are underused.

This Docker project is a single-node development environment, so it does not
demonstrate a production hotspot or distributed throughput limit. The issue is
still important when evolving the design.

## Salted/hash-prefixed alternative

`row_key_scalability_demo.py` shows a deterministic alternative:

```text
07#CUST000001#ORD00000001
13#CUST000002#ORD00000002
A4#CUST000003#ORD00000003
```

The prefix is derived from a stable hash of the customer ID. Different
customers are distributed across more leading key prefixes, which can reduce
write concentration when regions are split. The application can calculate the
salt for a known customer before a lookup.

Salting has a cost: a global order scan no longer follows the natural customer
prefix, and applications must know the salt scheme. It also does not make a
single customer's own writes parallel by itself. A production design would
choose the salt width and query/index strategy from measured access patterns.

The demonstration is intentionally standalone and does not modify the current
HBase schema or tables.

## Other scaling considerations

- HBase scales horizontally by splitting regions and assigning them to more
  RegionServers.
- Denormalization is normal: the three tables support the access patterns
  directly instead of relying on relational joins.
- Column-family selection reduces the bytes fetched for targeted reads.
- Prefix scans are appropriate for customer history; broad analytics scans are
  more expensive and should be scheduled, cached, or pre-aggregated if the
  dataset grows substantially.
- Production deployments require operational concerns not present here,
  including HDFS capacity, replication, compaction tuning, backups, security,
  and cluster monitoring.
