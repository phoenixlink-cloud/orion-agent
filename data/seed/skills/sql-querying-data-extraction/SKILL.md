---
name: sql-querying-data-extraction
description: "Writing efficient, accurate SQL queries to extract, transform, and analyse"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - data
  - analytics
  - business-intelligence
  - data-analyst
---

SKILL: SQL QUERYING & DATA EXTRACTION

SKILL ID:       DA-SK-001
ROLE:           Data Analyst
CATEGORY:       Data Engineering & Extraction
DIFFICULTY:     Intermediate to Advanced
ESTIMATED TIME: Ongoing (core daily skill)

DESCRIPTION
Writing efficient, accurate SQL queries to extract, transform, and analyse
data from relational databases. This covers query optimisation, complex joins,
window functions, CTEs, subqueries, and building reusable query libraries for
recurring analytical needs.

STEP-BY-STEP PROCEDURE

STEP 1: UNDERSTAND THE DATA MODEL
  Before writing any query:
  - Review the database schema: Tables, columns, data types, relationships
  - Identify primary keys, foreign keys, and join paths
  - Understand the grain: What does one row represent in each table?
  - Check for data quirks: NULLs, duplicates, soft deletes, time zones
  - Document your understanding in a data dictionary if one doesn't exist

STEP 2: TRANSLATE BUSINESS QUESTIONS TO SQL
  Business question: "What were our top 10 products by revenue last quarter?"
  SQL thinking:
  - Which tables? orders, order_items, products
  - What columns? product_name, SUM(revenue)
  - What filters? WHERE order_date BETWEEN quarter_start AND quarter_end
  - What grouping? GROUP BY product_name
  - What ordering? ORDER BY revenue DESC LIMIT 10

STEP 3: WRITE CLEAN, READABLE SQL
  Style guidelines:
  - Use UPPERCASE for SQL keywords (SELECT, FROM, WHERE, JOIN)
  - Use lowercase for table and column names
  - One clause per line for readability
  - Indent subqueries and CASE statements
  - Alias tables with meaningful short names (o for orders, p for products)
  - Comment complex logic with -- inline comments
  - Use CTEs (WITH clauses) instead of nested subqueries for clarity

STEP 4: ADVANCED TECHNIQUES
  Window functions (for ranking, running totals, comparisons):
  - ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...) for ranking within groups
  - SUM() OVER (ORDER BY date) for running totals
  - LAG() / LEAD() for comparing to previous/next row
  - PERCENT_RANK() for percentile calculations

  CTEs for modular queries:
  WITH monthly_revenue AS (
    SELECT DATE_TRUNC('month', order_date) AS month, SUM(amount) AS revenue
    FROM orders GROUP BY 1
  ),
  growth AS (
    SELECT month, revenue,
      LAG(revenue) OVER (ORDER BY month) AS prev_month,
      (revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER (ORDER BY month) * 100 AS growth_pct
    FROM monthly_revenue
  )
  SELECT * FROM growth ORDER BY month;

STEP 5: OPTIMISE QUERY PERFORMANCE
  - Use EXPLAIN / EXPLAIN ANALYZE to understand the query execution plan
  - Index columns used in WHERE, JOIN, and ORDER BY clauses
  - Avoid SELECT * — only select columns you need
  - Filter early: Apply WHERE conditions as close to the source table as possible
  - Avoid functions on indexed columns in WHERE clauses (breaks index usage)
  - Use appropriate data types (don't store dates as strings)
  - For large datasets: Consider materialised views or pre-aggregated tables
  - Test query runtime: Set a benchmark (< 30 seconds for interactive queries)

STEP 6: VALIDATE RESULTS
  Before sharing any query results:
  - Sanity check: Do the numbers make intuitive sense?
  - Row count: Is the result set the expected size?
  - Cross-reference: Compare key totals against a known source (e.g., finance reports)
  - Edge cases: Check for NULLs, zeros, duplicates that might distort results
  - Date ranges: Verify the correct time period is captured

TOOLS & RESOURCES
- Database clients: DBeaver, DataGrip, pgAdmin, SQL Server Management Studio
- Cloud SQL: BigQuery (GCP), Redshift (AWS), Snowflake, Azure Synapse
- Query versioning: Git for SQL files, dbt for transformation models
- Performance: EXPLAIN plans, query profilers, index advisors
- Documentation: Data dictionaries, ERD diagrams, query library

QUALITY STANDARDS
- Query accuracy: Zero errors in published results
- Performance: Interactive queries < 30 seconds
- Readability: Follow team SQL style guide consistently
- Version control: All production queries stored in Git
- Documentation: Complex queries include comments explaining logic
- Validation: Cross-check results before sharing with stakeholders
