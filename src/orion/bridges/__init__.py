"""
Orion Agent — Messaging Bridges (v6.8.0)

Bidirectional messaging bridges that let users interact with Orion
through external platforms: Telegram, Slack, Discord.

Security model:
  1. Chat ID allowlist — only pre-authorized users can interact
  2. Passphrase authentication — first message must contain a secret
  3. AEGIS gate — destructive actions require inline approval
  4. Rate limiting — per-user request throttling
  5. All messages logged to ~/.orion/logs/orion.log

Usage:
    from orion.bridges import get_bridge_manager
    manager = get_bridge_manager()
    manager.enable("telegram", token="BOT_TOKEN")
    await manager.start_all()
"""
