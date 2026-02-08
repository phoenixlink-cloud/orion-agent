'use client'

import React from 'react'
import Link from 'next/link'
import Button from './Button'

interface RuleCardProps {
  id: string
  title: string
  description: string
}

function RuleCard({ id, title, description }: RuleCardProps) {
  return (
    <div
      style={{
        padding: '20px 24px',
        background: 'var(--tile)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)',
        marginBottom: 16,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
        <span
          style={{
            padding: '4px 10px',
            background: 'rgba(6, 9, 19, 0.9)',
            borderRadius: 999,
            fontSize: 12,
            fontWeight: 600,
            color: 'var(--glow)',
          }}
        >
          {id}
        </span>
        <span style={{ fontSize: 16, fontWeight: 500, color: 'var(--text)' }}>{title}</span>
      </div>
      <div style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.6 }}>{description}</div>
    </div>
  )
}

export default function AegisInfo() {
  return (
    <div
      style={{
        maxWidth: 800,
        margin: '0 auto',
        padding: '56px 20px',
      }}
    >
      {/* Header */}
      <div style={{ marginBottom: 48 }}>
        <div
          style={{
            fontSize: 'var(--h1-size)',
            fontWeight: 'var(--h1-weight)',
            color: 'var(--text)',
            marginBottom: 8,
          }}
        >
          AEGIS
        </div>
        <div style={{ fontSize: 18, color: 'var(--muted)', marginBottom: 24 }}>
          Governance Layer — How Orion Keeps Control
        </div>
        <div style={{ fontSize: 15, color: 'var(--text)', lineHeight: 1.7, opacity: 0.9 }}>
          Aegis is the governance layer that ensures Orion operates safely and transparently. 
          Every action Orion takes is subject to these non-negotiable rules. Aegis cannot be 
          disabled, bypassed, or overridden — it's the foundation of trust.
        </div>
      </div>

      {/* Core Principles */}
      <div style={{ marginBottom: 48 }}>
        <div
          style={{
            fontSize: 20,
            fontWeight: 500,
            color: 'var(--text)',
            marginBottom: 20,
          }}
        >
          Core Principles
        </div>

        <RuleCard
          id="AEGIS-1"
          title="Workspace Confinement"
          description="Orion can only read and write files within the designated workspace. No access to system files, other projects, or sensitive directories. This is enforced at the file operation level."
        />

        <RuleCard
          id="AEGIS-2"
          title="Mode Boundaries"
          description="Three governance modes (SAFE, PRO, PROJECT) define what Orion can do. SAFE requires approval for everything. PRO auto-approves safe operations. PROJECT enables command execution within allowlist."
        />

        <RuleCard
          id="AEGIS-3"
          title="No Workspace Escape"
          description="Path traversal attacks (../) are blocked. Symlinks pointing outside workspace are rejected. Absolute paths outside workspace are forbidden."
        />

        <RuleCard
          id="AEGIS-4"
          title="Human Approval Gates"
          description="Destructive operations always require explicit human approval. File deletions, overwrites, and command execution are never auto-approved regardless of mode."
        />

        <RuleCard
          id="AEGIS-5"
          title="Command Allowlist"
          description="Only pre-approved commands can be executed (dotnet, npm, python, git, etc.). Shell operators (|, &, >, ;) are banned. No arbitrary command execution."
        />

        <RuleCard
          id="AEGIS-6"
          title="Web Access Control"
          description="Only allowed domains can be fetched. Content is cached locally. No arbitrary network requests. Protects against data exfiltration."
        />
      </div>

      {/* How It Works */}
      <div style={{ marginBottom: 48 }}>
        <div
          style={{
            fontSize: 20,
            fontWeight: 500,
            color: 'var(--text)',
            marginBottom: 20,
          }}
        >
          How It Works
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 16,
          }}
        >
          {[
            { step: '1', title: 'Proposal', desc: 'Orion proposes an action' },
            { step: '2', title: 'Aegis Check', desc: 'Rules are validated' },
            { step: '3', title: 'Approval Gate', desc: 'Human confirms if needed' },
            { step: '4', title: 'Execution', desc: 'Action is performed' },
            { step: '5', title: 'Ledger', desc: 'Everything is logged' },
          ].map((item) => (
            <div
              key={item.step}
              style={{
                padding: '20px',
                background: 'var(--tile)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--r-md)',
                textAlign: 'center',
              }}
            >
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  background: 'rgba(6, 9, 19, 0.9)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 12px',
                  fontSize: 14,
                  fontWeight: 600,
                  color: 'var(--glow)',
                }}
              >
                {item.step}
              </div>
              <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>
                {item.title}
              </div>
              <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4 }}>
                {item.desc}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Immutable Ledger */}
      <div style={{ marginBottom: 48 }}>
        <div
          style={{
            fontSize: 20,
            fontWeight: 500,
            color: 'var(--text)',
            marginBottom: 12,
          }}
        >
          Immutable Ledger
        </div>
        <div style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.6 }}>
          Every proposal, approval, and execution is logged to an append-only ledger. 
          This creates a complete audit trail that cannot be modified. You can always 
          review what Orion did, when, and why.
        </div>
      </div>

      {/* Navigation */}
      <div style={{ display: 'flex', gap: 12 }}>
        <Link href="/chat">
          <Button variant="primary">Ask Orion</Button>
        </Link>
        <Link href="/">
          <Button variant="secondary">Back to Home</Button>
        </Link>
      </div>
    </div>
  )
}
