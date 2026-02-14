'use client'

import React, { useEffect, useState } from 'react'
import Link from 'next/link'
import Shell from '@/components/Shell'
import Starfield from '@/visuals/Starfield'
import Button from '@/components/Button'

interface DashboardSection {
  title: string
  content: string
  style: string
}

interface SetupCheck {
  name: string
  status: string
  message: string
}

interface RoleInfo {
  name: string
  scope: string
  auth_method: string
  source: string
}

interface SessionInfo {
  session_id: string
  role: string
  goal: string
  status: string
}

export default function ARAPage() {
  const [setupChecks, setSetupChecks] = useState<SetupCheck[]>([])
  const [roles, setRoles] = useState<RoleInfo[]>([])
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [status, setStatus] = useState<string>('Loading...')
  const [error, setError] = useState<string | null>(null)

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

  useEffect(() => {
    async function loadData() {
      try {
        // Load setup status
        const setupRes = await fetch(`${API_BASE}/api/ara/setup`)
        if (setupRes.ok) {
          const setupData = await setupRes.json()
          setSetupChecks(setupData.data?.checks || [])
        }

        // Load roles
        const rolesRes = await fetch(`${API_BASE}/api/ara/roles`)
        if (rolesRes.ok) {
          const rolesData = await rolesRes.json()
          setRoles(rolesData.data?.roles || [])
        }

        // Load sessions
        const sessionsRes = await fetch(`${API_BASE}/api/ara/sessions`)
        if (sessionsRes.ok) {
          const sessionsData = await sessionsRes.json()
          setSessions(sessionsData.data?.sessions || [])
        }

        // Load current status
        const statusRes = await fetch(`${API_BASE}/api/ara/status`)
        if (statusRes.ok) {
          const statusData = await statusRes.json()
          setStatus(statusData.message || 'No active session')
        }

        setError(null)
      } catch (e: any) {
        setError('Could not connect to Orion API. Make sure the API server is running.')
      }
    }
    loadData()
  }, [API_BASE])

  const statusIcon = (s: string) => {
    if (s === 'ok') return '✓'
    if (s === 'not_configured') return '!'
    return '✗'
  }

  const statusColor = (s: string) => {
    if (s === 'ok') return 'var(--glow)'
    if (s === 'not_configured') return '#FFD666'
    return '#FF6B6B'
  }

  const sessionIcon = (s: string) => {
    const map: Record<string, string> = {
      running: '▶', paused: '⏸', completed: '✓', failed: '✗', cancelled: '⊘'
    }
    return map[s] || '?'
  }

  return (
    <>
      <Starfield />
      <div style={{ position: 'relative', zIndex: 1 }}>
        <Shell>
          <div style={{ maxWidth: 960, margin: '0 auto', padding: '40px 20px' }}>

            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 32 }}>
              <div>
                <Link href="/" style={{ color: 'var(--muted)', fontSize: 14 }}>← Back to Orion</Link>
                <h1 style={{ fontSize: 32, fontWeight: 500, color: 'var(--text)', marginTop: 8 }}>
                  Autonomous Role Architecture
                </h1>
                <p style={{ color: 'var(--muted)', fontSize: 15, marginTop: 4 }}>
                  Background task execution with configurable roles and AEGIS-gated promotion
                </p>
              </div>
            </div>

            {error && (
              <div style={{
                background: 'rgba(255, 107, 107, 0.1)',
                border: '1px solid rgba(255, 107, 107, 0.3)',
                borderRadius: 'var(--r-md)',
                padding: '16px 20px',
                marginBottom: 24,
                color: '#FF6B6B',
                fontSize: 14,
              }}>
                {error}
              </div>
            )}

            {/* Current Status */}
            <div style={{
              background: 'var(--tile)',
              border: '1px solid var(--line)',
              borderRadius: 'var(--r-md)',
              padding: '20px 24px',
              marginBottom: 24,
            }}>
              <h2 style={{ fontSize: 16, fontWeight: 500, color: 'var(--glow)', marginBottom: 12 }}>
                Current Status
              </h2>
              <p style={{ color: 'var(--text)', fontSize: 14 }}>{status}</p>
            </div>

            {/* Grid: Setup + Roles */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>

              {/* Setup Checks */}
              <div style={{
                background: 'var(--tile)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--r-md)',
                padding: '20px 24px',
              }}>
                <h2 style={{ fontSize: 16, fontWeight: 500, color: 'var(--glow)', marginBottom: 16 }}>
                  Setup Status
                </h2>
                {setupChecks.length === 0 ? (
                  <p style={{ color: 'var(--muted)', fontSize: 14 }}>Loading...</p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {setupChecks.map((c, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ color: statusColor(c.status), fontSize: 16, width: 20, textAlign: 'center' }}>
                          {statusIcon(c.status)}
                        </span>
                        <span style={{ color: 'var(--text)', fontSize: 14 }}>{c.message}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Roles */}
              <div style={{
                background: 'var(--tile)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--r-md)',
                padding: '20px 24px',
              }}>
                <h2 style={{ fontSize: 16, fontWeight: 500, color: 'var(--glow)', marginBottom: 16 }}>
                  Available Roles ({roles.length})
                </h2>
                {roles.length === 0 ? (
                  <p style={{ color: 'var(--muted)', fontSize: 14 }}>No roles found</p>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {roles.map((r, i) => (
                      <div key={i} style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '8px 12px',
                        background: 'rgba(159, 214, 255, 0.04)',
                        borderRadius: 'var(--r-sm)',
                        border: '1px solid rgba(159, 214, 255, 0.08)',
                      }}>
                        <div>
                          <span style={{ color: 'var(--text)', fontSize: 14, fontWeight: 500 }}>{r.name}</span>
                          {r.source === 'starter' && (
                            <span style={{ color: 'var(--muted)', fontSize: 12, marginLeft: 8 }}>(starter)</span>
                          )}
                        </div>
                        <div style={{ display: 'flex', gap: 12, color: 'var(--muted)', fontSize: 12 }}>
                          <span>{r.scope}</span>
                          <span>{r.auth_method}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Sessions */}
            <div style={{
              background: 'var(--tile)',
              border: '1px solid var(--line)',
              borderRadius: 'var(--r-md)',
              padding: '20px 24px',
              marginBottom: 24,
            }}>
              <h2 style={{ fontSize: 16, fontWeight: 500, color: 'var(--glow)', marginBottom: 16 }}>
                Sessions ({sessions.length})
              </h2>
              {sessions.length === 0 ? (
                <p style={{ color: 'var(--muted)', fontSize: 14 }}>
                  No sessions yet. Start one with <code style={{ color: 'var(--glow)' }}>/work &lt;role&gt; &lt;goal&gt;</code>
                </p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {sessions.map((s, i) => (
                    <div key={i} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '10px 14px',
                      background: 'rgba(159, 214, 255, 0.04)',
                      borderRadius: 'var(--r-sm)',
                      border: '1px solid rgba(159, 214, 255, 0.08)',
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: 16 }}>{sessionIcon(s.status)}</span>
                        <div>
                          <span style={{ color: 'var(--text)', fontSize: 14, fontWeight: 500 }}>
                            {s.session_id?.slice(0, 8)}
                          </span>
                          <span style={{ color: 'var(--muted)', fontSize: 13, marginLeft: 8 }}>
                            {s.role} — {s.goal?.slice(0, 60)}
                          </span>
                        </div>
                      </div>
                      <span style={{
                        fontSize: 12, padding: '2px 8px', borderRadius: 6,
                        background: s.status === 'running' ? 'rgba(159, 214, 255, 0.15)' : 'rgba(159, 214, 255, 0.05)',
                        color: s.status === 'running' ? 'var(--glow)' : 'var(--muted)',
                      }}>
                        {s.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Navigation */}
            <div style={{ display: 'flex', gap: 14, justifyContent: 'center', flexWrap: 'wrap' }}>
              <Link href="/chat">
                <Button variant="primary">Ask Orion</Button>
              </Link>
              <Link href="/settings">
                <Button variant="secondary">Settings</Button>
              </Link>
            </div>
          </div>
        </Shell>
      </div>
    </>
  )
}
