# Orion Agent
# Copyright (C) 2025 Phoenix Link (Pty) Ltd. All Rights Reserved.
#
# This file is part of Orion Agent.
#
# Orion Agent is dual-licensed:
#
# 1. Open Source: GNU Affero General Public License v3.0 (AGPL-3.0)
#    You may use, modify, and distribute this file under AGPL-3.0.
#    See LICENSE for the full text.
#
# 2. Commercial: Available from Phoenix Link (Pty) Ltd
#    For proprietary use, SaaS deployment, or enterprise licensing.
#    See LICENSE-ENTERPRISE.md or contact info@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""Egress proxy management API routes.

Provides endpoints for:
  - Viewing proxy status and audit stats
  - Managing the domain whitelist
  - Viewing recent audit log entries
  - Starting/stopping the proxy (when running in-process)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from orion.security.egress.audit import AuditLogger
from orion.security.egress.config import (
    DomainRule,
    load_config,
    save_config,
)

logger = logging.getLogger("orion.api.routes.egress")

router = APIRouter(prefix="/api/egress", tags=["egress"])

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class DomainRuleRequest(BaseModel):
    domain: str
    allow_write: bool = False
    protocols: list[str] = ["https"]
    rate_limit_rpm: int = 60
    description: str = ""


class WhitelistResponse(BaseModel):
    hardcoded_domains: list[dict]
    user_domains: list[dict]


class ProxyStatusResponse(BaseModel):
    enforce: bool
    content_inspection: bool
    dns_filtering: bool
    proxy_port: int
    global_rate_limit_rpm: int
    hardcoded_domain_count: int
    user_domain_count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_egress_status() -> dict:
    """Get the current egress proxy configuration and status."""
    config = load_config()
    all_domains = config.get_all_allowed_domains()
    user_count = len(config.whitelist)
    hardcoded_count = len(all_domains) - user_count

    return {
        "enforce": config.enforce,
        "content_inspection": config.content_inspection,
        "dns_filtering": config.dns_filtering,
        "proxy_port": config.proxy_port,
        "global_rate_limit_rpm": config.global_rate_limit_rpm,
        "hardcoded_domain_count": hardcoded_count,
        "user_domain_count": user_count,
    }


@router.get("/whitelist")
async def get_whitelist() -> dict:
    """Get the full domain whitelist (hardcoded + user)."""
    config = load_config()
    all_domains = config.get_all_allowed_domains()

    hardcoded = [
        {
            "domain": r.domain,
            "allow_write": r.allow_write,
            "protocols": r.protocols,
            "rate_limit_rpm": r.rate_limit_rpm,
            "added_by": r.added_by,
            "description": r.description,
        }
        for r in all_domains
        if r.added_by == "system"
    ]
    user = [
        {
            "domain": r.domain,
            "allow_write": r.allow_write,
            "protocols": r.protocols,
            "rate_limit_rpm": r.rate_limit_rpm,
            "added_by": r.added_by,
            "description": r.description,
        }
        for r in all_domains
        if r.added_by == "user"
    ]

    return {"hardcoded_domains": hardcoded, "user_domains": user}


@router.post("/whitelist")
async def add_domain(request: DomainRuleRequest) -> dict:
    """Add a domain to the user whitelist."""
    if not request.domain.strip():
        raise HTTPException(status_code=400, detail="Domain cannot be empty")

    config = load_config()

    # Check if domain already exists in user whitelist
    for existing in config.whitelist:
        if existing.domain.lower() == request.domain.lower().strip():
            raise HTTPException(
                status_code=409,
                detail=f"Domain '{request.domain}' already in whitelist",
            )

    # Add new rule
    new_rule = DomainRule(
        domain=request.domain.strip(),
        allow_write=request.allow_write,
        protocols=request.protocols,
        rate_limit_rpm=request.rate_limit_rpm,
        added_by="user",
        description=request.description,
    )
    config.whitelist.append(new_rule)
    save_config(config)

    logger.info("Added domain to egress whitelist: %s", request.domain)
    return {"status": "added", "domain": request.domain}


@router.delete("/whitelist/{domain}")
async def remove_domain(domain: str) -> dict:
    """Remove a domain from the user whitelist."""
    config = load_config()

    # Find and remove
    original_len = len(config.whitelist)
    config.whitelist = [r for r in config.whitelist if r.domain.lower() != domain.lower()]

    if len(config.whitelist) == original_len:
        raise HTTPException(
            status_code=404,
            detail=f"Domain '{domain}' not found in user whitelist",
        )

    save_config(config)
    logger.info("Removed domain from egress whitelist: %s", domain)
    return {"status": "removed", "domain": domain}


@router.get("/audit")
async def get_audit_log(limit: int = 50) -> dict:
    """Get recent audit log entries."""
    config = load_config()
    audit = AuditLogger(config.audit_log_path)

    entries = audit.read_recent(min(limit, 200))
    stats = audit.get_stats()
    audit.close()

    return {
        "stats": stats,
        "entries": [
            {
                "timestamp": e.timestamp,
                "event_type": e.event_type,
                "method": e.method,
                "url": e.url,
                "hostname": e.hostname,
                "status_code": e.status_code,
                "blocked_reason": e.blocked_reason,
                "rule_matched": e.rule_matched,
                "duration_ms": e.duration_ms,
            }
            for e in entries
        ],
    }
