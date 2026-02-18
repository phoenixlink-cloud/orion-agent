---
name: it-automation-scripting
description: "Automating repetitive IT tasks using scripting languages (PowerShell, Bash,"
version: "1.0.0"
author: "Phoenix Link"
tags:
  - it
  - infrastructure
  - security
  - it-systems-administrator
---

SKILL: IT AUTOMATION & SCRIPTING

SKILL ID:       IT-SK-005
ROLE:           IT Systems Administrator
CATEGORY:       Automation & Efficiency
DIFFICULTY:     Advanced
ESTIMATED TIME: 4-8 hours per week (ongoing development and maintenance)

DESCRIPTION
Automating repetitive IT tasks using scripting languages (PowerShell, Bash,
Python) and automation platforms (Ansible, Terraform) to improve efficiency,
reduce human error, and enable the IT team to focus on strategic work rather
than manual operations.

STEP-BY-STEP PROCEDURE

STEP 1: IDENTIFY AUTOMATION CANDIDATES
  Evaluate tasks based on:
  - Frequency: How often is this task performed? (Daily/weekly = high value)
  - Time: How long does it take manually? (> 30 min = worth automating)
  - Error-prone: Does manual execution lead to mistakes?
  - Standardisation: Can the task be defined with consistent steps?
  - Impact: What is the risk if done incorrectly?

  Common automation candidates:
  - User account provisioning and deprovisioning
  - Server patching and rebooting
  - Log collection and analysis
  - Disk space monitoring and cleanup
  - Certificate renewal
  - Backup verification and reporting
  - Software deployment and updates
  - Report generation (uptime, capacity, security)
  - Network device configuration backup

STEP 2: CHOOSE THE RIGHT TOOL
  PowerShell: Windows administration, Active Directory, Exchange, Azure
  Bash: Linux administration, cron jobs, file operations, system monitoring
  Python: Cross-platform, API integrations, complex logic, data processing
  Ansible: Configuration management, multi-server deployment, idempotent
  Terraform: Infrastructure provisioning, cloud resource management

STEP 3: DEVELOP THE SCRIPT
  Best practices:
  - Start with a clear specification: Input, process, output, error handling
  - Use version control (Git) for all scripts
  - Include error handling and logging in every script
  - Use parameters (not hardcoded values) for flexibility
  - Add comments explaining the WHY, not just the WHAT
  - Follow naming conventions: verb-noun for PowerShell, snake_case for Python/Bash
  - Test in a non-production environment first
  - Peer review before deploying to production

  Script structure:
  1. Header: Purpose, author, date, version, parameters
  2. Input validation: Check parameters and prerequisites
  3. Main logic: The actual automation steps
  4. Error handling: Try/catch with meaningful error messages
  5. Logging: Write to a log file with timestamps
  6. Notification: Email or Slack alert on success/failure
  7. Cleanup: Remove temp files, close connections

STEP 4: SCHEDULE AND DEPLOY
  - Schedule recurring scripts via:
    * Windows: Task Scheduler
    * Linux: cron
    * Cloud: Lambda/Functions with CloudWatch/Timer triggers
    * Automation platform: Ansible Tower, Jenkins, RunDeck
  - Monitor execution: Check logs, verify expected outcomes
  - Set up alerts for failures
  - Document the automation: Purpose, schedule, dependencies, troubleshooting

STEP 5: MAINTAIN AND IMPROVE
  - Review automation scripts quarterly
  - Update for environment changes (new servers, changed APIs, new requirements)
  - Track time saved: Manual time x frequency = automation value
  - Gather feedback from team members using the automations
  - Continuously identify new automation opportunities
  - Maintain a script library with documentation and examples

COMMON AUTOMATION EXAMPLES

USER PROVISIONING (PowerShell/Active Directory):
  - Create AD account based on HR system data
  - Add to security groups based on department/role
  - Create mailbox, assign licences
  - Generate and securely deliver initial password
  - Send welcome email with setup instructions

DAILY HEALTH CHECK (Bash/Python):
  - Check all critical services are running
  - Verify backup completion from last night
  - Check disk space on all servers
  - Review security alerts from overnight
  - Send morning health report email

PATCH COMPLIANCE REPORT (PowerShell):
  - Query all servers for installed patches
  - Compare against required patch list
  - Calculate compliance percentage
  - Generate report and email to IT Manager

CERTIFICATE MONITORING (Python):
  - Check expiry dates of all SSL/TLS certificates
  - Alert 30 days before expiry
  - Auto-renew Let's Encrypt certificates
  - Report certificate inventory

TOOLS & RESOURCES
- Languages: PowerShell, Bash, Python
- Automation platforms: Ansible, Terraform, Puppet, Chef
- Scheduling: Task Scheduler, cron, Jenkins, RunDeck
- Version control: Git (GitLab, GitHub, Bitbucket)
- IDE: VS Code with relevant extensions
- Testing: Pester (PowerShell), pytest (Python), ShellCheck (Bash)
- Documentation: README files, Confluence, internal wiki

QUALITY STANDARDS
- All scripts in version control: 100%
- Error handling: Every script has try/catch and logging
- Testing: Scripts tested in non-production before deployment
- Documentation: README for every automation with purpose and usage
- Peer review: Required before production deployment
- Time saved tracking: Measured and reported quarterly
- Failure rate: < 2% of scheduled automation runs
