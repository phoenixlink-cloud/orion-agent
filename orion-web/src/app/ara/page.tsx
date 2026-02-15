'use client'

import React, { useEffect, useState, useCallback, useRef } from 'react'
import Link from 'next/link'

/* ── types ─────────────────────────────────────────────────────── */
interface SetupCheck { name: string; status: string; message: string }
interface RoleInfo { name: string; scope: string; auth_method: string; source: string; description?: string }
interface SessionInfo { session_id: string; role: string; goal: string; status: string; cost_usd?: number; elapsed_seconds?: number; progress?: number; created_at?: string }
interface ActivityItem { icon: 'code' | 'search' | 'write' | 'check'; title: string; desc: string; time: string }
interface DashSection { title: string; content: string; style: string }
interface ARASettingsData { [key: string]: any }

/* ── color palette (matches prototype) ─────────────────────────── */
const C = {
  bg0: '#0a0a0f', bg1: '#12121a', bg2: '#1a1a24', bg3: '#22222e',
  border: '#2a2a3a', borderSub: '#1e1e2a',
  txt: '#f0f0f5', txtSec: '#8888a0', txtMut: '#5a5a70',
  blue: '#3b82f6', green: '#22c55e', amber: '#f59e0b', red: '#ef4444', purple: '#a855f7',
  glowBlue: 'rgba(59,130,246,0.15)', glowGreen: 'rgba(34,197,94,0.15)', glowAmber: 'rgba(245,158,11,0.15)',
}

/* ── helpers ───────────────────────────────────────────────────── */
function fmtElapsed(sec: number): string {
  const h = Math.floor(sec / 3600); const m = Math.floor((sec % 3600) / 60); const s = sec % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

/* ── main page ─────────────────────────────────────────────────── */
export default function ARAPage() {
  /* state */
  const [setupChecks, setSetupChecks] = useState<SetupCheck[]>([])
  const [roles, setRoles] = useState<RoleInfo[]>([])
  const [sessions, setSessions] = useState<SessionInfo[]>([])
  const [statusMsg, setStatusMsg] = useState('No active session')
  const [statusData, setStatusData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeNav, setActiveNav] = useState('dashboard')
  const [activeTab, setActiveTab] = useState('in_progress')
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [activities, setActivities] = useState<ActivityItem[]>([])
  const [dashSections, setDashSections] = useState<DashSection[]>([])
  const [pendingCount, setPendingCount] = useState(0)

  // Role CRUD
  const [showCreateRole, setShowCreateRole] = useState(false)
  const [newRole, setNewRole] = useState({ name: '', scope: 'coding', auth_method: 'pin', description: '' })
  const [roleError, setRoleError] = useState('')
  const [selectedRole, setSelectedRole] = useState<RoleInfo | null>(null)

  // ARA Settings
  const [araSettings, setAraSettings] = useState<ARASettingsData>({})
  const [araSaving, setAraSaving] = useState(false)
  const [araSaveMsg, setAraSaveMsg] = useState('')

  // Chat
  const [chatMessages, setChatMessages] = useState<{role: string; text: string}[]>([
    { role: 'ai', text: "Welcome to the ARA Dashboard. I'm monitoring your autonomous sessions. Use /work <role> <goal> in the CLI to start a session, or browse the panels here." },
  ])
  const [chatInput, setChatInput] = useState('')

  // Timer
  const [elapsed, setElapsed] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

  /* ── data loading ──────────────────────────────────────────── */
  const loadData = useCallback(async () => {
    setRefreshing(true)
    try {
      const [setupR, rolesR, sessR, statusR, dashR, settingsR] = await Promise.allSettled([
        fetch(`${API}/api/ara/setup`),
        fetch(`${API}/api/ara/roles`),
        fetch(`${API}/api/ara/sessions`),
        fetch(`${API}/api/ara/status`),
        fetch(`${API}/api/ara/dashboard`),
        fetch(`${API}/api/settings`),
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
      if (dashR.status === 'fulfilled' && dashR.value.ok) {
        const d = await dashR.value.json()
        setDashSections(d.data?.sections || [])
        setPendingCount(d.data?.pending_count || 0)
      }
      if (settingsR.status === 'fulfilled' && settingsR.value.ok) {
        const d = await settingsR.value.json()
        const s = d.settings || d
        setAraSettings({
          ara_enabled: s.ara_enabled ?? true,
          ara_default_auth: s.ara_default_auth ?? 'pin',
          ara_max_cost_usd: s.ara_max_cost_usd ?? 5,
          ara_max_session_hours: s.ara_max_session_hours ?? 8,
          ara_sandbox_mode: s.ara_sandbox_mode ?? 'branch',
          ara_prompt_guard: s.ara_prompt_guard ?? true,
          ara_audit_log: s.ara_audit_log ?? true,
        })
      }
      setError(null)
      setLastRefresh(new Date())
    } catch { setError('Could not connect to Orion API. Is the server running on port 8001?') }
    setRefreshing(false)
  }, [API])

  useEffect(() => { loadData(); const t = setInterval(loadData, 10000); return () => clearInterval(t) }, [loadData])

  // Build activities from sessions
  useEffect(() => {
    const acts: ActivityItem[] = []
    sessions.forEach(s => {
      if (s.status === 'running') acts.push({ icon: 'code', title: `Working: ${s.goal?.slice(0, 50)}`, desc: `Role: ${s.role} · Session ${s.session_id?.slice(0, 8)}`, time: 'Active' })
      else if (s.status === 'completed') acts.push({ icon: 'check', title: `Completed: ${s.goal?.slice(0, 50)}`, desc: `Role: ${s.role}`, time: 'Done' })
      else if (s.status === 'paused') acts.push({ icon: 'search', title: `Paused: ${s.goal?.slice(0, 50)}`, desc: `Role: ${s.role}`, time: 'Paused' })
      else if (s.status === 'failed' || s.status === 'cancelled') acts.push({ icon: 'write', title: `${s.status}: ${s.goal?.slice(0, 50)}`, desc: `Role: ${s.role}`, time: s.status })
    })
    setActivities(acts)
  }, [sessions])

  // Elapsed timer for running session
  const running = sessions.filter(s => s.status === 'running')
  const paused = sessions.filter(s => s.status === 'paused')
  const completed = sessions.filter(s => s.status === 'completed')
  const failed = sessions.filter(s => s.status === 'failed' || s.status === 'cancelled')
  const currentTask = running[0]
  const progress = currentTask?.progress ?? 0
  const isWorking = running.length > 0

  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    if (isWorking && currentTask?.elapsed_seconds != null) {
      setElapsed(currentTask.elapsed_seconds)
      timerRef.current = setInterval(() => setElapsed(p => p + 1), 1000)
    } else if (isWorking) {
      setElapsed(0)
      timerRef.current = setInterval(() => setElapsed(p => p + 1), 1000)
    } else { setElapsed(0) }
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [isWorking, currentTask?.elapsed_seconds, currentTask?.session_id])

  const tabSessions: Record<string, SessionInfo[]> = { in_progress: running, paused, completed, failed }

  /* ── actions ───────────────────────────────────────────────── */
  const handleSessionAction = async (action: string) => {
    try { await fetch(`${API}/api/ara/${action}`, { method: 'POST' }); setTimeout(loadData, 300) } catch {}
  }

  const handleCreateRole = async () => {
    setRoleError('')
    if (!newRole.name.trim()) { setRoleError('Role name is required'); return }
    try {
      const res = await fetch(`${API}/api/ara/roles`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newRole),
      })
      if (!res.ok) { const e = await res.json(); setRoleError(e.detail || 'Failed'); return }
      setNewRole({ name: '', scope: 'coding', auth_method: 'pin', description: '' })
      setShowCreateRole(false)
      loadData()
    } catch { setRoleError('API unavailable') }
  }

  const handleDeleteRole = async (name: string) => {
    if (!confirm(`Delete role "${name}"?`)) return
    try {
      const res = await fetch(`${API}/api/ara/roles/${encodeURIComponent(name)}`, { method: 'DELETE' })
      if (!res.ok) { const e = await res.json(); alert(e.detail || 'Failed'); return }
      setSelectedRole(null)
      loadData()
    } catch { alert('API unavailable') }
  }

  const handleSaveAraSettings = async () => {
    setAraSaving(true); setAraSaveMsg('')
    try {
      const res = await fetch(`${API}/api/settings`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(araSettings),
      })
      if (res.ok) { setAraSaveMsg('Saved!'); setTimeout(() => setAraSaveMsg(''), 3000) }
      else setAraSaveMsg('Save failed')
    } catch { setAraSaveMsg('API unavailable') }
    setAraSaving(false)
  }

  const handleReview = async (sid?: string) => {
    try {
      const params = sid ? `?session_id=${encodeURIComponent(sid)}` : ''
      await fetch(`${API}/api/ara/review${params}`, { method: 'POST' })
      loadData()
    } catch {}
  }

  const dashOffset = 264 - (264 * progress / 100)

  const actIcon = (t: string) => t === 'code' ? '< >' : t === 'search' ? '🔍' : t === 'check' ? '✓' : '📝'
  const actColor = (t: string) => t === 'code' ? C.glowBlue : t === 'search' ? C.glowAmber : t === 'check' ? C.glowGreen : C.glowGreen
  const actTextColor = (t: string) => t === 'code' ? C.blue : t === 'search' ? C.amber : t === 'check' ? C.green : C.green

  /* ── nav button helper ─────────────────────────────────────── */
  const NavBtn = ({ id, icon, label, badge, href }: { id: string; icon: string; label: string; badge?: number; href?: string }) => {
    if (href) return (
      <Link href={href} style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 10,
        border: '1px solid transparent', background: 'transparent',
        color: C.txtSec, fontSize: 14, fontWeight: 500, textDecoration: 'none',
      }}><span style={{ fontSize: 16, width: 20, textAlign: 'center' }}>{icon}</span> {label}</Link>
    )
    return (
      <button onClick={() => setActiveNav(id)} style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', borderRadius: 10,
        border: activeNav === id ? '1px solid rgba(59,130,246,0.3)' : '1px solid transparent',
        background: activeNav === id ? C.glowBlue : 'transparent',
        color: activeNav === id ? C.blue : C.txtSec,
        fontSize: 14, fontWeight: 500, cursor: 'pointer', width: '100%', textAlign: 'left',
      }}>
        <span style={{ fontSize: 16, width: 20, textAlign: 'center' }}>{icon}</span> {label}
        {(badge ?? 0) > 0 && <span style={{ marginLeft: 'auto', background: C.amber, color: C.bg0, fontSize: 11, fontWeight: 700, padding: '1px 8px', borderRadius: 10 }}>{badge}</span>}
      </button>
    )
  }

  /* ── render ─────────────────────────────────────────────────── */
  return (
    <div style={{ fontFamily: "'Plus Jakarta Sans','Inter',system-ui,sans-serif", background: C.bg0, color: C.txt, minHeight: '100vh' }}>
      <div style={{ position: 'fixed', inset: 0, zIndex: 0, opacity: 0.25, pointerEvents: 'none', backgroundImage: `linear-gradient(${C.borderSub} 1px, transparent 1px), linear-gradient(90deg, ${C.borderSub} 1px, transparent 1px)`, backgroundSize: '40px 40px' }} />

      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr 340px', gridTemplateRows: '64px 1fr', minHeight: '100vh', position: 'relative', zIndex: 1 }}>

        {/* ── HEADER ─────────────────────────────────────── */}
        <header style={{ gridColumn: '1 / -1', background: C.bg1, borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', background: `linear-gradient(135deg, ${C.blue}, ${C.purple})`, fontWeight: 700, fontSize: 16, boxShadow: `0 0 20px ${C.glowBlue}` }}>O</div>
            <div style={{ fontWeight: 700, fontSize: 18, letterSpacing: -0.5 }}>Orion <span style={{ color: C.txtMut, fontWeight: 400 }}>Agent</span></div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: C.bg2, padding: '6px 14px', borderRadius: 20, fontSize: 13, fontFamily: 'monospace' }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: isWorking ? C.green : C.txtMut, boxShadow: isWorking ? `0 0 8px ${C.green}` : 'none', animation: isWorking ? 'pulse 2s ease-in-out infinite' : 'none' }} />
              {isWorking ? 'WORKING' : 'IDLE'}
            </div>
            {isWorking && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: C.bg2, padding: '6px 14px', borderRadius: 20, fontSize: 13, fontFamily: 'monospace' }}>
                <span style={{ fontSize: 14 }}>⏱</span> {fmtElapsed(elapsed)}
              </div>
            )}
            <button onClick={() => loadData()} style={{ background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, padding: '6px 12px', color: refreshing ? C.txtMut : C.blue, cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
              {refreshing ? '...' : '↻ Refresh'}
            </button>
            {lastRefresh && <span style={{ fontSize: 11, color: C.txtMut, fontFamily: 'monospace' }}>Updated {lastRefresh.toLocaleTimeString()}</span>}
            <div style={{ width: 36, height: 36, background: C.bg2, borderRadius: '50%', border: `2px solid ${C.border}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 600, fontSize: 14, color: C.txtSec }}>JA</div>
            <Link href="/" style={{ fontSize: 13, color: C.blue, textDecoration: 'none' }}>← Back</Link>
          </div>
        </header>

        {/* ── SIDEBAR ────────────────────────────────────── */}
        <nav style={{ background: C.bg1, borderRight: `1px solid ${C.border}`, padding: '20px 14px', display: 'flex', flexDirection: 'column', gap: 4, overflowY: 'auto' }}>
          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1.5, color: C.txtMut, padding: '0 12px', marginBottom: 8 }}>Overview</div>
          <NavBtn id="dashboard" icon="◫" label="Dashboard" />
          <NavBtn id="activity" icon="⚡" label="Activity" />

          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1.5, color: C.txtMut, padding: '0 12px', marginTop: 16, marginBottom: 8 }}>Work</div>
          <NavBtn id="tasks" icon="☑" label="Tasks" badge={running.length + paused.length} />
          <NavBtn id="deliverables" icon="📄" label="Deliverables" />
          <NavBtn id="consent" icon="🔒" label="Consent Gates" badge={pendingCount} />

          <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1.5, color: C.txtMut, padding: '0 12px', marginTop: 16, marginBottom: 8 }}>Configuration</div>
          <NavBtn id="roles" icon="👤" label="Job Roles" />
          <NavBtn id="memory" icon="🧠" label="Memory" />
          <NavBtn id="ara-settings" icon="⚙" label="ARA Settings" />
          <NavBtn id="settings" icon="🔧" label="All Settings" href="/settings" />
        </nav>

        {/* ── MAIN CONTENT ───────────────────────────────── */}
        <main style={{ padding: 24, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
          {error && <div style={{ padding: '14px 18px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 12, color: C.red, fontSize: 13 }}>{error}</div>}

          {/* ═══ DASHBOARD VIEW ═══ */}
          {activeNav === 'dashboard' && (<>
            {/* Stats Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16 }}>
              {[
                { label: 'Sessions Total', value: String(sessions.length), change: `${completed.length} completed` },
                { label: 'Available Roles', value: String(roles.length), change: `${roles.filter(r => r.source === 'starter').length} starter templates` },
                { label: 'Setup Status', value: setupChecks.length > 0 && setupChecks.every(c => c.status === 'ok') ? 'Ready' : 'Check', change: `${setupChecks.filter(c => c.status === 'ok').length}/${setupChecks.length} checks passed` },
              ].map((s, i) => (
                <div key={i} style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 12, padding: 20, animation: 'fadeIn 0.5s ease forwards' }}>
                  <div style={{ fontSize: 12, color: C.txtMut, marginBottom: 8 }}>{s.label}</div>
                  <div style={{ fontSize: 28, fontWeight: 700, fontFamily: 'monospace' }}>{s.value}</div>
                  <div style={{ fontSize: 12, color: C.green, marginTop: 8 }}>{s.change}</div>
                </div>
              ))}
            </div>

            {/* Status Hero */}
            <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, padding: 28, display: 'grid', gridTemplateColumns: '1fr auto', gap: 24, position: 'relative', overflow: 'hidden' }}>
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 3, background: `linear-gradient(90deg, ${C.green}, ${C.blue})` }} />
              <div>
                <h2 style={{ fontSize: 14, color: C.txtMut, fontWeight: 500, marginBottom: 8 }}>{isWorking ? 'Currently Working On' : 'Status'}</h2>
                <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 16, lineHeight: 1.3 }}>{currentTask ? currentTask.goal : statusMsg}</div>
                <div style={{ display: 'flex', gap: 20 }}>
                  {currentTask && (<>
                    <span style={{ fontSize: 13, color: C.txtSec }}>Role: {currentTask.role}</span>
                    <span style={{ fontSize: 13, color: C.txtSec }}>ID: {currentTask.session_id?.slice(0, 8)}</span>
                    {currentTask.cost_usd != null && <span style={{ fontSize: 13, color: C.txtSec }}>${currentTask.cost_usd.toFixed(2)}</span>}
                    <span style={{ fontSize: 13, color: C.txtSec }}>Elapsed: {fmtElapsed(elapsed)}</span>
                  </>)}
                  {!currentTask && !error && <span style={{ fontSize: 13, color: C.txtSec }}>Start a session with /work &lt;role&gt; &lt;goal&gt;</span>}
                </div>
                {isWorking && (
                  <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                    <button onClick={() => handleSessionAction('pause')} style={{ padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.glowAmber, color: C.amber, border: '1px solid rgba(245,158,11,0.3)' }}>Pause</button>
                    <button onClick={() => handleSessionAction('cancel')} style={{ padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: 'rgba(239,68,68,0.1)', color: C.red, border: '1px solid rgba(239,68,68,0.3)' }}>Cancel</button>
                  </div>
                )}
                {paused.length > 0 && !isWorking && (
                  <button onClick={() => handleSessionAction('resume')} style={{ marginTop: 16, padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.glowGreen, color: C.green, border: '1px solid rgba(34,197,94,0.3)' }}>Resume</button>
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 10 }}>
                <div style={{ width: 100, height: 100, position: 'relative' }}>
                  <svg width="100" height="100" style={{ transform: 'rotate(-90deg)' }}>
                    <circle cx="50" cy="50" r="42" fill="none" strokeWidth="8" stroke={C.bg2} />
                    <circle cx="50" cy="50" r="42" fill="none" strokeWidth="8" stroke={C.green} strokeLinecap="round" strokeDasharray="264" strokeDashoffset={dashOffset} style={{ transition: 'stroke-dashoffset 0.5s ease' }} />
                  </svg>
                  <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', fontFamily: 'monospace', fontSize: 20, fontWeight: 600 }}>{progress}%</div>
                </div>
                <div style={{ fontSize: 12, color: C.txtMut }}>Task Progress</div>
              </div>
            </div>

            {/* Activity Feed */}
            <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, overflow: 'hidden' }}>
              <div style={{ padding: '20px 24px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ fontSize: 16, fontWeight: 600 }}>Real-time Activity</div>
                <span onClick={() => setActiveNav('activity')} style={{ fontSize: 13, color: C.blue, cursor: 'pointer' }}>View All</span>
              </div>
              <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                {activities.length === 0 && <div style={{ padding: 20, textAlign: 'center', color: C.txtMut, fontSize: 13 }}>No activity yet. Start a /work session to see live updates.</div>}
                {activities.slice(0, 5).map((a, i) => (
                  <div key={i} style={{ padding: '16px 24px', borderBottom: `1px solid ${C.borderSub}`, display: 'flex', gap: 16, alignItems: 'center' }}>
                    <div style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, background: actColor(a.icon), color: actTextColor(a.icon), fontSize: 14 }}>{actIcon(a.icon)}</div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>{a.title}</div>
                      <div style={{ fontSize: 13, color: C.txtMut, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.desc}</div>
                    </div>
                    <div style={{ fontSize: 12, color: C.txtMut, fontFamily: 'monospace', flexShrink: 0 }}>{a.time}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Task Queue */}
            <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, overflow: 'hidden' }}>
              <div style={{ display: 'flex', padding: '0 24px', borderBottom: `1px solid ${C.border}` }}>
                {[{ id: 'in_progress', label: 'Running', count: running.length }, { id: 'paused', label: 'Paused', count: paused.length }, { id: 'completed', label: 'Completed', count: completed.length }, { id: 'failed', label: 'Failed', count: failed.length }].map(t => (
                  <button key={t.id} onClick={() => setActiveTab(t.id)} style={{ padding: '14px 0', marginRight: 24, fontSize: 14, cursor: 'pointer', background: 'none', border: 'none', color: activeTab === t.id ? C.txt : C.txtMut, borderBottom: activeTab === t.id ? `2px solid ${C.blue}` : '2px solid transparent' }}>
                    {t.label} <span style={{ background: C.bg2, padding: '2px 8px', borderRadius: 8, fontSize: 12, marginLeft: 6 }}>{t.count}</span>
                  </button>
                ))}
              </div>
              <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {(tabSessions[activeTab] || []).length === 0 ? (
                  <div style={{ padding: 20, textAlign: 'center', color: C.txtMut, fontSize: 13 }}>No {activeTab.replace('_', ' ')} sessions</div>
                ) : (tabSessions[activeTab] || []).map((s, i) => (
                  <div key={i} style={{ background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 12, padding: 16, cursor: 'pointer', transition: 'all 0.2s ease' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.4, flex: 1 }}>{s.goal || 'Untitled session'}</div>
                      <span style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, padding: '4px 8px', borderRadius: 6, marginLeft: 12, flexShrink: 0, background: s.status === 'running' ? 'rgba(34,197,94,0.15)' : s.status === 'failed' ? 'rgba(239,68,68,0.15)' : s.status === 'completed' ? 'rgba(34,197,94,0.1)' : C.glowAmber, color: s.status === 'running' ? C.green : s.status === 'failed' ? C.red : s.status === 'completed' ? C.green : C.amber }}>{s.status}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 12, color: C.txtMut }}>
                      <span>{s.role}</span><span>{s.session_id?.slice(0, 8)}</span>
                      {s.progress != null && (<><div style={{ flex: 1, height: 4, background: C.bg3, borderRadius: 2, overflow: 'hidden' }}><div style={{ height: '100%', background: C.blue, borderRadius: 2, width: `${s.progress}%`, transition: 'width 0.3s ease' }} /></div><span>{s.progress}%</span></>)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>)}

          {/* ═══ ACTIVITY VIEW ═══ */}
          {activeNav === 'activity' && (
            <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, overflow: 'hidden' }}>
              <div style={{ padding: '20px 24px', borderBottom: `1px solid ${C.border}` }}>
                <div style={{ fontSize: 16, fontWeight: 600 }}>All Activity</div>
              </div>
              {activities.length === 0 && <div style={{ padding: 30, textAlign: 'center', color: C.txtMut }}>No activity recorded yet.</div>}
              {activities.map((a, i) => (
                <div key={i} style={{ padding: '16px 24px', borderBottom: `1px solid ${C.borderSub}`, display: 'flex', gap: 16, alignItems: 'center' }}>
                  <div style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, background: actColor(a.icon), color: actTextColor(a.icon), fontSize: 14 }}>{actIcon(a.icon)}</div>
                  <div style={{ flex: 1 }}><div style={{ fontSize: 14, fontWeight: 500, marginBottom: 4 }}>{a.title}</div><div style={{ fontSize: 13, color: C.txtMut }}>{a.desc}</div></div>
                  <div style={{ fontSize: 12, color: C.txtMut, fontFamily: 'monospace', flexShrink: 0 }}>{a.time}</div>
                </div>
              ))}
            </div>
          )}

          {/* ═══ TASKS VIEW ═══ */}
          {activeNav === 'tasks' && (<>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Task Management</div>
            <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, overflow: 'hidden' }}>
              <div style={{ display: 'flex', padding: '0 24px', borderBottom: `1px solid ${C.border}` }}>
                {[{ id: 'in_progress', label: 'Running', count: running.length }, { id: 'paused', label: 'Paused', count: paused.length }, { id: 'completed', label: 'Completed', count: completed.length }, { id: 'failed', label: 'Failed', count: failed.length }].map(t => (
                  <button key={t.id} onClick={() => setActiveTab(t.id)} style={{ padding: '14px 0', marginRight: 24, fontSize: 14, cursor: 'pointer', background: 'none', border: 'none', color: activeTab === t.id ? C.txt : C.txtMut, borderBottom: activeTab === t.id ? `2px solid ${C.blue}` : '2px solid transparent' }}>
                    {t.label} <span style={{ background: C.bg2, padding: '2px 8px', borderRadius: 8, fontSize: 12, marginLeft: 6 }}>{t.count}</span>
                  </button>
                ))}
              </div>
              <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {(tabSessions[activeTab] || []).length === 0 ? (
                  <div style={{ padding: 30, textAlign: 'center', color: C.txtMut }}>No {activeTab.replace('_', ' ')} sessions</div>
                ) : (tabSessions[activeTab] || []).map((s, i) => (
                  <div key={i} style={{ background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 12, padding: 16 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, flex: 1 }}>{s.goal || 'Untitled'}</div>
                      <span style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', padding: '4px 8px', borderRadius: 6, background: s.status === 'running' ? 'rgba(34,197,94,0.15)' : s.status === 'failed' ? 'rgba(239,68,68,0.15)' : C.glowAmber, color: s.status === 'running' ? C.green : s.status === 'failed' ? C.red : C.amber }}>{s.status}</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 12, color: C.txtMut, marginBottom: 10 }}>
                      <span>Role: {s.role}</span><span>ID: {s.session_id?.slice(0, 8)}</span>
                      {s.progress != null && <span>Progress: {s.progress}%</span>}
                      {s.cost_usd != null && <span>Cost: ${s.cost_usd.toFixed(2)}</span>}
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      {s.status === 'running' && <><button onClick={() => handleSessionAction('pause')} style={{ padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: C.glowAmber, color: C.amber, border: '1px solid rgba(245,158,11,0.3)' }}>Pause</button><button onClick={() => handleSessionAction('cancel')} style={{ padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: 'rgba(239,68,68,0.1)', color: C.red, border: '1px solid rgba(239,68,68,0.3)' }}>Cancel</button></>}
                      {s.status === 'paused' && <button onClick={() => handleSessionAction('resume')} style={{ padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: C.glowGreen, color: C.green, border: '1px solid rgba(34,197,94,0.3)' }}>Resume</button>}
                      {s.status === 'completed' && <button onClick={() => handleReview(s.session_id)} style={{ padding: '6px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: C.glowBlue, color: C.blue, border: '1px solid rgba(59,130,246,0.3)' }}>Review & Promote</button>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>)}

          {/* ═══ DELIVERABLES VIEW ═══ */}
          {activeNav === 'deliverables' && (
            <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, padding: 30, textAlign: 'center' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>📄</div>
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Deliverables</div>
              <div style={{ color: C.txtMut, fontSize: 14 }}>Session deliverables (code, docs, commits) will appear here after sessions are completed and reviewed.</div>
            </div>
          )}

          {/* ═══ CONSENT GATES VIEW ═══ */}
          {activeNav === 'consent' && (<>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Consent Gates</div>
            {pendingCount > 0 && dashSections.filter(s => s.title.toLowerCase().includes('pending') || s.title.toLowerCase().includes('review')).map((s, i) => (
              <div key={i} style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 12, padding: 16, marginBottom: 10 }}>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ color: C.amber }}>⚠</span> {s.title}</div>
                <div style={{ fontSize: 13, color: C.txtSec, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{s.content}</div>
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  <button onClick={() => handleReview()} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.green, color: C.bg0, border: 'none' }}>Approve</button>
                  <button style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.bg2, color: C.txtSec, border: `1px solid ${C.border}` }}>Review First</button>
                </div>
              </div>
            ))}
            {sessions.filter(s => s.status === 'completed').map((s, i) => (
              <div key={i} style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 12, padding: 16, marginBottom: 10 }}>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ color: C.amber }}>🔒</span> Review: {s.goal?.slice(0, 60)}</div>
                <div style={{ fontSize: 13, color: C.txtSec, marginBottom: 12 }}>Session {s.session_id?.slice(0, 8)} completed by {s.role}. Ready for sandbox review and promotion.</div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button onClick={() => handleReview(s.session_id)} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.green, color: C.bg0, border: 'none' }}>Approve & Promote</button>
                  <button style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.bg2, color: C.txtSec, border: `1px solid ${C.border}` }}>Review Diff</button>
                </div>
              </div>
            ))}
            {pendingCount === 0 && sessions.filter(s => s.status === 'completed').length === 0 && (
              <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, padding: 30, textAlign: 'center' }}>
                <div style={{ fontSize: 40, marginBottom: 12 }}>✓</div>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>All Clear</div>
                <div style={{ color: C.txtMut, fontSize: 14 }}>No items awaiting approval. Completed sessions will appear here for review.</div>
              </div>
            )}
          </>)}

          {/* ═══ ROLES VIEW ═══ */}
          {activeNav === 'roles' && (<>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>Job Roles ({roles.length})</div>
              <button onClick={() => setShowCreateRole(!showCreateRole)} style={{ padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: showCreateRole ? 'rgba(239,68,68,0.1)' : C.glowBlue, color: showCreateRole ? C.red : C.blue, border: `1px solid ${showCreateRole ? 'rgba(239,68,68,0.3)' : 'rgba(59,130,246,0.3)'}` }}>
                {showCreateRole ? 'Cancel' : '+ Create Role'}
              </button>
            </div>

            {/* Create Role Form */}
            {showCreateRole && (
              <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, padding: 20 }}>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Create New Role</div>
                {roleError && <div style={{ color: C.red, fontSize: 13, marginBottom: 12, padding: '8px 12px', background: 'rgba(239,68,68,0.1)', borderRadius: 8 }}>{roleError}</div>}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                  <div>
                    <label style={{ fontSize: 12, color: C.txtMut, marginBottom: 4, display: 'block' }}>Role Name *</label>
                    <input value={newRole.name} onChange={e => setNewRole(p => ({ ...p, name: e.target.value }))} placeholder="e.g. code-reviewer" style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14 }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: C.txtMut, marginBottom: 4, display: 'block' }}>Scope</label>
                    <select value={newRole.scope} onChange={e => setNewRole(p => ({ ...p, scope: e.target.value }))} style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14 }}>
                      <option value="coding">Coding</option><option value="research">Research</option><option value="documentation">Documentation</option><option value="testing">Testing</option><option value="devops">DevOps</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: C.txtMut, marginBottom: 4, display: 'block' }}>Auth Method</label>
                    <select value={newRole.auth_method} onChange={e => setNewRole(p => ({ ...p, auth_method: e.target.value }))} style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14 }}>
                      <option value="pin">PIN</option><option value="totp">TOTP</option><option value="none">None</option>
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: C.txtMut, marginBottom: 4, display: 'block' }}>Description</label>
                    <input value={newRole.description} onChange={e => setNewRole(p => ({ ...p, description: e.target.value }))} placeholder="Short description" style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14 }} />
                  </div>
                </div>
                <button onClick={handleCreateRole} style={{ padding: '10px 20px', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', background: C.green, color: C.bg0, border: 'none' }}>Create Role</button>
              </div>
            )}

            {/* Roles List */}
            <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, overflow: 'hidden' }}>
              <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
                {roles.map((r, i) => (
                  <div key={i} onClick={() => setSelectedRole(selectedRole?.name === r.name ? null : r)} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: selectedRole?.name === r.name ? C.glowBlue : C.bg2, borderRadius: 10, border: `1px solid ${selectedRole?.name === r.name ? 'rgba(59,130,246,0.3)' : C.borderSub}`, cursor: 'pointer', transition: 'all 0.2s ease' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ width: 36, height: 36, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', background: r.source === 'starter' ? C.glowBlue : C.glowGreen, color: r.source === 'starter' ? C.blue : C.green, fontSize: 16, fontWeight: 600 }}>{r.name.charAt(0).toUpperCase()}</div>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 500 }}>{r.name}</div>
                        <div style={{ fontSize: 12, color: C.txtMut }}>{r.scope} · {r.auth_method} · {r.source}</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      {r.source !== 'starter' && <button onClick={e => { e.stopPropagation(); handleDeleteRole(r.name) }} style={{ padding: '4px 10px', borderRadius: 6, fontSize: 11, cursor: 'pointer', background: 'rgba(239,68,68,0.1)', color: C.red, border: '1px solid rgba(239,68,68,0.2)' }}>Delete</button>}
                      <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 6, background: r.source === 'starter' ? C.glowBlue : 'rgba(34,197,94,0.1)', color: r.source === 'starter' ? C.blue : C.green }}>{r.source}</span>
                    </div>
                  </div>
                ))}
                {roles.length === 0 && <div style={{ padding: 30, textAlign: 'center', color: C.txtMut }}>No roles found. Click &quot;+ Create Role&quot; to get started.</div>}
              </div>
            </div>

            {/* Role Detail (expanded) */}
            {selectedRole && (
              <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, padding: 20 }}>
                <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>Role: {selectedRole.name}</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8 }}><div style={{ fontSize: 11, color: C.txtMut }}>Scope</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{selectedRole.scope}</div></div>
                  <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8 }}><div style={{ fontSize: 11, color: C.txtMut }}>Auth Method</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{selectedRole.auth_method}</div></div>
                  <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8 }}><div style={{ fontSize: 11, color: C.txtMut }}>Source</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{selectedRole.source}</div></div>
                  <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8 }}><div style={{ fontSize: 11, color: C.txtMut }}>Description</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{selectedRole.description || 'No description'}</div></div>
                </div>
              </div>
            )}
          </>)}

          {/* ═══ MEMORY VIEW ═══ */}
          {activeNav === 'memory' && (
            <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, padding: 30, textAlign: 'center' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>🧠</div>
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Memory</div>
              <div style={{ color: C.txtMut, fontSize: 14, maxWidth: 500, margin: '0 auto', lineHeight: 1.6 }}>
                ARA session memory and context retention. Orion stores feedback, learned patterns, and session context across autonomous work sessions. This data is used to improve future task estimation and execution.
              </div>
              {dashSections.filter(s => s.title.toLowerCase().includes('memory') || s.title.toLowerCase().includes('learning')).map((s, i) => (
                <div key={i} style={{ background: C.bg2, borderRadius: 12, padding: 16, marginTop: 16, textAlign: 'left' }}>
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>{s.title}</div>
                  <div style={{ fontSize: 13, color: C.txtSec, whiteSpace: 'pre-wrap' }}>{s.content}</div>
                </div>
              ))}
            </div>
          )}

          {/* ═══ ARA SETTINGS VIEW ═══ */}
          {activeNav === 'ara-settings' && (<>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>ARA Settings</div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                {araSaveMsg && <span style={{ fontSize: 12, color: araSaveMsg === 'Saved!' ? C.green : C.red }}>{araSaveMsg}</span>}
                <button onClick={handleSaveAraSettings} disabled={araSaving} style={{ padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.green, color: C.bg0, border: 'none', opacity: araSaving ? 0.5 : 1 }}>
                  {araSaving ? 'Saving...' : 'Save Settings'}
                </button>
              </div>
            </div>
            <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, padding: 20 }}>
              <div style={{ padding: '12px 16px', background: 'rgba(59,130,246,0.08)', borderRadius: 8, marginBottom: 20, border: '1px solid rgba(59,130,246,0.2)' }}>
                <div style={{ fontSize: 13, color: C.blue }}>These settings control how ARA autonomous sessions behave. Changes take effect on the next session start.</div>
              </div>
              {[
                { key: 'ara_enabled', label: 'ARA Enabled', desc: 'Enable the Autonomous Role Architecture', type: 'bool' },
                { key: 'ara_default_auth', label: 'Default Auth Method', desc: 'Authentication for autonomous sessions', type: 'select', options: ['pin', 'totp', 'none'] },
                { key: 'ara_max_cost_usd', label: 'Max Cost Per Session (USD)', desc: 'Maximum USD cost before auto-stop', type: 'number', min: 1, max: 100 },
                { key: 'ara_max_session_hours', label: 'Max Session Duration (hours)', desc: 'Maximum hours a session can run', type: 'number', min: 1, max: 24 },
                { key: 'ara_sandbox_mode', label: 'Sandbox Mode', desc: 'Isolation strategy for autonomous work', type: 'select', options: ['docker', 'branch', 'local'] },
                { key: 'ara_prompt_guard', label: 'Prompt Guard', desc: 'Prompt injection defence (12 patterns)', type: 'bool' },
                { key: 'ara_audit_log', label: 'Audit Log', desc: 'Tamper-proof HMAC-SHA256 audit logging', type: 'bool' },
              ].map(s => (
                <div key={s.key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 0', borderBottom: `1px solid ${C.borderSub}` }}>
                  <div><div style={{ fontSize: 14, fontWeight: 500 }}>{s.label}</div><div style={{ fontSize: 12, color: C.txtMut, marginTop: 2 }}>{s.desc}</div></div>
                  {s.type === 'bool' && (
                    <button onClick={() => setAraSettings(p => ({ ...p, [s.key]: !p[s.key] }))} style={{ width: 48, height: 26, borderRadius: 13, border: 'none', cursor: 'pointer', background: araSettings[s.key] ? C.green : C.bg3, position: 'relative', transition: 'background 0.2s' }}>
                      <span style={{ position: 'absolute', top: 3, left: araSettings[s.key] ? 25 : 3, width: 20, height: 20, borderRadius: '50%', background: '#fff', transition: 'left 0.2s' }} />
                    </button>
                  )}
                  {s.type === 'select' && (
                    <select value={araSettings[s.key] || ''} onChange={e => setAraSettings(p => ({ ...p, [s.key]: e.target.value }))} style={{ padding: '8px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 13 }}>
                      {s.options?.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  )}
                  {s.type === 'number' && (
                    <input type="number" value={araSettings[s.key] ?? ''} min={s.min} max={s.max} onChange={e => setAraSettings(p => ({ ...p, [s.key]: Number(e.target.value) }))} style={{ width: 80, padding: '8px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 13, textAlign: 'center' }} />
                  )}
                </div>
              ))}
            </div>
          </>)}
        </main>

        {/* ── RIGHT PANEL ────────────────────────────────── */}
        <aside style={{ background: C.bg1, borderLeft: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column' }}>
          {/* Consent Gates / Setup */}
          <div style={{ padding: 20, borderBottom: `1px solid ${C.border}`, maxHeight: '40vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <span style={{ background: (pendingCount + completed.length) > 0 ? C.amber : setupChecks.every(c => c.status === 'ok') ? C.green : C.amber, color: C.bg0, fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 12 }}>{pendingCount + completed.length || setupChecks.length}</span>
              <span style={{ fontSize: 14, fontWeight: 600 }}>{(pendingCount + completed.length) > 0 ? 'Awaiting Approval' : 'Setup Checks'}</span>
            </div>

            {/* Consent cards for completed sessions */}
            {completed.map((s, i) => (
              <div key={`consent-${i}`} style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 12, padding: 14, marginBottom: 10 }}>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ color: C.amber }}>🔒</span> Promote: {s.goal?.slice(0, 40)}</div>
                <div style={{ fontSize: 13, color: C.txtSec, marginBottom: 12, lineHeight: 1.5 }}>Session by {s.role} ready for review.</div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button onClick={() => handleReview(s.session_id)} style={{ padding: '8px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: C.green, color: C.bg0, border: 'none' }}>Approve</button>
                  <button style={{ padding: '8px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: C.bg2, color: C.txtSec, border: `1px solid ${C.border}` }}>Review First</button>
                </div>
              </div>
            ))}

            {/* Setup checks when no consent items */}
            {completed.length === 0 && setupChecks.map((c, i) => (
              <div key={i} style={{ background: c.status === 'ok' ? 'rgba(34,197,94,0.06)' : 'rgba(245,158,11,0.08)', border: `1px solid ${c.status === 'ok' ? 'rgba(34,197,94,0.2)' : 'rgba(245,158,11,0.2)'}`, borderRadius: 12, padding: 14, marginBottom: 10 }}>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ color: c.status === 'ok' ? C.green : C.amber }}>{c.status === 'ok' ? '✓' : c.status === 'not_configured' ? '!' : '✗'}</span>
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
                <div key={i} style={{ maxWidth: '90%', padding: '10px 14px', borderRadius: 12, fontSize: 14, lineHeight: 1.5, alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', background: m.role === 'user' ? C.blue : C.bg2, borderBottomRightRadius: m.role === 'user' ? 4 : 12, borderBottomLeftRadius: m.role === 'ai' ? 4 : 12 }}>{m.text}</div>
              ))}
            </div>
            <div style={{ padding: '12px 16px', borderTop: `1px solid ${C.border}` }}>
              <textarea value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey && chatInput.trim()) {
                  e.preventDefault()
                  setChatMessages(prev => [...prev, { role: 'user', text: chatInput.trim() }])
                  const msg = chatInput.trim(); setChatInput('')
                  fetch(`${API}/api/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: msg, workspace: '.' }) })
                    .then(r => r.ok ? r.json() : null)
                    .then(d => { if (d?.response) setChatMessages(prev => [...prev, { role: 'ai', text: d.response }]) })
                    .catch(() => setChatMessages(prev => [...prev, { role: 'ai', text: 'Could not reach the API server.' }]))
                }
              }} placeholder="Ask Orion something..." rows={2} style={{ width: '100%', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 12, padding: '12px 14px', color: C.txt, fontSize: 14, fontFamily: 'inherit', resize: 'none' }} />
            </div>
          </div>
        </aside>
      </div>

      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        select option { background: #1a1a24; color: #f0f0f5; }
      `}</style>
    </div>
  )
}
