---
name: data-cleaning-quality-assurance
description: "Systematically identifying, diagnosing, and resolving data quality issues to"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - data
  - analytics
  - business-intelligence
  - data-analyst
---

SKILL: DATA CLEANING & QUALITY ASSURANCE

SKILL ID:       DA-SK-005
ROLE:           Data Analyst
CATEGORY:       Data Quality
DIFFICULTY:     Intermediate to Advanced
ESTIMATED TIME: 2-8 hours per dataset (depending on complexity)

DESCRIPTION
Systematically identifying, diagnosing, and resolving data quality issues to
ensure analyses are built on trustworthy foundations. This covers data profiling,
validation rules, handling missing data, deduplication, standardisation, and
establishing ongoing data quality monitoring.

STEP-BY-STEP PROCEDURE

STEP 1: DATA PROFILING (First look at any new dataset)
  For every column, assess:
  - Data type: Is it correct? (Dates stored as strings? Numbers as text?)
  - Completeness: What percentage of values are missing/null?
  - Uniqueness: Are there unexpected duplicates?
  - Validity: Do values fall within expected ranges?
  - Consistency: Are formats consistent? (Date formats, phone numbers, addresses)
  - Distribution: Are there unusual patterns, outliers, or skewed distributions?

  Profiling tools:
  - Python: pandas-profiling (ydata-profiling), df.describe(), df.info()
  - SQL: COUNT, COUNT(DISTINCT), MIN, MAX, AVG, NULL counts per column
  - Excel: Pivot tables, conditional formatting for anomalies

STEP 2: HANDLE MISSING DATA
  Diagnosis: Why is data missing?
  - MCAR (Missing Completely at Random): Safe to drop or impute
  - MAR (Missing at Random): Imputation based on related variables
  - MNAR (Missing Not at Random): Requires domain knowledge to handle

  Strategies:
  - DROP rows: If < 5% missing and MCAR (won't bias results)
  - DROP columns: If > 50% missing (column is unreliable)
  - IMPUTE with mean/median: For numerical, when MCAR
  - IMPUTE with mode: For categorical
  - IMPUTE with forward/backward fill: For time series
  - FLAG: Create a binary indicator column (is_missing) to track impact
  - LEAVE AS NULL: When missingness itself is informative

STEP 3: DEDUPLICATION
  - Define what constitutes a duplicate (exact match vs. fuzzy match)
  - Exact: df.drop_duplicates(subset=['key_columns'])
  - Fuzzy: Use fuzzywuzzy or recordlinkage for approximate string matching
  - Keep the most complete or most recent record when removing duplicates
  - Log the number of duplicates removed and the criteria used

STEP 4: STANDARDISATION & NORMALISATION
  - Date formats: Convert all to ISO 8601 (YYYY-MM-DD) or consistent format
  - Text: Trim whitespace, standardise case, remove special characters
  - Categories: Map variations to canonical values
    ("USA", "US", "United States", "U.S.A." → "United States")
  - Units: Convert to consistent units (all currency in ZAR, all weights in kg)
  - Encoding: Fix character encoding issues (UTF-8 as standard)

STEP 5: VALIDATION RULES
  Define and apply validation rules:
  - Range checks: Age between 0 and 120; price > 0
  - Format checks: Email matches regex; phone number has correct digits
  - Referential integrity: Every order_id has a matching customer_id
  - Business logic: End date >= start date; total = quantity * unit_price
  - Cross-field: If country = "ZA", currency should be "ZAR"

  Automate validation:
  - Build a validation script that runs before any analysis
  - Log all failures with: Row ID, column, expected, actual
  - Generate a data quality scorecard: % passing each rule

STEP 6: ONGOING DATA QUALITY MONITORING
  For recurring data sources:
  - Automate profiling: Run data quality checks on every data refresh
  - Alert on anomalies: Row count changes > 10%, new NULL columns, schema changes
  - Track quality metrics over time: Is data quality improving or degrading?
  - Escalate to data owners: If persistent quality issues need upstream fixes
  - Document known issues and workarounds in a data quality log

TOOLS & RESOURCES
- Python: pandas, ydata-profiling, great_expectations, pandera
- SQL: Data profiling queries, CHECK constraints, data quality views
- Excel: Conditional formatting, data validation, COUNTBLANK
- Data quality frameworks: Great Expectations, dbt tests, Soda
- Fuzzy matching: fuzzywuzzy, recordlinkage (Python)
- Documentation: Data quality log, validation rule library

QUALITY STANDARDS
- Data profiling: Completed for every new dataset before analysis begins
- Missing data: Strategy documented and applied consistently
- Duplicates: Zero unexpected duplicates in analysis datasets
- Validation: All key fields pass defined validation rules (>= 98%)
- Documentation: Data quality issues, decisions, and transformations logged
- Monitoring: Automated quality checks on all recurring data sources
- Escalation: Persistent upstream quality issues reported to data owners
