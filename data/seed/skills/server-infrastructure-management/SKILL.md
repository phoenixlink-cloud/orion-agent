---
name: server-infrastructure-management
description: "Installing, configuring, monitoring, and maintaining physical and virtual"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - it
  - infrastructure
  - security
  - it-systems-administrator
---

SKILL: SERVER & INFRASTRUCTURE MANAGEMENT

SKILL ID:       IT-SK-001
ROLE:           IT Systems Administrator
CATEGORY:       Infrastructure
DIFFICULTY:     Advanced
ESTIMATED TIME: Ongoing (10-15 hours per week)

DESCRIPTION
Installing, configuring, monitoring, and maintaining physical and virtual
server infrastructure to ensure maximum uptime, performance, and security.
This covers Windows Server, Linux, virtualisation platforms, capacity planning,
patching, and documentation of the entire server estate.

STEP-BY-STEP PROCEDURE

STEP 1: SERVER PROVISIONING
  For new server deployments:
  - Define requirements: Purpose, OS, CPU, RAM, storage, network, security
  - Choose platform: Physical, VM (VMware/Hyper-V), or cloud (AWS/Azure/GCP)
  - Install and configure the OS —
    * Windows Server 2022 — join to AD domain, configure roles/features
    * Linux: Ubuntu/RHEL, configure SSH, create service accounts
  - Harden the OS: Disable unnecessary services, configure firewall rules,
    apply CIS benchmarks or company security baseline
  - Install monitoring agent (Nagios, Zabbix, Datadog)
  - Configure backup schedule (Veeam, AWS Backup)
  - Document in the CMDB: Hostname, IP, OS, purpose, owner, config details
  - Test: Verify connectivity, services, monitoring, and backup

STEP 2: MONITORING & ALERTING
  Monitor continuously:
  - CPU utilisation: Alert at > 80% sustained for 15 minutes
  - Memory usage: Alert at > 85%
  - Disk space: Alert at > 80% (critical at > 90%)
  - Network throughput: Alert on unusual spikes or drops
  - Service status: Alert if critical services stop
  - Application health: HTTP checks, port checks, process checks
  - Event logs: Error and warning log monitoring (SIEM integration)

  Response to alerts:
  - Acknowledge within 15 minutes during business hours
  - Investigate root cause using logs, performance counters, and diagnostics
  - Resolve or escalate based on severity
  - Document incident and resolution in the ticketing system

STEP 3: PATCH MANAGEMENT
  Monthly patch cycle:
  Week 1: Patch Tuesday — review released patches, assess relevance
  Week 2: Test patches in dev/staging environment
  Week 3: Deploy to production (during maintenance window)
  Week 4: Verify successful deployment, remediate failures

  Critical/emergency patches (zero-day vulnerabilities):
  - Assess risk immediately (is this actively exploited?)
  - Test in staging within 24 hours
  - Deploy to production within 48-72 hours
  - Document emergency change

  Patch compliance target: >= 95% within 30 days of release

STEP 4: CAPACITY PLANNING
  Quarterly review:
  - Analyse resource utilisation trends (CPU, memory, storage, network)
  - Project growth based on business plans (new hires, projects, products)
  - Identify servers approaching capacity thresholds
  - Plan upgrades, migrations, or scaling 3-6 months ahead
  - Budget for hardware/cloud resource expansion
  - Present capacity report to IT Manager with recommendations

STEP 5: DOCUMENTATION
  Maintain up-to-date documentation for:
  - Server inventory (CMDB): All servers with specs, purpose, owner
  - Network diagrams: Physical and logical topology
  - Configuration standards: OS hardening baselines, naming conventions
  - Runbooks: Step-by-step procedures for common tasks and incidents
  - Change log: All changes with date, description, and approver
  - DR documentation: Recovery procedures for each critical system

TOOLS & RESOURCES
- VMware vSphere / Hyper-V / Proxmox for virtualisation
- AWS EC2 / Azure VMs / GCP Compute for cloud
- Monitoring: Nagios, Zabbix, Datadog, Prometheus + Grafana, PRTG
- Patch management: WSUS, SCCM, Ansible, cloud-native patch managers
- Configuration management: Ansible, Puppet, Chef, Terraform
- CMDB / documentation: IT Glue, Confluence, ServiceNow CMDB
- Remote management: SSH, RDP, iLO/iDRAC (for physical servers)

QUALITY STANDARDS
- System uptime: >= 99.9% for production systems
- Patch compliance: >= 95% within 30 days
- Monitoring coverage: 100% of production servers monitored
- Alert response: < 15 minutes during business hours
- Documentation: All servers documented in CMDB, updated within 24h of changes
- Backup verification: Monthly restoration test for all critical servers
