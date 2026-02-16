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
"""
Orion Agent -- Prompt Builder (v7.4.0)

Extracted from intelligent_orion.py to reduce god-class size.
Contains: expansion instructions, project plan parsing, and enhanced input building.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)


def get_expansion_instruction(ext: str, filename: str, user_lower: str, content: str) -> str:
    """
    Get principle-based expansion instructions.

    Principles over metrics.
    No hardcoded line counts - trust the LLM to produce appropriate content.
    """
    principles = [
        "Write COMPLETE, PRODUCTION-READY content",
        "Use best practices and industry standards",
        "No placeholders, stubs, TODOs, or 'implement this' comments",
        "All code must be immediately runnable",
        "All references must resolve (no missing imports, no undefined functions)",
        "Match the scope and depth appropriate to the request",
    ]

    type_guidance = {
        "py": "Include proper imports, error handling, and docstrings where helpful.",
        "js": "Include proper imports and JSDoc where helpful.",
        "ts": "Include proper imports and type annotations.",
        "cs": "Include proper using statements and XML documentation where helpful.",
        "xaml": "Include complete layouts with proper bindings and event handlers.",
        "html": "Include embedded CSS for styling. Make it visually complete.",
        "md": "Write full prose, not outlines. Include tables and formatting where appropriate.",
        "css": "Include complete styles with proper selectors and responsive considerations.",
    }

    guidance = type_guidance.get(ext, "Write complete, usable content.")

    return f"{' '.join(principles)}. {guidance}"


def get_project_plan_instruction(workspace_path: str) -> str | None:
    """
    Read PROJECT_PLAN.md and extract deliverables to enforce.
    """
    project_plan_path = os.path.join(workspace_path, "PROJECT_PLAN.md")

    if not os.path.exists(project_plan_path):
        return None

    try:
        with open(project_plan_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        deliverables = []
        in_deliverables = False

        for line in content.split("\n"):
            line_lower = line.lower().strip()

            if (
                "deliverable" in line_lower
                or "output" in line_lower
                or "files to create" in line_lower
            ):
                in_deliverables = True
                continue

            if in_deliverables and line.startswith("## ") and "deliverable" not in line_lower:
                in_deliverables = False
                continue

            if in_deliverables:
                file_matches = re.findall(r"[`(]([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)[`)]", line)
                for match in file_matches:
                    if match not in deliverables:
                        deliverables.append(match)

                if line.strip().startswith(
                    ("#", "-", "*", "1", "2", "3", "4", "5", "6", "7", "8", "9")
                ):
                    ext_matches = re.findall(
                        r"(\w+\.(md|py|html|css|js|ts|json|xml|yaml|yml|txt))", line
                    )
                    for match in ext_matches:
                        if match[0] not in deliverables:
                            deliverables.append(match[0])

        if deliverables:
            return (
                "## MANDATORY DELIVERABLES FROM PROJECT_PLAN.md\n"
                "You MUST create ALL of the following files as specified in the project plan:\n"
                "- " + "\n- ".join(deliverables) + "\n\n"
                "DO NOT skip any deliverables. Create EVERY file listed above with COMPLETE content.\n"
                "Each file must be fully implemented, not a stub or placeholder."
            )

        return None

    except Exception as e:
        logger.debug("Failed to parse PROJECT_PLAN.md: %s", e)
        return None


