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
#    See LICENSE-ENTERPRISE.md or contact licensing@phoenixlink.co.za
#
# Contributions require a signed CLA. See COPYRIGHT.md and CLA.md.
"""
Orion Agent -- Platform Registry (v6.4.0)

Comprehensive registry of ALL platforms Orion can connect to.
Each platform defines:
  - Auth method (oauth, api_key, token, none)
  - Capabilities Orion can use when connected
  - Setup instructions and URLs
  - Connection status (via SecureStore + env vars)

Categories:
  - ai_models:      LLM providers (OpenAI, Anthropic, Google, Ollama, Groq, etc.)
  - developer_tools: GitHub, GitLab, Docker, Notion
  - messaging:       Slack, Discord, Telegram
  - voice:           ElevenLabs, Edge TTS, Whisper, Piper, Vosk
  - image:           DALL-E, Stability AI, SDXL
  - cloud_storage:   Google Drive, OneDrive (via OAuth)

Usage:
    from orion.integrations.platforms import get_platform_registry
    registry = get_platform_registry()
    platforms = registry.list_all()
    connected = registry.list_connected()
    github = registry.get("github")
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger("orion.integrations.platforms")


class AuthMethod(Enum):
    NONE = "none"
    API_KEY = "api_key"
    TOKEN = "token"
    OAUTH = "oauth"
    CLI_TOOL = "cli_tool"  # Like CLI delegation: delegates to installed CLI (gh, docker, etc.)


class PlatformCategory(Enum):
    AI_MODELS = "ai_models"
    DEVELOPER_TOOLS = "developer_tools"
    MESSAGING = "messaging"
    VOICE = "voice"
    IMAGE = "image"
    CLOUD_STORAGE = "cloud_storage"


@dataclass
class PlatformCapability:
    """A single thing Orion can do with this platform when connected."""
    name: str
    description: str
    example_prompt: str = ""


@dataclass
class PlatformDef:
    """Definition of a single platform."""
    id: str
    name: str
    category: PlatformCategory
    description: str
    icon: str                          # Emoji for display
    auth_method: AuthMethod
    # Auth configuration
    env_var: str = ""                  # Primary env var (e.g. OPENAI_API_KEY)
    env_var_alt: str = ""              # Alternate env var name
    secure_store_key: str = ""         # Key in SecureStore (defaults to id)
    oauth_provider: str = ""           # Maps to OAUTH_PLATFORMS in server.py
    cli_tool: str = ""                 # CLI binary name (e.g. "gh", "docker") -- CLI delegation pattern
    # Setup
    setup_url: str = ""                # URL to get API key / create OAuth app
    setup_instructions: str = ""       # Short setup guide
    package_name: str = ""             # Python package needed (for health check)
    # What Orion can do with this platform
    capabilities: List[PlatformCapability] = field(default_factory=list)
    # Display
    free_tier: str = ""                # Free tier info
    cost_info: str = ""                # Pricing info
    is_local: bool = False             # Runs locally (no API key needed)
    # State (filled at runtime)
    connected: bool = False
    connection_source: str = ""        # "environment", "secure_store", "oauth", "local", "cli_tool"
    status_message: str = ""


# =============================================================================
# PLATFORM DEFINITIONS
# =============================================================================

def _build_platforms() -> Dict[str, PlatformDef]:
    """Build the complete platform registry."""
    platforms = {}

    def _add(p: PlatformDef):
        if not p.secure_store_key:
            p.secure_store_key = p.id
        platforms[p.id] = p

    # =========================================================================
    # AI MODEL PROVIDERS
    # =========================================================================

    _add(PlatformDef(
        id="ollama", name="Ollama (Local)", category=PlatformCategory.AI_MODELS,
        description="Run AI models locally on your machine -- completely free and private",
        icon="🦙", auth_method=AuthMethod.NONE,
        package_name="httpx", is_local=True,
        free_tier="Unlimited -- runs on your hardware",
        setup_url="https://ollama.com/download",
        setup_instructions="Download and install Ollama, then run: ollama pull qwen2.5-coder:14b",
        capabilities=[
            PlatformCapability("chat", "Chat with local AI models", "explain this code"),
            PlatformCapability("code_generation", "Generate and edit code locally", "write a function to sort a list"),
            PlatformCapability("code_review", "Review code changes", "review my changes"),
        ],
    ))

    _add(PlatformDef(
        id="openai", name="OpenAI", category=PlatformCategory.AI_MODELS,
        description="GPT-4o, GPT-4, o1 -- powerful reasoning and code generation",
        icon="🟢", auth_method=AuthMethod.API_KEY,
        env_var="OPENAI_API_KEY", package_name="openai",
        setup_url="https://platform.openai.com/api-keys",
        setup_instructions="Create an API key at platform.openai.com -> API Keys",
        cost_info="Pay-per-use, ~$2.50/M input tokens for GPT-4o",
        capabilities=[
            PlatformCapability("chat", "Advanced reasoning with GPT-4o", "analyze this architecture"),
            PlatformCapability("code_generation", "Generate code with GPT-4o", "implement a REST API"),
            PlatformCapability("image_generation", "Generate images with DALL-E", "create a logo for my app"),
            PlatformCapability("speech_to_text", "Transcribe audio with Whisper", "transcribe this recording"),
            PlatformCapability("text_to_speech", "Generate speech with OpenAI TTS", "read this aloud"),
        ],
    ))

    _add(PlatformDef(
        id="anthropic", name="Anthropic", category=PlatformCategory.AI_MODELS,
        description="Claude 4 Sonnet & Opus -- excellent for code review and analysis",
        icon="🟠", auth_method=AuthMethod.API_KEY,
        env_var="ANTHROPIC_API_KEY", package_name="anthropic",
        setup_url="https://console.anthropic.com/settings/keys",
        setup_instructions="Create an API key at console.anthropic.com -> Settings -> API Keys",
        cost_info="Pay-per-use, ~$3/M input tokens for Claude Sonnet",
        capabilities=[
            PlatformCapability("chat", "Deep analysis with Claude", "review this PR for security issues"),
            PlatformCapability("code_review", "Expert code review", "what could go wrong with this approach?"),
            PlatformCapability("code_generation", "Generate code with Claude", "refactor this module"),
        ],
    ))

    _add(PlatformDef(
        id="google", name="Google Gemini", category=PlatformCategory.AI_MODELS,
        description="Gemini 2.5 Pro & Flash -- free tier with 1500 req/day",
        icon="🔵", auth_method=AuthMethod.OAUTH,
        env_var="GOOGLE_API_KEY", oauth_provider="google",
        package_name="google.generativeai",
        setup_url="https://aistudio.google.com/apikey",
        setup_instructions="Get a free API key at Google AI Studio, or connect your Google account for OAuth",
        free_tier="1,500 requests/day free",
        capabilities=[
            PlatformCapability("chat", "Chat with Gemini models", "summarize this codebase"),
            PlatformCapability("code_generation", "Generate code with Gemini", "write unit tests"),
            PlatformCapability("google_drive", "Access Google Drive files (OAuth)", "read my design doc from Drive"),
            PlatformCapability("google_docs", "Read/write Google Docs (OAuth)", "update the project spec"),
        ],
    ))

    _add(PlatformDef(
        id="groq", name="Groq", category=PlatformCategory.AI_MODELS,
        description="Ultra-fast inference -- Llama 3.3 70B at 500+ tokens/sec",
        icon="⚡", auth_method=AuthMethod.API_KEY,
        env_var="GROQ_API_KEY", package_name="groq",
        setup_url="https://console.groq.com/keys",
        setup_instructions="Create a free API key at console.groq.com",
        free_tier="Free tier available",
        capabilities=[
            PlatformCapability("chat", "Ultra-fast AI responses", "quick explain this error"),
            PlatformCapability("code_generation", "Fast code generation", "generate boilerplate"),
        ],
    ))

    _add(PlatformDef(
        id="mistral", name="Mistral AI", category=PlatformCategory.AI_MODELS,
        description="Mistral Large & Codestral -- strong coding models from Europe",
        icon="🌊", auth_method=AuthMethod.API_KEY,
        env_var="MISTRAL_API_KEY", package_name="mistralai",
        setup_url="https://console.mistral.ai/api-keys",
        setup_instructions="Create an API key at console.mistral.ai",
        cost_info="Pay-per-use",
        capabilities=[
            PlatformCapability("chat", "Chat with Mistral models", "explain this algorithm"),
            PlatformCapability("code_generation", "Code with Codestral", "optimize this function"),
        ],
    ))

    _add(PlatformDef(
        id="cohere", name="Cohere", category=PlatformCategory.AI_MODELS,
        description="Command R+ -- strong for RAG and enterprise search",
        icon="🟣", auth_method=AuthMethod.API_KEY,
        env_var="COHERE_API_KEY", package_name="cohere",
        setup_url="https://dashboard.cohere.com/api-keys",
        setup_instructions="Create an API key at dashboard.cohere.com",
        free_tier="Free trial available",
        capabilities=[
            PlatformCapability("chat", "Chat with Command R+", "search through these docs"),
            PlatformCapability("embeddings", "Generate text embeddings", "find similar code"),
        ],
    ))

    _add(PlatformDef(
        id="together", name="Together AI", category=PlatformCategory.AI_MODELS,
        description="Run open-source models (Llama, Mixtral, DeepSeek) in the cloud",
        icon="🤝", auth_method=AuthMethod.API_KEY,
        env_var="TOGETHER_API_KEY", package_name="together",
        setup_url="https://api.together.xyz/settings/api-keys",
        setup_instructions="Create an API key at together.xyz",
        free_tier="$25 free credit on signup",
        capabilities=[
            PlatformCapability("chat", "Chat with open-source models", "explain this code"),
            PlatformCapability("code_generation", "Code with DeepSeek/CodeLlama", "write a parser"),
        ],
    ))

    _add(PlatformDef(
        id="openrouter", name="OpenRouter", category=PlatformCategory.AI_MODELS,
        description="Access 100+ models through one API -- compare providers easily",
        icon="🔀", auth_method=AuthMethod.API_KEY,
        env_var="OPENROUTER_API_KEY", package_name="openai",
        setup_url="https://openrouter.ai/keys",
        setup_instructions="Create an API key at openrouter.ai",
        free_tier="Some free models available",
        capabilities=[
            PlatformCapability("chat", "Chat with any model", "compare GPT-4o vs Claude on this task"),
        ],
    ))

    # =========================================================================
    # DEVELOPER TOOLS
    # =========================================================================

    _add(PlatformDef(
        id="github", name="GitHub", category=PlatformCategory.DEVELOPER_TOOLS,
        description="Repositories, issues, pull requests, code search, Actions CI/CD",
        icon="🐙", auth_method=AuthMethod.CLI_TOOL,
        env_var="GITHUB_TOKEN", cli_tool="gh",
        setup_url="https://cli.github.com/",
        setup_instructions="Install the GitHub CLI (gh), then run: gh auth login",
        free_tier="Public repos free, unlimited private repos",
        capabilities=[
            PlatformCapability("list_repos", "List your repositories", "show my GitHub repos"),
            PlatformCapability("search_code", "Search code across repos", "find where auth is handled in my repos"),
            PlatformCapability("create_issue", "Create GitHub issues", "create an issue for this bug"),
            PlatformCapability("create_pr", "Create pull requests", "open a PR for these changes"),
            PlatformCapability("read_issues", "Read and analyze issues", "what are the open issues?"),
            PlatformCapability("read_pr", "Review pull requests", "summarize the latest PR"),
            PlatformCapability("read_file", "Read files from repos", "show me the README from my-repo"),
        ],
    ))

    _add(PlatformDef(
        id="gitlab", name="GitLab", category=PlatformCategory.DEVELOPER_TOOLS,
        description="Repositories, merge requests, CI/CD pipelines, issue tracking",
        icon="🦊", auth_method=AuthMethod.CLI_TOOL,
        env_var="GITLAB_TOKEN", cli_tool="glab",
        setup_url="https://gitlab.com/-/user_settings/personal_access_tokens",
        setup_instructions="Install glab CLI or create a personal access token at GitLab -> Settings -> Access Tokens",
        free_tier="Public repos free",
        capabilities=[
            PlatformCapability("list_repos", "List your GitLab projects", "show my GitLab projects"),
            PlatformCapability("create_issue", "Create GitLab issues", "create an issue for this"),
            PlatformCapability("create_mr", "Create merge requests", "open an MR for these changes"),
            PlatformCapability("read_pipeline", "Check CI/CD status", "what's the pipeline status?"),
        ],
    ))

    _add(PlatformDef(
        id="docker", name="Docker", category=PlatformCategory.DEVELOPER_TOOLS,
        description="Run code in isolated containers -- safe sandbox execution",
        icon="🐳", auth_method=AuthMethod.NONE,
        package_name="docker", is_local=True,
        setup_url="https://docs.docker.com/get-docker/",
        setup_instructions="Install Docker Desktop -- no API key needed",
        free_tier="Free for personal use",
        capabilities=[
            PlatformCapability("run_code", "Execute code safely in containers", "run this Python script in a sandbox"),
            PlatformCapability("test_code", "Run tests in isolation", "run pytest in a container"),
        ],
    ))

    _add(PlatformDef(
        id="notion", name="Notion", category=PlatformCategory.DEVELOPER_TOOLS,
        description="Access Notion pages, databases, and project docs",
        icon="📝", auth_method=AuthMethod.TOKEN,
        env_var="NOTION_TOKEN",
        setup_url="https://www.notion.so/my-integrations",
        setup_instructions="Create an integration at notion.so/my-integrations -> copy the Internal Integration Token",
        free_tier="Free personal plan",
        capabilities=[
            PlatformCapability("read_pages", "Read Notion pages", "read my project spec from Notion"),
            PlatformCapability("search_docs", "Search Notion workspace", "find the design doc in Notion"),
            PlatformCapability("create_page", "Create Notion pages", "create a meeting notes page"),
        ],
    ))

    _add(PlatformDef(
        id="linear", name="Linear", category=PlatformCategory.DEVELOPER_TOOLS,
        description="Issue tracking and project management",
        icon="📐", auth_method=AuthMethod.API_KEY,
        env_var="LINEAR_API_KEY",
        setup_url="https://linear.app/settings/api",
        setup_instructions="Create an API key at linear.app -> Settings -> API -> Personal API keys",
        free_tier="Free for small teams",
        capabilities=[
            PlatformCapability("list_issues", "List Linear issues", "show my open issues in Linear"),
            PlatformCapability("create_issue", "Create Linear issues", "create a bug report in Linear"),
        ],
    ))

    _add(PlatformDef(
        id="jira", name="Jira", category=PlatformCategory.DEVELOPER_TOOLS,
        description="Issue tracking for enterprise teams",
        icon="📋", auth_method=AuthMethod.TOKEN,
        env_var="JIRA_API_TOKEN",
        setup_url="https://id.atlassian.com/manage-profile/security/api-tokens",
        setup_instructions="Create an API token at id.atlassian.com -> Security -> API tokens",
        free_tier="Free for up to 10 users",
        capabilities=[
            PlatformCapability("list_issues", "List Jira tickets", "show my open Jira tickets"),
            PlatformCapability("create_issue", "Create Jira tickets", "create a story for this feature"),
        ],
    ))

    # =========================================================================
    # MESSAGING
    # =========================================================================

    _add(PlatformDef(
        id="slack", name="Slack", category=PlatformCategory.MESSAGING,
        description="Send messages, notifications, and code snippets to Slack channels",
        icon="💬", auth_method=AuthMethod.TOKEN,
        env_var="SLACK_BOT_TOKEN",
        package_name="slack_sdk",
        setup_url="https://api.slack.com/apps",
        setup_instructions="Create a Slack app at api.slack.com/apps -> OAuth & Permissions -> copy Bot User OAuth Token",
        free_tier="Free for small teams",
        capabilities=[
            PlatformCapability("send_message", "Send messages to Slack", "post the build status to #dev"),
            PlatformCapability("send_snippet", "Share code snippets", "share this function in #code-review"),
            PlatformCapability("read_channel", "Read channel history", "what was discussed in #architecture?"),
        ],
    ))

    _add(PlatformDef(
        id="discord", name="Discord", category=PlatformCategory.MESSAGING,
        description="Send messages and notifications to Discord servers",
        icon="🎮", auth_method=AuthMethod.TOKEN,
        env_var="DISCORD_BOT_TOKEN",
        package_name="discord",
        setup_url="https://discord.com/developers/applications",
        setup_instructions="Create a Discord bot at discord.com/developers -> Bot -> copy Token",
        free_tier="Free",
        capabilities=[
            PlatformCapability("send_message", "Send messages to Discord", "post update to #general"),
        ],
    ))

    _add(PlatformDef(
        id="telegram", name="Telegram", category=PlatformCategory.MESSAGING,
        description="Send notifications and updates via Telegram bot",
        icon="✈️", auth_method=AuthMethod.TOKEN,
        env_var="TELEGRAM_BOT_TOKEN",
        setup_url="https://t.me/BotFather",
        setup_instructions="Message @BotFather on Telegram to create a bot and get the token",
        free_tier="Free",
        capabilities=[
            PlatformCapability("send_message", "Send Telegram notifications", "notify me when the build finishes"),
        ],
    ))

    # =========================================================================
    # VOICE
    # =========================================================================

    _add(PlatformDef(
        id="elevenlabs", name="ElevenLabs", category=PlatformCategory.VOICE,
        description="Premium text-to-speech with natural-sounding voices",
        icon="🎙️", auth_method=AuthMethod.API_KEY,
        env_var="ELEVENLABS_API_KEY", package_name="elevenlabs",
        setup_url="https://elevenlabs.io/app/settings/api-keys",
        setup_instructions="Create an API key at elevenlabs.io",
        free_tier="10,000 characters/month free",
        capabilities=[
            PlatformCapability("text_to_speech", "Convert text to speech", "read this explanation aloud"),
        ],
    ))

    _add(PlatformDef(
        id="edge_tts", name="Edge TTS", category=PlatformCategory.VOICE,
        description="Free text-to-speech using Microsoft Edge voices -- no API key needed",
        icon="🔊", auth_method=AuthMethod.NONE,
        package_name="edge_tts", is_local=True,
        setup_url="https://pypi.org/project/edge-tts/",
        setup_instructions="pip install edge-tts",
        free_tier="Unlimited -- free",
        capabilities=[
            PlatformCapability("text_to_speech", "Free text-to-speech", "read this aloud"),
        ],
    ))

    _add(PlatformDef(
        id="whisper_local", name="Whisper (Local)", category=PlatformCategory.VOICE,
        description="Local speech-to-text using OpenAI's Whisper model -- runs offline",
        icon="👂", auth_method=AuthMethod.NONE,
        package_name="whisper", is_local=True,
        setup_url="https://github.com/openai/whisper",
        setup_instructions="pip install openai-whisper",
        free_tier="Unlimited -- runs on your hardware",
        capabilities=[
            PlatformCapability("speech_to_text", "Transcribe audio locally", "transcribe this recording"),
        ],
    ))

    _add(PlatformDef(
        id="piper_tts", name="Piper TTS", category=PlatformCategory.VOICE,
        description="Fast local text-to-speech -- lightweight and offline",
        icon="🎵", auth_method=AuthMethod.NONE,
        package_name="piper", is_local=True,
        setup_url="https://github.com/rhasspy/piper",
        setup_instructions="pip install piper-tts",
        free_tier="Unlimited -- runs locally",
        capabilities=[
            PlatformCapability("text_to_speech", "Fast local TTS", "read this quickly"),
        ],
    ))

    # =========================================================================
    # IMAGE GENERATION
    # =========================================================================

    _add(PlatformDef(
        id="dalle", name="DALL-E 3", category=PlatformCategory.IMAGE,
        description="Generate images from text descriptions -- via OpenAI",
        icon="🎨", auth_method=AuthMethod.API_KEY,
        env_var="OPENAI_API_KEY", secure_store_key="openai",
        package_name="openai",
        setup_url="https://platform.openai.com/api-keys",
        setup_instructions="Uses your OpenAI API key",
        cost_info="$0.04/image (standard), $0.08/image (HD)",
        capabilities=[
            PlatformCapability("generate_image", "Generate images from text", "create a diagram of this architecture"),
        ],
    ))

    _add(PlatformDef(
        id="stability", name="Stability AI", category=PlatformCategory.IMAGE,
        description="Stable Diffusion image generation in the cloud",
        icon="🖼️", auth_method=AuthMethod.API_KEY,
        env_var="STABILITY_API_KEY",
        setup_url="https://platform.stability.ai/account/keys",
        setup_instructions="Create an API key at platform.stability.ai",
        cost_info="Pay-per-image, ~$0.01-0.05 per image",
        capabilities=[
            PlatformCapability("generate_image", "Generate images with Stable Diffusion", "create a UI mockup"),
        ],
    ))

    _add(PlatformDef(
        id="sdxl_local", name="SDXL (Local)", category=PlatformCategory.IMAGE,
        description="Run Stable Diffusion XL locally via ComfyUI -- completely free",
        icon="🎭", auth_method=AuthMethod.NONE,
        package_name="diffusers", is_local=True,
        setup_url="https://github.com/comfyanonymous/ComfyUI",
        setup_instructions="Install ComfyUI or diffusers: pip install diffusers",
        free_tier="Unlimited -- runs on your GPU",
        capabilities=[
            PlatformCapability("generate_image", "Local image generation", "generate an icon locally"),
        ],
    ))

    # =========================================================================
    # CLOUD STORAGE (via OAuth)
    # =========================================================================

    _add(PlatformDef(
        id="google_drive", name="Google Drive", category=PlatformCategory.CLOUD_STORAGE,
        description="Access files and documents from Google Drive",
        icon="📁", auth_method=AuthMethod.OAUTH,
        oauth_provider="google",
        setup_instructions="Connect your Google account to access Drive files",
        free_tier="15 GB free storage",
        capabilities=[
            PlatformCapability("read_file", "Read files from Drive", "open my design doc from Drive"),
            PlatformCapability("search_files", "Search Drive files", "find the API spec in Drive"),
        ],
    ))

    _add(PlatformDef(
        id="onedrive", name="OneDrive", category=PlatformCategory.CLOUD_STORAGE,
        description="Access files from Microsoft OneDrive and SharePoint",
        icon="☁️", auth_method=AuthMethod.OAUTH,
        oauth_provider="microsoft",
        setup_instructions="Connect your Microsoft account to access OneDrive files",
        free_tier="5 GB free storage",
        capabilities=[
            PlatformCapability("read_file", "Read files from OneDrive", "open the spec from OneDrive"),
        ],
    ))

    return platforms


# =============================================================================
# PLATFORM REGISTRY
# =============================================================================

class PlatformRegistry:
    """
    Central registry for all platforms Orion can connect to.

    Checks connection status via:
      1. Environment variables (highest priority)
      2. SecureStore credentials
      3. OAuth tokens
      4. Local service availability
    """

    def __init__(self):
        self._platforms = _build_platforms()
        self._refresh_status()

    def _refresh_status(self):
        """Check connection status of all platforms."""
        store = self._get_store()

        for pid, platform in self._platforms.items():
            platform.connected = False
            platform.connection_source = ""
            platform.status_message = "Not connected"

            # Check 1: Environment variable
            if platform.env_var and os.environ.get(platform.env_var):
                platform.connected = True
                platform.connection_source = "environment"
                platform.status_message = "Connected via environment variable"
                continue

            if platform.env_var_alt and os.environ.get(platform.env_var_alt):
                platform.connected = True
                platform.connection_source = "environment"
                platform.status_message = "Connected via environment variable"
                continue

            # Check 2: SecureStore
            if store and platform.secure_store_key:
                if store.has_key(platform.secure_store_key):
                    platform.connected = True
                    platform.connection_source = "secure_store"
                    platform.status_message = f"Connected via secure store ({store.backend_name})"
                    continue

            # Check 3: OAuth token
            if platform.oauth_provider and store:
                if store.has_key(f"oauth_{platform.oauth_provider}_access_token"):
                    platform.connected = True
                    platform.connection_source = "oauth"
                    platform.status_message = "Connected via OAuth"
                    continue

            # Check 4: CLI tool detection (CLI delegation pattern)
            if platform.cli_tool:
                if self._check_cli_tool(platform.cli_tool):
                    platform.connected = True
                    platform.connection_source = "cli_tool"
                    platform.status_message = f"Connected via {platform.cli_tool} CLI"
                    continue

            # Check 5: Local service (is_local=True, no auth needed)
            if platform.is_local:
                platform.connected = True
                platform.connection_source = "local"
                platform.status_message = "Available locally (no setup needed)"

    def _get_store(self):
        try:
            from orion.security.store import get_secure_store
            store = get_secure_store()
            return store if store.is_available else None
        except Exception:
            return None

    @staticmethod
    def _check_cli_tool(tool_name: str) -> bool:
        """Check if a CLI tool is installed and available (CLI delegation pattern)."""
        import shutil
        return shutil.which(tool_name) is not None

    def refresh(self):
        """Refresh all platform statuses."""
        self._refresh_status()

    def get(self, platform_id: str) -> Optional[PlatformDef]:
        """Get a platform by ID."""
        return self._platforms.get(platform_id)

    def list_all(self) -> List[Dict[str, Any]]:
        """List all platforms with status."""
        self._refresh_status()
        return [self._serialize(p) for p in self._platforms.values()]

    def list_by_category(self) -> Dict[str, List[Dict[str, Any]]]:
        """List platforms grouped by category."""
        self._refresh_status()
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for p in self._platforms.values():
            cat = p.category.value
            if cat not in groups:
                groups[cat] = []
            groups[cat].append(self._serialize(p))
        return groups

    def list_connected(self) -> List[Dict[str, Any]]:
        """List only connected platforms."""
        self._refresh_status()
        return [self._serialize(p) for p in self._platforms.values() if p.connected]

    def list_capabilities(self) -> Dict[str, List[str]]:
        """
        List all available capabilities from connected platforms.
        Returns: { "capability_name": ["platform_id", ...] }
        """
        self._refresh_status()
        caps: Dict[str, List[str]] = {}
        for p in self._platforms.values():
            if not p.connected:
                continue
            for cap in p.capabilities:
                if cap.name not in caps:
                    caps[cap.name] = []
                caps[cap.name].append(p.id)
        return caps

    def get_platform_for_capability(self, capability: str) -> Optional[PlatformDef]:
        """Find the best connected platform that provides a capability."""
        self._refresh_status()
        for p in self._platforms.values():
            if not p.connected:
                continue
            for cap in p.capabilities:
                if cap.name == capability:
                    return p
        return None

    def _serialize(self, p: PlatformDef) -> Dict[str, Any]:
        """Serialize a platform for API responses."""
        return {
            "id": p.id,
            "name": p.name,
            "category": p.category.value,
            "description": p.description,
            "icon": p.icon,
            "auth_method": p.auth_method.value,
            "setup_url": p.setup_url,
            "setup_instructions": p.setup_instructions,
            "free_tier": p.free_tier,
            "cost_info": p.cost_info,
            "is_local": p.is_local,
            "connected": p.connected,
            "connection_source": p.connection_source,
            "status_message": p.status_message,
            "oauth_provider": p.oauth_provider,
            "env_var": p.env_var,
            "capabilities": [
                {"name": c.name, "description": c.description, "example": c.example_prompt}
                for c in p.capabilities
            ],
        }


# =============================================================================
# SINGLETON
# =============================================================================

_registry: Optional[PlatformRegistry] = None


def get_platform_registry() -> PlatformRegistry:
    """Get or create the global platform registry."""
    global _registry
    if _registry is None:
        _registry = PlatformRegistry()
    return _registry


# =============================================================================
# CATEGORY DISPLAY NAMES
# =============================================================================

CATEGORY_LABELS = {
    "ai_models": {"label": "AI Models", "description": "Language models for coding, analysis, and generation", "icon": "🧠"},
    "developer_tools": {"label": "Developer Tools", "description": "Git, issue tracking, containers, and docs", "icon": "🛠️"},
    "messaging": {"label": "Messaging", "description": "Send notifications and updates to your team", "icon": "💬"},
    "voice": {"label": "Voice", "description": "Text-to-speech and speech-to-text", "icon": "🎙️"},
    "image": {"label": "Image Generation", "description": "Create images, diagrams, and mockups", "icon": "🎨"},
    "cloud_storage": {"label": "Cloud Storage", "description": "Access files from cloud drives", "icon": "☁️"},
}
