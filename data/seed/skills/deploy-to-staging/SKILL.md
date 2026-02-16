---
name: deploy-to-staging
description: "Safe deployment to staging with pre-flight checks and rollback procedure"
version: "1.0.0"
author: "Orion"
tags: ["devops", "deployment", "staging"]
source: "bundled"
trust_level: "verified"
---

## Pre-deployment Checklist

1. Run all tests — ensure the test suite passes completely
2. Check for uncommitted changes — `git status` must be clean
3. Verify environment variables match the staging template
4. Check that the target branch is up to date with main

## Deployment Steps

1. **Build the project** — run the project's build command
2. **Tag the release** — create a git tag for traceability
3. **Deploy to staging** — use the project's deploy script or CI/CD
4. **Run smoke tests** — verify critical paths work on staging
5. **Check logs** — look for errors or warnings in the first 5 minutes

## Rollback Procedure

If smoke tests fail or errors appear:
1. Identify the previous known-good tag
2. Revert to the previous deployment
3. Verify the rollback restored service
4. Document what failed and why

## Post-deployment

- Notify the team in the designated channel
- Update the deployment log with version, time, and status
- Monitor error rates for the next 30 minutes
