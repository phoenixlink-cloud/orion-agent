"""
Orion Agent — Prompt Builder (v6.4.0)

Extracted from intelligent_orion.py to reduce god-class size.
Contains: expansion instructions, project plan parsing, and enhanced input building.
"""

import os
import re
import logging
from typing import Dict, Any, Optional, List


logger = logging.getLogger(__name__)


def get_expansion_instruction(ext: str, filename: str, user_lower: str, content: str) -> str:
    """
    Get principle-based expansion instructions.

    Following principle-based approach: principles over metrics.
    No hardcoded line counts - trust the LLM to produce appropriate content.
    """
    principles = [
        "Write COMPLETE, PRODUCTION-READY content",
        "Use best practices and industry standards",
        "No placeholders, stubs, TODOs, or 'implement this' comments",
        "All code must be immediately runnable",
        "All references must resolve (no missing imports, no undefined functions)",
        "Match the scope and depth appropriate to the request"
    ]

    type_guidance = {
        'py': "Include proper imports, error handling, and docstrings where helpful.",
        'js': "Include proper imports and JSDoc where helpful.",
        'ts': "Include proper imports and type annotations.",
        'cs': "Include proper using statements and XML documentation where helpful.",
        'xaml': "Include complete layouts with proper bindings and event handlers.",
        'html': "Include embedded CSS for styling. Make it visually complete.",
        'md': "Write full prose, not outlines. Include tables and formatting where appropriate.",
        'css': "Include complete styles with proper selectors and responsive considerations.",
    }

    guidance = type_guidance.get(ext, "Write complete, usable content.")

    return f"{' '.join(principles)}. {guidance}"


def get_project_plan_instruction(workspace_path: str) -> Optional[str]:
    """
    Read PROJECT_PLAN.md and extract deliverables to enforce.
    """
    project_plan_path = os.path.join(workspace_path, "PROJECT_PLAN.md")

    if not os.path.exists(project_plan_path):
        return None

    try:
        with open(project_plan_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        deliverables = []
        in_deliverables = False

        for line in content.split('\n'):
            line_lower = line.lower().strip()

            if 'deliverable' in line_lower or 'output' in line_lower or 'files to create' in line_lower:
                in_deliverables = True
                continue

            if in_deliverables and line.startswith('## ') and 'deliverable' not in line_lower:
                in_deliverables = False
                continue

            if in_deliverables:
                file_matches = re.findall(r'[`(]([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)[`)]', line)
                for match in file_matches:
                    if match not in deliverables:
                        deliverables.append(match)

                if line.strip().startswith(('#', '-', '*', '1', '2', '3', '4', '5', '6', '7', '8', '9')):
                    ext_matches = re.findall(r'(\w+\.(md|py|html|css|js|ts|json|xml|yaml|yml|txt))', line)
                    for match in ext_matches:
                        if match[0] not in deliverables:
                            deliverables.append(match[0])

        if deliverables:
            return (
                "## MANDATORY DELIVERABLES FROM PROJECT_PLAN.md\n"
                f"You MUST create ALL of the following files as specified in the project plan:\n"
                f"- " + "\n- ".join(deliverables) + "\n\n"
                "DO NOT skip any deliverables. Create EVERY file listed above with COMPLETE content.\n"
                "Each file must be fully implemented, not a stub or placeholder."
            )

        return None

    except Exception:
        return None


def build_enhanced_input(
    user_input: str,
    workspace_path: str,
    base_wisdom: Dict[str, Any],
    institutional_wisdom: Dict[str, Any],
    project_context: str,
    past_decisions: List[Dict],
    retry_context: str,
    context_files: List[str] = None,
    knowledge_retrieval=None,
    reasoning_layer=None,
    working_memory=None,
    institutional_memory=None,
    project_memory=None,
) -> str:
    """
    Build enhanced input with ALL FOUR memory layers.

    This is where Orion's accumulated intelligence gets applied.

    Args:
        user_input: The user's request
        workspace_path: Path to the workspace
        base_wisdom: Layer 4 base knowledge dict
        institutional_wisdom: Layer 3 institutional wisdom dict
        project_context: Layer 2 project context string
        past_decisions: List of past decision dicts
        retry_context: Layer 1 retry context string
        context_files: User's /add files
        knowledge_retrieval: KnowledgeRetrieval instance (optional)
        reasoning_layer: ReasoningLayer instance (optional)
        working_memory: WorkingMemory instance (optional)
        institutional_memory: InstitutionalMemory instance (optional)
        project_memory: ProjectMemory instance (optional)
    """
    parts = [user_input]

    # CRITICAL: Check for PROJECT_PLAN.md and enforce deliverables
    project_plan_instruction = get_project_plan_instruction(workspace_path)
    if project_plan_instruction:
        parts.append(f"\n\n{project_plan_instruction}")

    # Repository map for codebase awareness 
    try:
        from orion.core.context.repo_map import get_repo_map_for_prompt
        repo_map = get_repo_map_for_prompt(workspace_path, context_files)
        parts.append(f"\n\n{repo_map}")
    except Exception:
        pass

    # Inject edit format instructions based on model
    try:
        from orion.core.editing.formats import get_format_instructions_for_model
        from orion.core.llm.config import get_model_config
        model_cfg = get_model_config()
        model_name = model_cfg.builder.model if model_cfg else ""
        if model_name:
            _fmt, fmt_instructions = get_format_instructions_for_model(model_name)
            parts.append(f"\n\n## EDIT FORMAT INSTRUCTIONS\n{fmt_instructions}")
    except Exception:
        pass

    # Inject code quality context for files being edited
    if context_files:
        try:
            from orion.core.context.code_quality import get_quality_context_for_prompt
            quality_ctx = get_quality_context_for_prompt(workspace_path, context_files)
            if quality_ctx:
                parts.append(f"\n\n{quality_ctx}")
        except Exception:
            pass

    # Context files content (files user explicitly added with /add)
    if context_files:
        context_content = []
        for rel_path in context_files[:5]:
            full_path = os.path.join(workspace_path, rel_path)
            try:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()[:5000]
                context_content.append(f"### {rel_path}\n```\n{content}\n```")
            except Exception:
                pass
        if context_content:
            parts.append("\n\n## FILES IN CONTEXT (user added with /add)\n" + "\n\n".join(context_content))

    # Inject available integration capabilities
    try:
        from orion.core.context.capability_injector import build_capability_prompt
        cap_prompt = build_capability_prompt()
        if cap_prompt:
            parts.append(cap_prompt)
    except Exception:
        pass

    # PRINCIPLES-BASED GUIDANCE
    parts.append("""

## QUALITY PRINCIPLES
- Write COMPLETE, PRODUCTION-READY content appropriate to the request
- All code must be immediately runnable with no missing dependencies
- All references must resolve (imports, function calls, file references)
- No placeholders, stubs, TODOs, or "implement this" comments
- Use industry best practices and standards
- Match the scope and depth to what the user actually asked for""")

    # Deep Knowledge Context (facts, procedures, templates)
    if knowledge_retrieval:
        try:
            knowledge_context = knowledge_retrieval.get_context_for_request(user_input)
            deep_knowledge_text = knowledge_retrieval.format_for_prompt(knowledge_context)
            if deep_knowledge_text:
                parts.append(f"\n\n## KNOWLEDGE CONTEXT\n{deep_knowledge_text}")
        except Exception:
            pass

    # Layer 4: Base Knowledge
    base_section = []

    if base_wisdom.get("anti_patterns"):
        anti_text = "\n".join(
            f"- **NEVER**: {a['description']} (reason: {a['reason']})"
            for a in base_wisdom["anti_patterns"][:5]
        )
        base_section.append(f"### Critical Anti-Patterns (VIOLATIONS WILL BE REJECTED)\n{anti_text}")

    if base_wisdom.get("patterns"):
        patterns_text = "\n".join(
            f"- {p['description']}"
            for p in base_wisdom["patterns"][:5]
        )
        base_section.append(f"### Best Practices\n{patterns_text}")

    if base_wisdom.get("domain_knowledge"):
        dk = base_wisdom["domain_knowledge"]
        domain_text = f"Domain: {dk['domain']}\nComponents: {', '.join(dk['components'][:5])}"
        if dk.get("regulatory"):
            domain_text += f"\nRegulatory: {dk['regulatory']}"
        base_section.append(f"### Domain Knowledge\n{domain_text}")

    if base_section:
        parts.append("\n\n## FOUNDATIONAL KNOWLEDGE (University Graduate Level)\n" + "\n\n".join(base_section))

    # Layer 3: Institutional wisdom
    institutional_section = []

    if institutional_wisdom.get("learned_patterns"):
        learned_text = "\n".join(
            f"- {p['description']} (confidence: {p['confidence']:.0%})"
            for p in institutional_wisdom["learned_patterns"][:3]
        )
        institutional_section.append(f"### Learned Patterns\n{learned_text}")

    if institutional_wisdom.get("learned_anti_patterns"):
        learned_anti = "\n".join(
            f"- AVOID: {a['description']} (severity: {a['severity']:.0%})"
            for a in institutional_wisdom["learned_anti_patterns"][:3]
        )
        institutional_section.append(f"### Learned Anti-Patterns\n{learned_anti}")

    if institutional_wisdom.get("user_preferences"):
        prefs = institutional_wisdom["user_preferences"]
        if prefs:
            prefs_text = "\n".join(f"- {k}: {v}" for k, v in list(prefs.items())[:3])
            institutional_section.append(f"### User Preferences\n{prefs_text}")

    if institutional_section:
        parts.append("\n\n## LEARNED EXPERIENCE\n" + "\n\n".join(institutional_section))

    # Reasoning Layer - Apply confirmed user feedback with context
    if reasoning_layer and working_memory:
        try:
            reasoning_context = reasoning_layer.reason(
                user_request=user_input,
                domain=working_memory.current_domain,
                files_involved=context_files,
                institutional_memory=institutional_memory,
                project_memory=project_memory
            )

            if reasoning_context.has_enhancements():
                reasoning_text = reasoning_layer.format_for_prompt(reasoning_context)
                if reasoning_text:
                    parts.append(reasoning_text)

                logger.debug(
                    "Reasoning layer enhanced prompt: "
                    f"preferences={len(reasoning_context.applicable_preferences)}, "
                    f"patterns={len(reasoning_context.applicable_patterns)}, "
                    f"instructions={len(reasoning_context.enhanced_instructions)}"
                )
        except Exception as e:
            logger.warning(f"Reasoning layer failed gracefully: {e}")

    # Layer 2: Project context
    if past_decisions:
        decisions_text = "\n".join(
            f"- {d['action'][:50]}: {'✓' if d['quality'] >= 0.8 else '○' if d['quality'] >= 0.5 else '✗'}"
            for d in past_decisions[-5:]
        )
        parts.append(f"\n\n## PROJECT CONTEXT\n### Recent Decisions\n{decisions_text}")

    # Layer 1: Working memory (retry context)
    if retry_context:
        parts.append(f"\n\n## QUALITY FEEDBACK FROM PREVIOUS ATTEMPT\n{retry_context}\n\n**Fix these issues in your response.**")

    return "\n".join(parts)
