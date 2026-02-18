---
name: dashboard-design-bi-management
description: "Designing and building interactive business intelligence dashboards that enable"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - data
  - analytics
  - business-intelligence
  - data-analyst
---

SKILL: DASHBOARD DESIGN & BI TOOL MANAGEMENT

SKILL ID:       DA-SK-003
ROLE:           Data Analyst
CATEGORY:       Visualisation & Reporting
DIFFICULTY:     Intermediate to Advanced
ESTIMATED TIME: 8-20 hours per dashboard (design through deployment)

DESCRIPTION
Designing and building interactive business intelligence dashboards that enable
stakeholders to explore data, monitor KPIs, and make decisions without relying
on ad-hoc analyst requests. This covers requirements gathering, data modelling,
visual design, performance optimisation, and user adoption.

STEP-BY-STEP PROCEDURE

STEP 1: GATHER REQUIREMENTS
  Meet with stakeholders to define:
  - WHO: Who will use this dashboard? (Executive, manager, analyst, operations)
  - WHY: What decisions will it support? What questions must it answer?
  - WHAT: Which KPIs and metrics are needed?
  - HOW OFTEN: Real-time, daily, weekly, monthly refresh?
  - DRILL-DOWN: Do users need to click into details?
  - ACCESS: Who should see what? (Row-level security, department filtering)

STEP 2: DESIGN THE DATA MODEL
  - Identify source tables and the relationships between them
  - Build a star schema if possible: Fact table(s) + dimension tables
  - Create calculated measures and KPIs in the semantic layer
  - Optimise for query performance: Pre-aggregate where beneficial
  - Set up data refresh schedule (automated, tested for reliability)
  - Document the data model: Sources, transformations, business logic

STEP 3: BUILD THE DASHBOARD
  Layout principles:
  - Top-left: Most important metric (eye naturally starts here)
  - Top row: Summary KPIs with traffic lights or trend indicators
  - Middle: Main visualisation(s) with filters
  - Bottom: Detail tables or supporting charts
  - Left sidebar: Filters and navigation (if multi-page)

  Visual design rules:
  - Maximum 6-8 visuals per page (avoid clutter)
  - Consistent colour palette aligned with brand
  - Use colour meaningfully: Green=good, Red=bad, Grey=neutral
  - Chart titles = insights, not labels ("Revenue grew 12%" not "Revenue Chart")
  - Include context: Comparisons (vs. target, vs. last year, vs. forecast)
  - Mobile-responsive layout for executives on the go
  - Tooltips for additional detail on hover

STEP 4: TEST AND VALIDATE
  Before publishing:
  [ ] Data accuracy: Numbers match the source system
  [ ] Filters work correctly: All combinations produce valid results
  [ ] Performance: Pages load in < 5 seconds
  [ ] Mobile: Dashboard is usable on tablet/phone
  [ ] Security: Users only see data they're authorised to view
  [ ] Edge cases: What happens with no data, negative values, or zeros?
  [ ] Cross-browser: Works in Chrome, Edge, Safari
  [ ] Stakeholder review: Key user validates the output

STEP 5: DEPLOY AND DRIVE ADOPTION
  - Publish to the BI platform with appropriate workspace and permissions
  - Send an announcement with: Purpose, link, user guide, training offer
  - Conduct a 30-minute walkthrough for primary users
  - Embed in daily workflows: Link from email reports, Slack, intranet
  - Track adoption: Views, unique users, frequency (built into most BI tools)
  - Gather feedback after 2 weeks and iterate

STEP 6: MAINTAIN AND EVOLVE
  - Monitor data refresh: Alert on failures, fix within 4 hours
  - Update for business changes: New products, reorganisations, KPI changes
  - Performance tune: As data grows, optimise queries and aggregations
  - Retire unused dashboards (archive after 90 days of no usage)
  - Quarterly review: Is the dashboard still answering the right questions?

TOOLS & RESOURCES
- Power BI: DAX, Power Query, data modelling, service publishing
- Tableau: Calculated fields, LOD expressions, Tableau Server/Online
- Looker: LookML modelling, explores, dashboards
- Google Data Studio: Free, Google ecosystem integration
- Qlik Sense: Associative engine, set analysis
- Design: Figma/Canva for mockups before building

QUALITY STANDARDS
- Data accuracy: 100% match to source systems
- Load time: < 5 seconds per page
- Refresh reliability: 99%+ successful automated refreshes
- Adoption: >= 70% of intended users actively using within 30 days
- User satisfaction: >= 4.0/5.0 on usability survey
- Maintenance: Issues resolved within 24 hours
