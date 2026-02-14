'use client'

import React, { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'

/* ── types ─────────────────────────────────────────────────────── */
interface SetupCheck { name: string; status: string; message: string }
interface RoleInfo { name: string; scope: string; auth_method: string; source: string }
interface SessionInfo { session_id: string; role: string; goal: string; status: string; cost_usd?: number; elapsed_seconds?: number; progress?: number }

/* ── main page ─────────────────────────────────────────────────── */
export default function ARAPage() {
  const [setupChecks, setSetupChecks] = useState<SetupCheck[]>([])
  const [roles, setRoles] = useState<RoleInfo[]>([])
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [statusMsg, setStatusMsg] = useState('No active session')
  const [statusData, setStatusData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeNav, setActiveNav] = useState('dashboard')
  const [activeTab, setActiveTab] = useState('in_progress')
  const [chatMessages, setChatMessages] = useState<{role: string; text: string}[]>([
    { role: 'ai', text: "Welcome to the ARA Dashboard. I'm monitoring your autonomous sessions. Use /work <role> <goal> in the CLI to start a session, or browse the panels here." },
  ])
  const [chatInput, setChatInput] = useState('')

  const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

  const loadData = useCallback(async () => {
    try {
      const [setupR, rolesR, sessR, statusR] = await Promise.allSettled([
        fetch(`${API}/api/ara/setup`),
        fetch(`${API}/api/ara/roles`),
        fetch(`${API}/api/ara/sessions`),
        fetch(`${API}/api/ara/status`),
      ])
      if (setupR.status === 'fulfilled' && setupR.value.ok) {
        const d = await setupR.value.json(); setSetupChecks(d.data?.checks || [])
      }
      if (rolesR.status === 'fulfilled' && rolesR.value.ok) {
        const d = await rolesR.value.json(); setRoles(d.data?.roles || [])
      }
      if (sessR.status === 'fulfilled' && sessR.value.ok) {
        const d = await sessR.value.json(); setSessions(d.data?.sessions || [])
      }
      if (statusR.status === 'fulfilled' && statusR.value.ok) {
        const d = await statusR.value.json(); setStatusMsg(d.message || 'No active session'); setStatusData(d.data)
      }
      setError(null)
    } catch { setError('Could not connect to Orion API.') }
  }, [API])

  useEffect(() => { loadData(); const t = setInterval(loadData, 10000); return () => clearInterval(t) }, [loadData])

  const running = sessions.filter(s => s.status === 'running')
  const paused = sessions.filter(s => s.status === 'paused')
  const completed = sessions.filter(s => s.status === 'completed')
  const failed = sessions.filter(s => s.status === 'failed' || s.status === 'cancelled')
  const currentTask = running[0]
  const progress = currentTask?.progress ?? 0
  const isWorking = running.length > 0

  const tabSessions: Record<string, SessionInfo[]> = {
    in_progress: running,
    paused: paused,
    completed: completed,
    failed: failed,
  }

  const handleSessionAction = async (action: string) => {
    try {
      await fetch(`${API}/api/ara/${action}`, { method: 'POST' })
      setTimeout(loadData, 500)
    } catch {}
  }

  /* ── styles (matching prototype) ───────────────────────────── */
  const C = {
    bg0: '#0a0a0f', bg1: '#12121a', bg2: '#1a1a24', bg3: '#22222e',
    border: '#2a2a3a', borderSub: '#1e1e2a',
    txt: '#f0f0f5', txtSec: '#8888a0', txtMut: '#5a5a70',
    blue: '#3b82f6', green: '#22c55e', amber: '#f59e0b', red: '#ef4444', purple: '#a855f7',
    glowBlue: 'rgba(59,130,246,0.15)', glowGreen: 'rgba(34,197,94,0.15)', glowAmber: 'rgba(245,158,11,0.15)',
  }

  const dashOffset = 264 - (264 * progress / 100)

  return (
    <div style={{
      fontFamily: "'Plus Jakarta Sans','Inter',system-ui,sans-serif",
      background: C.bg0, color: C.txt, minHeight: '100vh',
    }}>
      {/* Grid background */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 0, opacity: 0.25, pointerEvents: 'none',
        backgroundImage: `linear-gradient(${C.borderSub} 1px, transparent 1px), linear-gradient(90deg, ${C.borderSub} 1px, transparent 1px)`,
        backgroundSize: '40px 40px',
      }} />

      <div style={{
        display: 'grid', gridTemplateColumns: '260px 1fr 340px', gridTemplateRows: '64px 1fr',
        minHeight: '100vh', position: 'relative', zIndex: 1,
      }}>

        {/* ── HEADER ──────────────────────────────────────── */}
        <header style={{
          gridColumn: '1 / -1', background: C.bg1, borderBottom: `1px solid ${C.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
              background: `linear-gradient(135deg, ${C.blue}, ${C.purple})`,
              fontWeight: 700, fontSize: 16, boxShadow: `0 0 20px ${C.glowBlue}`,
            }}>O</div>
            <div style={{ fontWeight: 700, fontSize: 18, letterSpacing: -0.5 }}>
              Orion <span style={{ color: C.txtMut, fontWeight: 400 }}>Agent</span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, background: C.bg2,
              padding: '6px 14px', borderRadius: 20, fontSize: 13, fontFamily: 'monospace',
            }}>
              <span style={{
                width: 8, height: 8, borderRadius: '50%',
                background: isWorking ? C.green : C.txtMut,
                boxShadow: isWorking ? `0 0 8px ${C.green}` : 'none',
                animation: isWorking ? 'pulse 2s ease-in-out infinite' : 'none',
              }} />
              {isWorking ? 'WORKING' : 'IDLE'}
            </div>
            <Link href="/" style={{ fontSize: 13, color: C.blue }}>← Back to Orion</Link>
          </div>
        </header>

        {/* ── SIDEBAR ─────────────────────────────────────── */}
        <nav style={{
          background: C.bg1, borderRight: `1px solid ${C.border}`, padding: '20px 14px',
          display: 'flex', flexDirection: 'column', gap: 6,
        }}>
          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1.5, color: C.txtMut, padding: '0 12px', marginBottom: 8 }}>Overview</div>
          {[
            { id: 'dashboard', icon: '◫', label: 'Dashboard' },
            { id: 'activity', icon: '⚡', label: 'Activity' },
          ].map(n => (
            <button key={n.id} onClick={() => setActiveNav(n.id)} style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 10,
              border: activeNav === n.id ? `1px solid rgba(59,130,246,0.3)` : '1px solid transparent',
              background: activeNav === n.id ? C.glowBlue : 'transparent',
              color: activeNav === n.id ? C.blue : C.txtSec,
              fontSize: 14, fontWeight: 500, cursor: 'pointer', width: '100%', textAlign: 'left',
            }}><span style={{ fontSize: 16 }}>{n.icon}</span> {n.label}</button>
          ))}

          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1.5, color: C.txtMut, padding: '0 12px', marginTop: 16, marginBottom: 8 }}>Work</div>
          {[
            { id: 'tasks', icon: '☑', label: 'Tasks', badge: running.length + paused.length },
            { id: 'deliverables', icon: '📄', label: 'Deliverables' },
            { id: 'consent', icon: '🔒', label: 'Consent Gates', badge: 0 },
          ].map(n => (
            <button key={n.id} onClick={() => setActiveNav(n.id)} style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 10,
              border: activeNav === n.id ? `1px solid rgba(59,130,246,0.3)` : '1px solid transparent',
              background: activeNav === n.id ? C.glowBlue : 'transparent',
              color: activeNav === n.id ? C.blue : C.txtSec,
              fontSize: 14, fontWeight: 500, cursor: 'pointer', width: '100%', textAlign: 'left',
            }}>
              <span style={{ fontSize: 16 }}>{n.icon}</span> {n.label}
              {(n.badge ?? 0) > 0 && <span style={{
                marginLeft: 'auto', background: C.amber, color: C.bg0, fontSize: 11,
                fontWeight: 700, padding: '1px 8px', borderRadius: 10,
              }}>{n.badge}</span>}
            </button>
          ))}

          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1.5, color: C.txtMut, padding: '0 12px', marginTop: 16, marginBottom: 8 }}>Configuration</div>
          {[
            { id: 'roles', icon: '👤', label: 'Job Roles' },
            { id: 'memory', icon: '🧠', label: 'Memory' },
            { id: 'settings', icon: '⚙', label: 'Settings', href: '/settings' },
          ].map(n => (
            n.href ? (
              <Link key={n.id} href={n.href} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 10,
                border: '1px solid transparent', background: 'transparent',
                color: C.txtSec, fontSize: 14, fontWeight: 500, textDecoration: 'none',
              }}><span style={{ fontSize: 16 }}>{n.icon}</span> {n.label}</Link>
            ) : (
              <button key={n.id} onClick={() => setActiveNav(n.id)} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 10,
                border: activeNav === n.id ? `1px solid rgba(59,130,246,0.3)` : '1px solid transparent',
                background: activeNav === n.id ? C.glowBlue : 'transparent',
                color: activeNav === n.id ? C.blue : C.txtSec,
                fontSize: 14, fontWeight: 500, cursor: 'pointer', width: '100%', textAlign: 'left',
              }}><span style={{ fontSize: 16 }}>{n.icon}</span> {n.label}</button>
            )
          ))}
        </nav>

        {/* ── MAIN CONTENT ────────────────────────────────── */}
        <main style={{ padding: 24, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 20 }}>

          {error && (
            <div style={{ padding: '14px 18px', background: 'rgba(239,68,68,0.1)', border: `1px solid rgba(239,68,68,0.3)`, borderRadius: 12, color: C.red, fontSize: 13 }}>
              {error}
            </div>
          )}

          {/* Stats Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16 }}>
            {[
              { label: 'Sessions Total', value: String(sessions.length), change: `${completed.length} completed` },
              { label: 'Available Roles', value: String(roles.length), change: `${roles.filter(r => r.source === 'starter').length} starter templates` },
              { label: 'Setup Status', value: setupChecks.every(c => c.status === 'ok') ? 'Ready' : 'Check', change: `${setupChecks.filter(c => c.status === 'ok').length}/${setupChecks.length} checks passed` },
            ].map((s, i) => (
              <div key={i} style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 12, padding: 20 }}>
                <div style={{ fontSize: 12, color: C.txtMut, marginBottom: 8 }}>{s.label}</div>
                <div style={{ fontSize: 28, fontWeight: 700, fontFamily: 'monospace' }}>{s.value}</div>
                <div style={{ fontSize: 12, color: C.green, marginTop: 8 }}>{s.change}</div>
              </div>
            ))}
          </div>

          {/* Status Hero Card */}
          <div style={{
            background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, padding: 28,
            display: 'grid', gridTemplateColumns: '1fr auto', gap: 24, position: 'relative', overflow: 'hidden',
          }}>
            <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: `linear-gradient(90deg, ${C.green}, ${C.blue})` }} />
            <div>
              <h2 style={{ fontSize: 14, color: C.txtMut, fontWeight: 500, marginBottom: 8 }}>
                {isWorking ? 'Currently Working On' : 'Status'}
              </h2>
              <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 16, lineHeight: 1.3 }}>
                {currentTask ? currentTask.goal : statusMsg}
              </div>
              <div style={{ display: 'flex', gap: 20 }}>
                {currentTask && (
                  <>
                    <span style={{ fontSize: 13, color: C.txtSec }}>Role: {currentTask.role}</span>
                    <span style={{ fontSize: 13, color: C.txtSec }}>ID: {currentTask.session_id?.slice(0, 8)}</span>
                    {currentTask.cost_usd != null && <span style={{ fontSize: 13, color: C.txtSec }}>${currentTask.cost_usd.toFixed(2)}</span>}
                  </>
                )}
                {!currentTask && !error && <span style={{ fontSize: 13, color: C.txtSec }}>Start a session with /work &lt;role&gt; &lt;goal&gt;</span>}
              </div>
              {isWorking && (
                <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                  <button onClick={() => handleSessionAction('pause')} style={{ padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.glowAmber, color: C.amber, border: `1px solid rgba(245,158,11,0.3)` }}>Pause</button>
                  <button onClick={() => handleSessionAction('cancel')} style={{ padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: 'rgba(239,68,68,0.1)', color: C.red, border: `1px solid rgba(239,68,68,0.3)` }}>Cancel</button>
                </div>
              )}
              {paused.length > 0 && !isWorking && (
                <button onClick={() => handleSessionAction('resume')} style={{ marginTop: 16, padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.glowGreen, color: C.green, border: `1px solid rgba(34,197,94,0.3)` }}>Resume</button>
              )}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
              <div style={{ width: 100, height: 100, position: 'relative' }}>
                <svg width="100" height="100" style={{ transform: 'rotate(-90deg)' }}>
                  <circle cx="50" cy="50" r="42" fill="none" strokeWidth="8" stroke={C.bg2} />
                  <circle cx="50" cy="50" r="42" fill="none" strokeWidth="8" stroke={C.green}
                    strokeLinecap="round" strokeDasharray="264" strokeDashoffset={dashOffset}
                    style={{ transition: 'stroke-dashoffset 0.5s ease' }} />
                </svg>
                <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', fontFamily: 'monospace', fontSize: 20, fontWeight: 600 }}>
                  {progress}%
                </div>
              </div>
              <div style={{ fontSize: 12, color: C.txtMut }}>Task Progress</div>
            </div>
          </div>

          {/* Task Queue */}
          <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, overflow: 'hidden' }}>
            <div style={{ display: 'flex', padding: '0 24px', borderBottom: `1px solid ${C.border}` }}>
              {[
                { id: 'in_progress', label: 'Running', count: running.length },
                { id: 'paused', label: 'Paused', count: paused.length },
                { id: 'completed', label: 'Completed', count: completed.length },
                { id: 'failed', label: 'Failed', count: failed.length },
              ].map(t => (
                <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
                  padding: '14px 0', marginRight: 24, fontSize: 14, cursor: 'pointer',
                  background: 'none', border: 'none',
                  color: activeTab === t.id ? C.txt : C.txtMut,
                  borderBottom: activeTab === t.id ? `2px solid ${C.blue}` : '2px solid transparent',
                }}>
                  {t.label} <span style={{ background: C.bg2, padding: '2px 8px', borderRadius: 8, fontSize: 12, marginLeft: 6 }}>{t.count}</span>
                </button>
              ))}
            </div>
            <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {(tabSessions[activeTab] || []).length === 0 ? (
                <div style={{ padding: 20, textAlign: 'center', color: C.txtMut, fontSize: 13 }}>
                  No {activeTab.replace('_', ' ')} sessions
                </div>
              ) : (tabSessions[activeTab] || []).map((s, i) => (
                <div key={i} style={{
                  background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 12, padding: 16,
                  cursor: 'pointer', transition: 'all 0.2s ease',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.4, flex: 1 }}>
                      {s.goal || 'Untitled session'}
                    </div>
                    <span style={{
                      fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5,
                      padding: '4px 8px', borderRadius: 6, marginLeft: 12, flexShrink: 0,
                      background: s.status === 'running' ? 'rgba(34,197,94,0.15)' : s.status === 'failed' ? 'rgba(239,68,68,0.15)' : C.glowAmber,
                      color: s.status === 'running' ? C.green : s.status === 'failed' ? C.red : C.amber,
                    }}>{s.status}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 12, color: C.txtMut }}>
                    <span>{s.role}</span>
                    <span>{s.session_id?.slice(0, 8)}</span>
                    {s.progress != null && (
                      <>
                        <div style={{ flex: 1, height: 4, background: C.bg3, borderRadius: 2, overflow: 'hidden' }}>
                          <div style={{ height: '100%', background: C.blue, borderRadius: 2, width: `${s.progress}%`, transition: 'width 0.3s ease' }} />
                        </div>
                        <span>{s.progress}%</span>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Roles Table */}
          <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, overflow: 'hidden' }}>
            <div style={{ padding: '18px 24px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>Available Roles</div>
              <span style={{ fontSize: 13, color: C.blue, cursor: 'pointer' }}>{roles.length} roles</span>
            </div>
            <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {roles.map((r, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '12px 16px', background: C.bg2, borderRadius: 10, border: `1px solid ${C.borderSub}`,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center',
                      background: r.source === 'starter' ? C.glowBlue : C.glowGreen,
                      color: r.source === 'starter' ? C.blue : C.green, fontSize: 14,
                    }}>
                      {r.name.charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 500 }}>{r.name}</div>
                      <div style={{ fontSize: 12, color: C.txtMut }}>{r.scope} &middot; {r.auth_method}{r.source === 'starter' ? ' &middot; starter' : ''}</div>
                    </div>
                  </div>
                  <span style={{
                    fontSize: 11, padding: '3px 10px', borderRadius: 6,
                    background: r.source === 'starter' ? C.glowBlue : 'rgba(34,197,94,0.1)',
                    color: r.source === 'starter' ? C.blue : C.green,
                  }}>{r.source}</span>
                </div>
              ))}
              {roles.length === 0 && (
                <div style={{ padding: 20, textAlign: 'center', color: C.txtMut, fontSize: 13 }}>
                  No roles found. Run <code style={{ color: C.blue }}>/role example</code> to get started.
                </div>
              )}
            </div>
          </div>
        </main>

        {/* ── RIGHT PANEL ─────────────────────────────────── */}
        <aside style={{ background: C.bg1, borderLeft: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column' }}>

          {/* Setup Checks / Consent Gates */}
          <div style={{ padding: 20, borderBottom: `1px solid ${C.border}` }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <span style={{
                background: setupChecks.every(c => c.status === 'ok') ? C.green : C.amber,
                color: C.bg0, fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 12,
              }}>{setupChecks.length}</span>
              <span style={{ fontSize: 14, fontWeight: 600 }}>Setup Checks</span>
            </div>
            {setupChecks.map((c, i) => (
              <div key={i} style={{
                background: c.status === 'ok' ? 'rgba(34,197,94,0.06)' : 'rgba(245,158,11,0.08)',
                border: `1px solid ${c.status === 'ok' ? 'rgba(34,197,94,0.2)' : 'rgba(245,158,11,0.2)'}`,
                borderRadius: 12, padding: 14, marginBottom: 10,
              }}>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ color: c.status === 'ok' ? C.green : C.amber }}>
                    {c.status === 'ok' ? '✓' : c.status === 'not_configured' ? '!' : '✗'}
                  </span>
                  {c.name}
                </div>
                <div style={{ fontSize: 13, color: C.txtSec, lineHeight: 1.5 }}>{c.message}</div>
              </div>
            ))}
          </div>

          {/* Chat Panel */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ padding: '16px 20px', borderBottom: `1px solid ${C.border}` }}>
              <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>Talk to Orion</div>
              <div style={{ fontSize: 12, color: C.txtMut }}>Ask questions or give instructions</div>
            </div>
            <div style={{ flex: 1, padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
              {chatMessages.map((m, i) => (
                <div key={i} style={{
                  maxWidth: '90%', padding: '10px 14px', borderRadius: 12, fontSize: 14, lineHeight: 1.5,
                  alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
                  background: m.role === 'user' ? C.blue : C.bg2,
                  borderBottomRightRadius: m.role === 'user' ? 4 : 12,
                  borderBottomLeftRadius: m.role === 'ai' ? 4 : 12,
                }}>{m.text}</div>
              ))}
            </div>
            <div style={{ padding: '12px 16px', borderTop: `1px solid ${C.border}` }}>
              <textarea
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey && chatInput.trim()) {
                    e.preventDefault()
                    setChatMessages(prev => [...prev, { role: 'user', text: chatInput.trim() }])
                    setChatInput('')
                    // Send to API chat endpoint
                    fetch(`${API}/api/chat`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ message: chatInput.trim() }),
                    }).then(r => r.ok ? r.json() : null)
                      .then(d => { if (d?.reply) setChatMessages(prev => [...prev, { role: 'ai', text: d.reply }]) })
                      .catch(() => setChatMessages(prev => [...prev, { role: 'ai', text: 'Could not reach the API server.' }]))
                  }
                }}
                placeholder="Ask Orion something..."
                rows={2}
                style={{
                  width: '100%', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 12,
                  padding: '12px 14px', color: C.txt, fontSize: 14, fontFamily: 'inherit', resize: 'none',
                }}
              />
            </div>
          </div>
        </aside>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  )
}
