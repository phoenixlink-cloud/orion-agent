---
name: risk-issue-management-raid
description: "Systematically identifying, assessing, mitigating, and monitoring project risks"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - project-management
  - delivery
  - planning
  - project-manager
---

SKILL: RISK & ISSUE MANAGEMENT (RAID LOG)

SKILL ID:       PM-SK-002
ROLE:           Project Manager
CATEGORY:       Risk Management
DIFFICULTY:     Intermediate to Advanced
ESTIMATED TIME: 2-4 hours per week ongoing

DESCRIPTION
Systematically identifying, assessing, mitigating, and monitoring project risks
and issues throughout the project lifecycle using the RAID framework (Risks,
Assumptions, Issues, Dependencies). This skill prevents surprises, enables
proactive decision-making, and ensures the project team is prepared for
uncertainty.

STEP-BY-STEP PROCEDURE

STEP 1: IDENTIFY RISKS (Brainstorming and analysis)
  Sources of risk identification:
  - Project team brainstorming sessions
  - Historical data from similar past projects
  - Stakeholder interviews and concerns
  - Technical complexity assessment
  - External factors: Market, regulatory, vendor, economic

  For each risk, capture:
  - Risk ID (unique reference number)
  - Description: "There is a risk that [EVENT] because [CAUSE] which would
    result in [IMPACT]"
  - Category: Technical, commercial, resource, schedule, external, compliance
  - Owner: Person responsible for monitoring and mitigating

STEP 2: ASSESS RISKS (Probability x Impact)
  Probability scale:
  1 = Very Low (< 10%)
  2 = Low (10-30%)
  3 = Medium (30-60%)
  4 = High (60-80%)
  5 = Very High (> 80%)

  Impact scale:
  1 = Negligible (< 5% budget/schedule impact)
  2 = Minor (5-10% impact, workaround available)
  3 = Moderate (10-20% impact, significant effort to resolve)
  4 = Major (20-40% impact, project objectives threatened)
  5 = Critical (> 40% impact, project viability at risk)

  Risk Score = Probability x Impact
  RED (15-25): Immediate action required, escalate to sponsor
  AMBER (8-14): Active mitigation plan, monitor weekly
  GREEN (1-7): Monitor, review monthly

STEP 3: DEVELOP MITIGATION STRATEGIES
  For each RED and AMBER risk, define one or more strategies:
  - AVOID: Eliminate the risk by changing the approach
  - MITIGATE: Reduce probability or impact through preventive actions
  - TRANSFER: Shift the risk to a third party (insurance, vendor contract)
  - ACCEPT: Acknowledge the risk and prepare a contingency plan
  - ESCALATE: Push to a higher authority if beyond project control

  Each mitigation action needs:
  - Description of the action
  - Owner responsible for implementation
  - Target date for completion
  - Cost (if any) and impact on project plan

STEP 4: MANAGE ISSUES
  An issue is a risk that has materialised — it is happening NOW.
  - Log immediately with: Description, impact, severity, owner
  - Triage: Can it be resolved at project level or must it be escalated?
  - Assign an owner and target resolution date
  - Track resolution actions and verify closure
  - Assess knock-on effects on other project areas

STEP 5: TRACK ASSUMPTIONS AND DEPENDENCIES
  ASSUMPTIONS: Things we believe to be true but haven't verified
  - Document all planning assumptions explicitly
  - Assign an owner to validate each assumption
  - If an assumption proves false, reassess affected plans

  DEPENDENCIES: External factors the project relies on
  - Other projects delivering on time
  - Vendor deliveries and third-party services
  - Regulatory approvals or decisions
  - Infrastructure or system availability
  - Track status of each dependency; escalate if at risk

STEP 6: REVIEW AND REPORT
  Weekly:
  - Review the RAID log in the team meeting
  - Update risk scores based on latest information
  - Close resolved issues and retired risks
  - Add new risks identified during the week

  Monthly (to steering committee):
  - Top 5 risks with current scores and mitigation status
  - Open issues requiring sponsor/steerco decision
  - Assumptions that need validation
  - Critical dependencies and their status

RAID LOG TEMPLATE

ID  | TYPE | DESCRIPTION        | OWNER  | PROB | IMPACT | SCORE | STATUS | ACTION
R01 | Risk | [Event/cause/impact]| [Name] | 1-5  | 1-5    | PxI   | Open   | [Mitigation]
A01 | Asmp | [What we assume]   | [Name] | -    | -      | -     | Valid? | [Validation]
I01 | Issue| [What happened]    | [Name] | -    | 1-5    | -     | Open   | [Resolution]
D01 | Dep  | [External need]    | [Name] | -    | 1-5    | -     | On trk | [Tracking]

TOOLS & RESOURCES
- RAID log spreadsheet (Excel / Google Sheets)
- JIRA or Azure DevOps (for integrated issue tracking)
- Risk register template with heatmap
- Monte Carlo simulation tool (for quantitative risk analysis)
- Lessons learned database from past projects

QUALITY STANDARDS
- RAID log: Updated weekly, reviewed in team meetings
- Risk assessment: All risks scored within 48 hours of identification
- Mitigation plans: In place for all RED and AMBER risks
- Issue resolution: Within agreed target dates (90% on-time)
- Steerco reporting: Top risks reported monthly
- Zero surprises: No critical risk materialises without prior escalation
