---
name: financial-modelling-scenario-analysis
description: "Building robust, auditable financial models that project business performance"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - finance
  - analysis
  - reporting
  - financial-analyst
---

SKILL: FINANCIAL MODELLING & SCENARIO ANALYSIS

SKILL ID:       FA-SK-001
ROLE:           Financial Analyst
CATEGORY:       Analysis & Modelling
DIFFICULTY:     Advanced
ESTIMATED TIME: 8-40 hours per model (depending on complexity)

DESCRIPTION
Building robust, auditable financial models that project business performance
under multiple scenarios to support strategic decision-making. This covers
three-statement models (P&L, balance sheet, cash flow), DCF valuations,
scenario and sensitivity analysis, and model documentation standards.

STEP-BY-STEP PROCEDURE

STEP 1: DEFINE THE PURPOSE AND SCOPE
  - What question does this model need to answer?
    (e.g., "Should we acquire Company X?" or "What is our 5-year growth plan?")
  - Time horizon: 3-year, 5-year, 10-year?
  - Granularity: Monthly, quarterly, or annual?
  - Output required: Valuation? Cash flow forecast? ROI? Break-even?
  - Audience: Board? Investors? Internal management?

STEP 2: GATHER DATA AND ASSUMPTIONS
  - Historical financials: 3-5 years of actuals (P&L, BS, CF)
  - Operational data: Volumes, pricing, headcount, capacity
  - Market data: Growth rates, inflation, interest rates, comparables
  - Management inputs: Strategic plans, capex pipeline, hiring plans
  - Document EVERY assumption with source and rationale

STEP 3: STRUCTURE THE MODEL
  Best-practice model architecture:
  TAB 1: COVER — Model name, version, author, date, status
  TAB 2: ASSUMPTIONS — All inputs in one place (colour-coded blue)
  TAB 3: REVENUE MODEL — Top-line build-up (volume x price x growth)
  TAB 4: COST MODEL — Fixed vs. variable, department-level detail
  TAB 5: P&L — Income statement (formulae only, no hard-coded numbers)
  TAB 6: BALANCE SHEET — Assets, liabilities, equity
  TAB 7: CASH FLOW — Operating, investing, financing activities
  TAB 8: DCF / VALUATION — If applicable (WACC, terminal value, NPV)
  TAB 9: SCENARIOS — Toggle between base, upside, downside
  TAB 10: SENSITIVITY — Data tables showing impact of key variable changes
  TAB 11: CHARTS — Visual summary of key outputs
  TAB 12: AUDIT — Error checks, balance check (BS balances?), sign-off

  Colour coding convention:
  BLUE:   Input / assumption (hard-coded, can be changed)
  BLACK:  Formula (calculated, do not overwrite)
  GREEN:  Link to another sheet
  RED:    Error check or warning

STEP 4: BUILD THE MODEL
  Build in this order:
  1. Assumptions tab first — all inputs centralised
  2. Revenue model — build from the bottom up (units x price)
  3. Cost model — split fixed and variable costs
  4. P&L — pull from revenue and cost tabs (all formulae)
  5. Balance sheet — link to P&L and assumptions
  6. Cash flow — derive from P&L and balance sheet movements
  7. Valuation — DCF, comparables, or other method
  8. Scenarios and sensitivity — wire to the assumptions tab
  9. Error checks — does the balance sheet balance? Signs correct?

  Golden rules:
  - One formula per row (no different formulas in adjacent cells)
  - No circular references
  - No hard-coded numbers in formula cells
  - All assumptions flow from the assumptions tab
  - Use named ranges for key inputs
  - Keep formulas simple and auditable (break into steps if needed)

STEP 5: SCENARIO ANALYSIS
  Build three scenarios minimum:
  BASE CASE:    Management's best estimate (most likely outcome)
  UPSIDE:       Optimistic assumptions (+10-20% on key drivers)
  DOWNSIDE:     Pessimistic assumptions (-10-30% on key drivers)

  Use a scenario toggle on the assumptions tab:
  - Dropdown: "Base" / "Upside" / "Downside"
  - All model outputs update automatically based on selection
  - Present all three scenarios side-by-side in the output summary

STEP 6: SENSITIVITY ANALYSIS
  Identify the 3-5 variables with the highest impact on the outcome:
  (e.g., revenue growth rate, gross margin, discount rate, capex)
  Build data tables showing how the key output (NPV, IRR, EBITDA) changes
  as each variable moves +/- 10%, 20%, 30%
  Visualise with tornado charts showing which variables matter most

STEP 7: DOCUMENT AND REVIEW
  - Complete the model cover sheet (purpose, author, version, date)
  - Document all assumptions with sources in the assumptions tab
  - Run error checks: Balance sheet balances? Cash flow ties to BS?
  - Peer review: Have another analyst check formulas and logic
  - Stress test: Input extreme values — does the model break?
  - Lock completed sections (protect sheets, hide formulas if distributing)
  - Save versioned copies (Model_v1.0, v1.1, v2.0)

TOOLS & RESOURCES
- Microsoft Excel (primary modelling tool)
- Google Sheets (for collaborative models)
- Financial modelling add-ins (Macabacus, F1F9)
- Bloomberg / Refinitiv for market data
- Company annual reports and filings
- Industry research reports
- Python / R (for complex statistical models or automation)

QUALITY STANDARDS
- Zero hard-coded numbers in formula cells
- Zero circular references
- Balance sheet balances in all periods (check cell = TRUE)
- Cash flow ties to balance sheet cash movement
- All assumptions documented with sources
- Peer-reviewed before distribution
- Version-controlled with change log
- Error check tab: All checks showing GREEN/PASS
