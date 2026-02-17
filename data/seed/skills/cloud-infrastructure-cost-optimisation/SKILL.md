---
name: cloud-infrastructure-cost-optimisation
description: "Managing cloud infrastructure across AWS, Azure, or GCP including provisioning,"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - it
  - infrastructure
  - security
  - it-systems-administrator
---

SKILL: CLOUD INFRASTRUCTURE & COST OPTIMISATION

SKILL ID:       IT-SK-004
ROLE:           IT Systems Administrator
CATEGORY:       Cloud Management
DIFFICULTY:     Advanced
ESTIMATED TIME: 6-8 hours per week (ongoing)

DESCRIPTION
Managing cloud infrastructure across AWS, Azure, or GCP including provisioning,
scaling, security, monitoring, and cost optimisation. This skill covers
infrastructure-as-code, right-sizing resources, reserved capacity planning,
and ensuring cloud spending delivers maximum value.

STEP-BY-STEP PROCEDURE

STEP 1: PROVISION CLOUD RESOURCES
  - Define requirements: Compute, storage, networking, region, compliance
  - Use Infrastructure as Code (IaC) for reproducibility:
    * Terraform: Multi-cloud, declarative, state management
    * CloudFormation (AWS) / ARM Templates (Azure) / Deployment Manager (GCP)
    * Ansible for configuration management post-provisioning
  - Follow naming conventions: {env}-{app}-{resource}-{region}-{number}
  - Tag all resources: Environment, Owner, CostCentre, Project, CreatedDate
  - Configure security: Security groups, IAM roles, encryption, network ACLs
  - Enable monitoring and logging from day one

STEP 2: MONITOR CLOUD HEALTH
  - Set up dashboards for: CPU, memory, disk, network, application metrics
  - Configure auto-scaling policies:
    * Scale out: When CPU > 70% for 5 minutes
    * Scale in: When CPU < 30% for 15 minutes
    * Minimum and maximum instance counts
  - Monitor for: Unhealthy instances, failed deployments, security alerts
  - Set up cost alerts: Notify when spending exceeds threshold

STEP 3: COST OPTIMISATION (Monthly review)
  Analyse cloud spend:
  - Review cost by service, account, tag, and region
  - Identify the top 10 cost drivers
  - Look for waste:
    * Unused resources: Unattached volumes, idle load balancers, stopped instances
    * Over-provisioned: Instances with < 20% CPU average
    * Untagged resources: Can't attribute cost = can't optimise
    * Old snapshots: Backup snapshots beyond retention policy

  Right-sizing:
  - Analyse 2-4 weeks of utilisation data
  - Downsize instances that are consistently under-utilised
  - Use burstable instances (T-series) for variable workloads
  - Consider serverless (Lambda, Azure Functions) for event-driven workloads

  Savings plans:
  - Reserved Instances / Savings Plans for steady-state workloads (30-60% savings)
  - Spot Instances for fault-tolerant batch processing (up to 90% savings)
  - Negotiate Enterprise Discount Programme for large commitments

  Target: Reduce cloud waste by 20-30% through optimisation

STEP 4: SECURITY IN THE CLOUD
  - Implement least-privilege IAM policies
  - Enable CloudTrail/Activity Log for audit trails
  - Configure security groups with minimal open ports
  - Enable encryption at rest (KMS) and in transit (TLS)
  - Use private subnets for databases and internal services
  - Enable GuardDuty/Security Center for threat detection
  - Regular access review: Remove unused IAM users and roles

STEP 5: REPORTING
  Monthly cloud report:
  - Total spend vs. budget (with trend)
  - Cost breakdown by service, team, and environment
  - Optimisation actions taken and savings achieved
  - Resource utilisation summary
  - Security compliance status
  - Recommendations for next month

TOOLS & RESOURCES
- IaC: Terraform, CloudFormation, ARM Templates, Pulumi
- Configuration: Ansible, Chef, Puppet
- Monitoring: CloudWatch (AWS), Azure Monitor, GCP Operations Suite
- Cost: AWS Cost Explorer, Azure Cost Management, GCP Billing
- Third-party cost tools: CloudHealth, Spot.io, Infracost
- Security: AWS Security Hub, Azure Security Center, GCP Security Command Center
- Documentation: Architecture diagrams in draw.io, Lucidchart

QUALITY STANDARDS
- All infrastructure deployed via IaC (no manual console changes in production)
- 100% of resources tagged per tagging policy
- Cloud cost within budget (< 5% variance)
- Cost optimisation: 20-30% reduction through right-sizing and reservations
- Security: Zero public-facing resources without approval
- Uptime: >= 99.9% for production workloads
- Monthly cost report: Delivered by working day 5
