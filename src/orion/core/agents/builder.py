"""
Orion Agent — Builder (v6.4.0)

Generates code solutions, file operations, plans, and answers.
Migrated from Orion_MVP/core/llm_calls.py (call_gpt_builder).

Architecture:
  - Async via httpx for non-blocking HTTP
  - Uses orion.core.llm.config for model routing
  - Uses orion.security.store for credential access
  - Supports all providers: Ollama, OpenAI, Anthropic, Google, Groq, etc.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

logger = logging.getLogger("orion.builder")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class BuilderResult:
    """Result from Builder execution."""
    outcome: str          # "ANSWER", "PLAN", "ACTION_INTENT"
    response: str         # Human-readable response
    actions: List[Dict[str, Any]] = field(default_factory=list)
    explanation: str = ""
    raw: str = ""         # Raw LLM output for debugging
    provider: str = ""
    model: str = ""


# =============================================================================
# CONSTRAINT EXTRACTION
# =============================================================================

def extract_constraints(user_input: str) -> dict:
    """Extract explicit user constraints from input text."""
    lower = user_input.lower()
    constraints = {"no_file_ops": False, "max_files": None, "required_filename": None}

    no_file_patterns = [
        "do not create any files", "don't create any files",
        "no file operations", "no files", "plan only",
        "planning only", "just plan", "only plan",
    ]
    for p in no_file_patterns:
        if p in lower:
            constraints["no_file_ops"] = True
            break

    m = re.search(r'exactly\s+(\d+|one|two|three)\s+file', lower)
    if m:
        num_map = {"one": 1, "two": 2, "three": 3}
        v = m.group(1)
        constraints["max_files"] = num_map.get(v, int(v) if v.isdigit() else None)

    m2 = re.search(r'(?:create|make)\s+(?:a\s+)?file\s+(?:named|called)\s+["\']?([\w.-]+)["\']?', lower)
    if m2:
        constraints["required_filename"] = m2.group(1)

    return constraints


# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

_GROUNDING_RULES = """## GROUNDING RULES (NON-NEGOTIABLE)
1) You may ONLY state facts that are explicitly present in the Evidence Snapshot.
2) You MUST NOT invent paths, folder names, URLs, build commands, frameworks, or features.
3) All file paths mentioned MUST come from evidence exactly (case-sensitive).
4) Prefer a minimal output that is correct over a detailed output that is wrong.
5) If workspace is empty, you may propose new file structures but mark them clearly as proposals.

## CODE QUALITY REQUIREMENTS (NON-NEGOTIABLE)
When generating code files:
1) Every file MUST be complete and functional - no stubs
2) Do NOT use placeholder comments like "// TODO: implement" or "# TODO"
3) Do NOT leave empty function/method bodies
4) Write REAL, WORKING implementations
5) If you are uncertain about implementation details, note it in the "explanation" field, NOT in the code
"""

_EXECUTION_MODE = """
## EXECUTION MODE (NON-NEGOTIABLE)
The user has APPROVED a plan for execution. You MUST respond with ACTION_INTENT containing concrete file operations.
ONLY "outcome": "ACTION_INTENT" is accepted. "PLAN" and "ANSWER" will be REJECTED.
Files must contain REAL implementation code, not stubs or TODOs.
"""


def _get_evolution_guidance() -> str:
    """Query the evolution engine for weaknesses and inject targeted guidance."""
    guidance_lines = []
    try:
        from orion.core.learning.evolution import get_evolution_engine
        evo = get_evolution_engine()
        sw = evo.analyze_strengths_weaknesses(days=60)
        weaknesses = [s for s in sw if not s.is_strength]
        if weaknesses:
            guidance_lines.append("SELF-IMPROVEMENT GUIDANCE (from learned patterns):")
            for w in weaknesses[:3]:
                if w.area == "refactor":
                    guidance_lines.append(
                        "- REFACTOR tasks: Break changes into small, testable steps. "
                        "Preserve existing tests. Show before/after for each change. "
                        "Never rewrite from scratch — prefer surgical edits."
                    )
                elif w.area == "bug_fix":
                    guidance_lines.append(
                        "- BUG FIX tasks: Identify root cause before proposing a fix. "
                        "Include the specific error message. Add a regression test. "
                        "Prefer minimal upstream fixes over downstream workarounds."
                    )
                elif w.area == "testing":
                    guidance_lines.append(
                        "- TESTING tasks: Write focused unit tests with clear assertions. "
                        "Cover edge cases. Use descriptive test names. "
                        "Mock external dependencies."
                    )
                elif w.area == "documentation":
                    guidance_lines.append(
                        "- DOCUMENTATION tasks: Be concise. Use examples over prose. "
                        "Include code snippets. Match the project's existing doc style."
                    )
                else:
                    guidance_lines.append(
                        f"- {w.area.upper()} tasks: {w.recommendation}"
                    )
    except Exception:
        pass

    # Also pull anti-patterns from memory
    try:
        from orion.core.memory.engine import get_memory_engine
        mem = get_memory_engine()
        anti_patterns = mem.recall(
            "anti-pattern avoid mistake", max_results=3,
            categories=["anti_pattern"], min_confidence=0.6,
        )
        if anti_patterns:
            if not guidance_lines:
                guidance_lines.append("LEARNED ANTI-PATTERNS (avoid these mistakes):")
            else:
                guidance_lines.append("\nLEARNED ANTI-PATTERNS (avoid these mistakes):")
            for ap in anti_patterns:
                guidance_lines.append(f"- {ap.content[:150]}")
    except Exception:
        pass

    return "\n".join(guidance_lines)


def _build_system_prompt(mode: str, constraints: dict, execution_mode: bool, is_local: bool) -> str:
    """Build the system prompt for the Builder."""
    constraint_rules = []
    if constraints.get("no_file_ops"):
        constraint_rules.append("USER CONSTRAINT: Do NOT propose any file operations. Respond with a PLAN only.")
    if constraints.get("max_files"):
        constraint_rules.append(f"USER CONSTRAINT: Create at most {constraints['max_files']} file(s).")
    if constraints.get("required_filename"):
        constraint_rules.append(f"USER CONSTRAINT: If creating a file, it must be named '{constraints['required_filename']}'.")
    constraint_section = "\n".join(constraint_rules) if constraint_rules else ""

    # Auto-inject evolution guidance into prompt
    evolution_section = _get_evolution_guidance()

    exec_section = _EXECUTION_MODE if execution_mode else ""

    # Load Orion persona
    persona_section = ""
    try:
        from orion.core.persona import get_builder_persona
        persona_section = get_builder_persona()
    except Exception:
        pass

    if is_local:
        return f"""{persona_section}

OUTPUT FORMAT (standard file listing):
To create a file, output the filename on its own line, then the code in a fenced block:

filename.py
```python
# your complete code here
```

RULES:
1. Write COMPLETE code - no stubs, no TODOs, no placeholders
2. Include ALL imports at the top of each file
3. Every function must have real implementation
4. Output the ENTIRE file content - never truncate or use "..."
5. Create ONE file at a time when asked

{evolution_section}

{constraint_section}"""
    else:
        return f"""{persona_section}

Current mode: {mode.upper()}
{"You MAY propose file operations." if mode in ("pro", "project") else "You may NOT propose file operations in SAFE mode."}
{exec_section}
{_GROUNDING_RULES}

{evolution_section}

{constraint_section}

If proposing file operations, respond with JSON:
{{
    "outcome": "ACTION_INTENT",
    "explanation": "why this is the right approach",
    "actions": [
        {{"operation": "CREATE", "path": "relative/path.ext", "content": "file content"}},
        {{"operation": "OVERWRITE", "path": "existing/file.ext", "content": "new content"}},
        {{"operation": "DELETE", "path": "file/to/delete.ext"}},
        {{"operation": "RUN", "command": "dotnet build", "cwd": "."}}
    ]
}}

If answering a question, respond with JSON:
{{
    "outcome": "ANSWER",
    "response": "your detailed answer here"
}}

If proposing a plan, respond with JSON:
{{
    "outcome": "PLAN",
    "response": "step by step plan here"
}}

Always respond with valid JSON. The "response" field MUST be a string."""


# =============================================================================
# PROVIDER CALLING
# =============================================================================

async def _call_provider(provider: str, model: str, system_prompt: str, user_prompt: str,
                         max_tokens: int = 8000, temperature: float = 0.3) -> str:
    """Call any supported LLM provider. Returns raw response text."""
    import httpx

    if provider == "ollama":
        return await _call_ollama(model, system_prompt, user_prompt, max_tokens, temperature)

    elif provider == "openai":
        import openai
        from orion.security.store import get_secure_store
        store = get_secure_store()
        api_key = store.get_key("openai")
        if not api_key:
            return json.dumps({"outcome": "ANSWER", "response": "OpenAI API key not configured."})
        client = openai.AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=temperature, max_tokens=max_tokens,
        )
        return resp.choices[0].message.content

    elif provider == "anthropic":
        import anthropic
        from orion.security.store import get_secure_store
        store = get_secure_store()
        api_key = store.get_key("anthropic")
        if not api_key:
            return json.dumps({"outcome": "ANSWER", "response": "Anthropic API key not configured."})
        client = anthropic.AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}],
        )
        return resp.content[0].text

    elif provider == "google":
        try:
            import google.generativeai as genai
        except ImportError:
            return json.dumps({"outcome": "ANSWER", "response": "google-generativeai not installed."})
        from orion.security.store import get_secure_store
        store = get_secure_store()
        api_key = store.get_key("google")
        if not api_key:
            return json.dumps({"outcome": "ANSWER", "response": "Google API key not configured."})
        genai.configure(api_key=api_key)
        gen_model = genai.GenerativeModel(model)
        resp = gen_model.generate_content(
            f"{system_prompt}\n\n{user_prompt}",
            generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens, temperature=temperature),
        )
        return resp.text

    else:
        # OpenAI-compatible providers (groq, together, mistral, openrouter, etc.)
        return await _call_openai_compatible(provider, model, system_prompt, user_prompt, max_tokens, temperature)


async def _call_ollama(model: str, system_prompt: str, user_prompt: str,
                       max_tokens: int = 4000, temperature: float = 0.7) -> str:
    """Call local Ollama model via httpx (async)."""
    import httpx
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")


_OPENAI_COMPATIBLE = {
    "groq":       {"base_url": "https://api.groq.com/openai/v1",    "key": "groq"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1",      "key": "openrouter"},
    "mistral":    {"base_url": "https://api.mistral.ai/v1",         "key": "mistral"},
    "together":   {"base_url": "https://api.together.xyz/v1",       "key": "together"},
}


async def _call_openai_compatible(provider: str, model: str, system_prompt: str,
                                  user_prompt: str, max_tokens: int, temperature: float) -> str:
    """Call OpenAI-compatible provider."""
    import openai
    from orion.security.store import get_secure_store
    cfg = _OPENAI_COMPATIBLE.get(provider, {"base_url": "", "key": provider})
    store = get_secure_store()
    api_key = store.get_key(cfg["key"])
    if not api_key:
        return json.dumps({"outcome": "ANSWER", "response": f"{provider} API key not configured."})
    client = openai.AsyncOpenAI(api_key=api_key, base_url=cfg["base_url"])
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=temperature, max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


# =============================================================================
# JSON EXTRACTION
# =============================================================================

def extract_json(text: str) -> Optional[Dict]:
    """Extract JSON from LLM response text (may contain markdown fences)."""
    if not text:
        return None
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from markdown code blocks
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try finding first { ... } block
    start = text.find('{')
    if start >= 0:
        depth = 0
        for i, c in enumerate(text[start:], start):
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def run_builder(
    user_input: str,
    evidence_context: str,
    mode: str = "safe",
    session_header: str = "",
    execution_mode: bool = False,
) -> BuilderResult:
    """
    Run the Builder agent.

    Args:
        user_input: User's request
        evidence_context: Formatted evidence from workspace
        mode: Current AEGIS mode (safe/pro/project)
        session_header: Session state header for multi-chunk
        execution_mode: If True, force ACTION_INTENT output

    Returns:
        BuilderResult with outcome, response, and actions
    """
    from orion.core.llm.config import get_model_config

    model_cfg = get_model_config()
    builder = model_cfg.get_builder()
    constraints = extract_constraints(user_input)

    system_prompt = _build_system_prompt(
        mode=mode,
        constraints=constraints,
        execution_mode=execution_mode,
        is_local=(builder.provider == "ollama"),
    )

    user_prompt = f"""## USER REQUEST
{user_input}

{session_header}## EVIDENCE
{evidence_context if evidence_context else "Workspace is empty. This is a greenfield project."}

Analyze the request and evidence, then respond with your proposal."""

    logger.info(f"Builder calling {builder.provider}/{builder.model}")

    try:
        raw = await _call_provider(
            provider=builder.provider,
            model=builder.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=8000,
            temperature=0.3,
        )
    except Exception as e:
        logger.error(f"Builder call failed: {e}")
        return BuilderResult(
            outcome="ANSWER",
            response=f"Builder error: {e}",
            raw=str(e),
            provider=builder.provider,
            model=builder.model,
        )

    # Parse response
    parsed = extract_json(raw)
    if parsed:
        return BuilderResult(
            outcome=parsed.get("outcome", "ANSWER"),
            response=parsed.get("response", parsed.get("explanation", "")),
            actions=parsed.get("actions", []),
            explanation=parsed.get("explanation", ""),
            raw=raw,
            provider=builder.provider,
            model=builder.model,
        )

    # Couldn't parse JSON — return as plain answer
    return BuilderResult(
        outcome="ANSWER",
        response=raw,
        raw=raw,
        provider=builder.provider,
        model=builder.model,
    )
