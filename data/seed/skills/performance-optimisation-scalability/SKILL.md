---
name: performance-optimisation-scalability
description: "Profiling, optimising, and scaling software for production workloads"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - development
  - coding
  - senior-developer
  - performance
  - scalability
---

# Performance Optimisation & Scalability

The ability to identify performance bottlenecks, apply targeted optimisations,
and design for scalability. Covers profiling, benchmarking, caching strategies,
database optimisation, and scaling patterns for growing workloads.

STEP-BY-STEP PROCEDURE

STEP 1: MEASURE BEFORE OPTIMISING
  Never optimise based on intuition — measure first:

  PROFILING:
  - CPU profiling: Which functions consume the most CPU time?
  - Memory profiling: Where is memory allocated? Are there leaks?
  - I/O profiling: Which operations block on disk, network, or database?
  - Trace profiling: End-to-end request flow with timing per component

  BENCHMARKING:
  - Establish a baseline: Record current latency (p50, p95, p99), throughput
    (requests/second), and resource usage (CPU%, memory, connections)
  - Use representative data: Benchmark with production-like volumes, not
    tiny test datasets
  - Run benchmarks in a consistent environment (same hardware, same load)
  - Automate benchmarks so they can be re-run after every change

  MONITORING:
  - Application metrics: Request latency, error rate, throughput
  - Infrastructure metrics: CPU, memory, disk I/O, network
  - Database metrics: Query latency, slow query log, connection pool usage
  - Alerting: Set thresholds for degradation (e.g. p95 > 500ms)

  Rule: If you can't measure the improvement, don't make the change.

STEP 2: OPTIMISE DATABASE QUERIES
  Database operations are the #1 bottleneck in most applications:

  QUERY OPTIMISATION:
  - Use EXPLAIN / EXPLAIN ANALYZE to understand query execution plans
  - Add indexes for columns used in WHERE, JOIN, ORDER BY, GROUP BY
  - Avoid SELECT * — only fetch the columns you need
  - Avoid N+1 queries: Use JOINs or batch fetches instead of loops
    BAD:  for user in users: fetch_orders(user.id)  # N queries
    GOOD: fetch_orders_for_users([u.id for u in users])  # 1 query
  - Use pagination for large result sets (LIMIT/OFFSET or cursor-based)
  - Avoid expensive operations in tight loops (string concatenation,
    repeated parsing, unnecessary serialisation)

  INDEXING STRATEGY:
  - Index columns used in WHERE clauses of frequent queries
  - Composite indexes: Order matters — most selective column first
  - Partial indexes: Index only the rows that matter (e.g. WHERE active=true)
  - Monitor unused indexes — they slow down writes for no benefit
  - Review slow query logs weekly

  CONNECTION MANAGEMENT:
  - Use connection pooling (PgBouncer, HikariCP, SQLAlchemy pool)
  - Set pool size based on workload (too small = queuing, too large = overhead)
  - Close connections properly — leaked connections exhaust the pool

STEP 3: APPLY CACHING STRATEGIES
  Cache frequently read, rarely changed data:

  CACHING LEVELS:
  - Application-level: In-memory cache (LRU, TTL-based) for hot data
  - Distributed cache: Redis or Memcached for shared state across instances
  - HTTP caching: Cache-Control headers, ETags, CDN for static assets
  - Query result caching: Cache expensive database query results

  CACHE INVALIDATION (the hard part):
  - Time-based (TTL): Simplest — data expires after N seconds
  - Event-based: Invalidate when the source data changes
  - Write-through: Update cache when writing to the database
  - Cache-aside: Application checks cache first, falls back to database,
    populates cache on miss

  Rules:
  - Only cache data that is read frequently and changes infrequently
  - Set appropriate TTLs — stale data is a common source of bugs
  - Monitor cache hit rate — if < 80%, the cache may not be helping
  - Plan for cache failures — the app must work (slowly) without cache

STEP 4: OPTIMISE APPLICATION CODE
  After database and caching, look at the application layer:

  ALGORITHMIC IMPROVEMENTS:
  - Replace O(n^2) with O(n log n) or O(n) where possible
  - Use hash maps for frequent lookups instead of scanning lists
  - Use generators/iterators for large datasets instead of loading all
    into memory at once
  - Avoid redundant computation: memoize pure functions

  ASYNC AND CONCURRENCY:
  - Use async I/O for network-bound operations (API calls, DB queries)
  - Use thread pools for CPU-bound work (if the language supports it)
  - Batch operations: Send 1 request with 100 items, not 100 requests
  - Use connection pooling and keep-alive for HTTP clients

  SERIALISATION:
  - JSON is human-readable but slow for high-volume internal comms
  - Consider MessagePack, Protocol Buffers, or FlatBuffers for
    inter-service communication where performance matters
  - Profile serialisation/deserialisation — it's often a hidden cost

  MEMORY:
  - Avoid creating unnecessary intermediate objects
  - Use streaming for large file processing (don't load entire file)
  - Watch for memory leaks: growing collections, event handlers not removed,
    circular references preventing garbage collection
  - Profile memory with language-specific tools

STEP 5: DESIGN FOR SCALABILITY
  Plan for growth before you need it:

  HORIZONTAL SCALING:
  - Stateless services: No in-memory state between requests
  - Session storage: External store (Redis, database), not local memory
  - Load balancing: Round-robin, least connections, or weighted
  - Database read replicas for read-heavy workloads

  VERTICAL SCALING:
  - Increase CPU, RAM, or I/O capacity of existing instances
  - Simpler but has a ceiling — use as a short-term bridge

  DATA SCALING:
  - Partitioning: Split data by tenant, region, or time range
  - Sharding: Distribute data across multiple database instances
  - Archiving: Move old data to cold storage to keep active dataset small
  - Read/write splitting: Route reads to replicas, writes to primary

  ASYNC PROCESSING:
  - Use message queues (RabbitMQ, Kafka, SQS) for work that doesn't
    need an immediate response
  - Background jobs for email sending, report generation, data processing
  - Event sourcing for high-write workloads

STEP 6: LOAD TESTING
  Verify your system handles expected (and unexpected) load:

  TEST TYPES:
  - Load test: Expected production traffic — does it meet SLAs?
  - Stress test: 2-3x expected traffic — where does it break?
  - Soak test: Sustained load over hours — any memory leaks or degradation?
  - Spike test: Sudden burst — does auto-scaling respond fast enough?

  PROCESS:
  1. Define target: "Handle 1000 req/s at p95 < 200ms"
  2. Create realistic test scenarios (mix of endpoints, data sizes)
  3. Run baseline test and record metrics
  4. Identify bottlenecks from profiling and monitoring
  5. Optimise the bottleneck
  6. Re-run test and compare
  7. Repeat until target is met

TOOLS & RESOURCES
- Profiling: cProfile/py-spy (Python), Chrome DevTools/clinic.js (Node),
  pprof (Go), async-profiler (JVM)
- Load testing: k6, Locust, JMeter, Artillery
- Monitoring: Prometheus + Grafana, Datadog, New Relic
- Caching: Redis, Memcached, Varnish
- Database: pganalyze, slow query logs, EXPLAIN visualisers

QUALITY STANDARDS
- All optimisations backed by profiling data, not guesswork
- Benchmarks automated and tracked over time
- p95 latency meets SLA targets for all critical endpoints
- No N+1 queries in production code
- Cache hit rate > 80% for cached resources
- Load tests run before every major release
- Memory usage stable under sustained load (no leaks)
- Scaling plan documented for 10x current traffic
