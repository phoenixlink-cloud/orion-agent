---
name: backup-disaster-recovery
description: "Designing, implementing, and testing backup and disaster recovery solutions"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - it
  - infrastructure
  - security
  - it-systems-administrator
---

SKILL: BACKUP & DISASTER RECOVERY

SKILL ID:       IT-SK-003
ROLE:           IT Systems Administrator
CATEGORY:       Business Continuity
DIFFICULTY:     Advanced
ESTIMATED TIME: 4-6 hours per week (ongoing) + annual DR testing

DESCRIPTION
Designing, implementing, and testing backup and disaster recovery solutions
that protect the organisation's data and ensure business continuity in the
event of hardware failure, ransomware, natural disaster, or human error.

STEP-BY-STEP PROCEDURE

STEP 1: DESIGN THE BACKUP STRATEGY (3-2-1 Rule)
  3 copies of data (production + 2 backups)
  2 different storage media (local + cloud, or local + tape)
  1 offsite copy (cloud storage, remote data centre, or tape vaulting)

  Backup types:
  FULL: Complete copy of all data (weekly, typically weekends)
  INCREMENTAL: Only data changed since last backup (daily)
  DIFFERENTIAL: Data changed since last full backup (alternative to incremental)

  Define per platform:
  - RPO (Recovery Point Objective): Maximum acceptable data loss
    Critical systems: RPO < 1 hour (continuous replication)
    Standard systems: RPO < 24 hours (daily backup)
    Low priority: RPO < 48-72 hours
  - RTO (Recovery Time Objective): Maximum acceptable downtime
    Critical: RTO < 1 hour (hot standby or instant failover)
    Standard: RTO < 4 hours
    Low priority: RTO < 24 hours

STEP 2: IMPLEMENT BACKUPS
  - Configure backup jobs for all systems:
    * Servers (OS, applications, databases)
    * User data (file shares, OneDrive, email)
    * Cloud services (SaaS backup: M365, Google Workspace)
    * Network device configurations
    * Virtual machine snapshots
  - Schedule jobs to run during off-peak hours
  - Configure retention: Daily (30 days), Weekly (12 weeks), Monthly (12 months), Yearly (7 years)
  - Encrypt backups at rest and in transit
  - Monitor backup completion: 100% success rate target

STEP 3: TEST BACKUPS (Monthly)
  Monthly restoration tests:
  - Select a different system each month (rotate through all critical systems)
  - Restore to a test environment (never overwrite production)
  - Verify: Data integrity, application functionality, database consistency
  - Measure: Time to restore (actual RTO vs. target RTO)
  - Document: Test date, system tested, result, time taken, issues found
  - Fix any failures immediately and retest

STEP 4: DISASTER RECOVERY PLAN
  Document the DR plan covering:
  1. SCOPE: Which systems are covered and their priority order
  2. TEAM: DR team members, roles, and contact details (including personal phones)
  3. ACTIVATION: Criteria for declaring a disaster and who authorises it
  4. RECOVERY SEQUENCE: Step-by-step restoration order
     Priority 1: Active Directory, DNS, DHCP (foundation services)
     Priority 2: Email, communication systems
     Priority 3: Business-critical applications (ERP, CRM, finance)
     Priority 4: File servers, collaboration tools
     Priority 5: Non-critical systems
  5. COMMUNICATION: How to notify staff, customers, and partners
  6. ALTERNATIVE OPERATIONS: Temporary workarounds during recovery
  7. TESTING: Schedule and procedure for annual DR drills

STEP 5: ANNUAL DR DRILL
  - Schedule a full DR test annually (off-hours or weekend)
  - Simulate a realistic scenario (data centre failure, ransomware)
  - Execute the recovery plan step by step
  - Measure actual RTO and RPO vs. targets
  - Document all issues encountered
  - Update the DR plan based on lessons learned
  - Brief leadership on results and any gaps

TOOLS & RESOURCES
- Backup: Veeam, Acronis, Commvault, AWS Backup, Azure Backup
- Replication: VMware SRM, Zerto, AWS DRS
- Cloud storage: AWS S3, Azure Blob, Backblaze B2 (for offsite copies)
- SaaS backup: Spanning, Backupify, Veeam for M365
- Monitoring: Veeam ONE, backup job alerting
- DR plan template and runbook
- Contact list with personal phone numbers

QUALITY STANDARDS
- Backup success rate: 100% (investigate and fix all failures immediately)
- Monthly restoration test: Completed for a different system each month
- DR plan: Reviewed and updated annually (or after major changes)
- Annual DR drill: Completed and documented with lessons learned
- RPO/RTO met: 100% of systems within defined targets
- Backup encryption: 100% of backups encrypted at rest and in transit
- Offsite copy: 100% of critical data has an offsite backup
