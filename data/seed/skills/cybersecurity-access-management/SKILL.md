---
name: cybersecurity-access-management
description: "Implementing and managing the organisation's IT security posture including"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - it
  - infrastructure
  - security
  - it-systems-administrator
---

SKILL: CYBERSECURITY & ACCESS MANAGEMENT

SKILL ID:       IT-SK-002
ROLE:           IT Systems Administrator
CATEGORY:       Security
DIFFICULTY:     Advanced
ESTIMATED TIME: 8-12 hours per week (ongoing)

DESCRIPTION
Implementing and managing the organisation's IT security posture including
identity and access management, endpoint protection, vulnerability management,
security monitoring, incident response, and compliance with data protection
regulations. This is a critical skill that protects the organisation from
cyber threats, data breaches, and regulatory penalties.

STEP-BY-STEP PROCEDURE

STEP 1: IDENTITY & ACCESS MANAGEMENT (IAM)
  Active Directory / Azure AD administration:
  - Create user accounts using naming convention (firstname.lastname)
  - Assign to security groups based on role and department
  - Implement least-privilege principle (minimum access needed for the job)
  - Configure Group Policy Objects (GPOs) for security settings
  - Enforce password policy: Minimum 12 chars, complexity, 90-day expiry
  - Implement MFA for all users (mandatory for admin and remote access)
  - Review access quarterly: Remove unnecessary permissions, disable stale accounts
  - Automate joiner/mover/leaver processes with HR integration

  SSO and application access:
  - Configure SAML/OIDC SSO for all supported applications
  - Manage application-specific roles and permissions
  - Maintain an access matrix: Who has access to what, and why

STEP 2: ENDPOINT PROTECTION
  Deploy and manage:
  - Antivirus / EDR (CrowdStrike, Sophos, Microsoft Defender for Endpoint)
  - Ensure all endpoints have agents installed and reporting
  - Configure policies: Real-time protection, scheduled scans, exclusions
  - Monitor for threats: Malware detections, suspicious behaviour, C2 connections
  - Respond to alerts: Isolate, investigate, remediate, restore

  Device hardening:
  - Enable disk encryption (BitLocker for Windows, FileVault for macOS)
  - Disable USB storage on sensitive endpoints (via GPO)
  - Enable screen lock timeout (5 minutes)
  - Configure automatic OS and application updates
  - Deploy MDM for mobile devices (Intune, Jamf)

STEP 3: VULNERABILITY MANAGEMENT
  Monthly vulnerability cycle:
  - Scan all systems using vulnerability scanner (Nessus, Qualys, OpenVAS)
  - Prioritise findings by CVSS score:
    CRITICAL (9.0-10.0): Patch within 72 hours
    HIGH (7.0-8.9): Patch within 7 days
    MEDIUM (4.0-6.9): Patch within 30 days
    LOW (0.1-3.9): Patch at next maintenance window
  - Remediate vulnerabilities (patching, configuration changes, compensating controls)
  - Rescan to verify remediation
  - Report: Total vulnerabilities, remediation rate, ageing analysis

STEP 4: SECURITY MONITORING & INCIDENT RESPONSE
  Continuous monitoring:
  - Firewall logs: Blocked connections, unusual traffic patterns
  - Authentication logs: Failed logins, brute-force attempts, impossible travel
  - Email security: Phishing attempts, malicious attachments, spoofing
  - Endpoint alerts: Malware detections, suspicious processes
  - Data loss prevention: Sensitive data leaving the network

  Incident response procedure:
  1. DETECT: Alert received from monitoring or user report
  2. TRIAGE: Assess severity (critical/high/medium/low)
  3. CONTAIN: Isolate affected systems, block malicious IPs/accounts
  4. INVESTIGATE: Determine scope, root cause, and impact
  5. ERADICATE: Remove the threat (malware, compromised accounts, backdoors)
  6. RECOVER: Restore systems from clean backups, re-enable services
  7. LESSONS LEARNED: Post-incident review, update procedures, report

STEP 5: SECURITY AWARENESS
  - Conduct quarterly phishing simulations (KnowBe4, Proofpoint)
  - Track click rates and report to management
  - Provide targeted training for repeat offenders
  - Distribute monthly security tips and reminders
  - Maintain security policies and ensure annual acknowledgement

TOOLS & RESOURCES
- IAM: Active Directory, Azure AD, Okta, JumpCloud
- MFA: Microsoft Authenticator, Duo, YubiKey
- Endpoint: CrowdStrike, Sophos, Microsoft Defender, SentinelOne
- Vulnerability: Nessus, Qualys, OpenVAS, Rapid7
- SIEM: Splunk, Microsoft Sentinel, Elastic SIEM, LogRhythm
- Firewall: Palo Alto, Fortinet, pfSense, Sophos XG
- Email security: Proofpoint, Mimecast, Microsoft Defender for Office 365
- Phishing simulation: KnowBe4, Proofpoint Security Awareness

QUALITY STANDARDS
- MFA adoption: 100% of users
- Patch compliance: >= 95% within SLA timeframes
- Vulnerability remediation: Critical within 72h, High within 7 days
- Phishing simulation click rate: < 5%
- Security incidents: Zero data breaches
- Access reviews: Completed quarterly, 100% coverage
- Incident response: Contained within 4 hours of detection
