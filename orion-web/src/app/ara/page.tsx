'use client'

import React, { useEffect, useState, useCallback, useRef } from 'react'
import Link from 'next/link'

/* ── types ─────────────────────────────────────────────────────── */
interface SetupCheck { name: string; status: string; message: string }
interface RoleInfo { name: string; scope: string; auth_method: string; source: string; description?: string; assigned_skills?: string[]; assigned_skill_groups?: string[] }
interface SessionInfo { session_id: string; role: string; goal: string; status: string; cost_usd?: number; elapsed_seconds?: number; progress?: number; created_at?: string }
interface ActivityItem { icon: 'code' | 'search' | 'write' | 'check'; title: string; desc: string; time: string }
interface DashSection { title: string; content: string; style: string; session_id?: string }
interface SkillInfo { name: string; description: string; version: string; source: string; trust_level: string; aegis_approved: boolean; tags: string[] }
interface ARASettingsData { [key: string]: any }
interface ReviewFileDiff { path: string; status: string; additions: number; deletions: number; diff: string; content: string; original: string; conflict: boolean }
interface ReviewDiffData { loading: boolean; files: ReviewFileDiff[]; summary: { total_files: number; added: number; modified: number; deleted: number; additions: number; deletions: number; conflicts: number } | null; fallbackText?: string }

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

  // Skills
  const [skills, setSkills] = useState<SkillInfo[]>([])
  const [showCreateSkill, setShowCreateSkill] = useState(false)
  const [newSkill, setNewSkill] = useState({ name: '', description: '', tags: '' })
  const [skillError, setSkillError] = useState('')
  const [selectedSkill, setSelectedSkill] = useState<SkillInfo | null>(null)
  const [assignSkillRole, setAssignSkillRole] = useState('')

  // ARA Settings
  const [araSettings, setAraSettings] = useState<ARASettingsData>({})
  const [araSaving, setAraSaving] = useState(false)
  const [araSaveMsg, setAraSaveMsg] = useState('')

  // Chat — WebSocket (same pipeline as main chat)
  const WS_URL = (process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8001/ws/chat')
  const [chatMessages, setChatMessages] = useState<{role: string; text: string; type?: string}[]>([
    { role: 'ai', text: "Welcome to the ARA Dashboard. I'm monitoring your autonomous sessions. Use /work <role> <goal> in the CLI to start a session, or browse the panels here." },
  ])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [wsConnected, setWsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const streamingRef = useRef<string>('')
  const chatWorkspaceRef = useRef<string>('.')

  // Role editing
  const [editingRole, setEditingRole] = useState<string | null>(null)
  const [editForm, setEditForm] = useState({ scope: '', auth_method: '', description: '' })

  // Consent gate inline review
  const [expandedReview, setExpandedReview] = useState<string | null>(null)
  const [reviewData, setReviewData] = useState<Record<string, ReviewDiffData>>({})
  const [selectedReviewFile, setSelectedReviewFile] = useState<string | null>(null)

  // Consent gate reject with feedback
  const [rejectingGate, setRejectingGate] = useState<string | null>(null)
  const [rejectFeedback, setRejectFeedback] = useState('')
  const [rejectSubmitting, setRejectSubmitting] = useState(false)

  // New work session
  const [showNewSession, setShowNewSession] = useState(false)
  const [newSession, setNewSession] = useState({ role: '', goal: '', workspace: '' })
  const [newSessionError, setNewSessionError] = useState('')
  const [newSessionLoading, setNewSessionLoading] = useState(false)

  // Notifications
  const [notifications, setNotifications] = useState<{id: string; message: string; type: string; time: string; read: boolean}[]>([])

  // Timer
  const [elapsed, setElapsed] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

  /* ── data loading ──────────────────────────────────────────── */
  const loadData = useCallback(async () => {
    setRefreshing(true)
    try {
      const [setupR, rolesR, sessR, statusR, dashR, settingsR, skillsR, notifR] = await Promise.allSettled([
        fetch(`${API}/api/ara/setup`),
        fetch(`${API}/api/ara/roles`),
        fetch(`${API}/api/ara/sessions`),
        fetch(`${API}/api/ara/status`),
        fetch(`${API}/api/ara/dashboard`),
        fetch(`${API}/api/settings`),
        fetch(`${API}/api/ara/skills`),
        fetch(`${API}/api/ara/notifications`),
      ])
      if (setupR.status === 'fulfilled' && setupR.value.ok) {
        const d = await setupR.value.json(); setSetupChecks(d.data?.checks || [])
      }
      if (rolesR.status === 'fulfilled' && rolesR.value.ok) {
        const d = await rolesR.value.json(); setRoles(d.data?.roles || [])
      }
      if (skillsR.status === 'fulfilled' && skillsR.value.ok) {
        const d = await skillsR.value.json(); setSkills(d.data?.skills || [])
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
      if (notifR.status === 'fulfilled' && notifR.value.ok) {
        const d = await notifR.value.json()
        setNotifications(d.data?.notifications || [])
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
  const handleStartWork = async () => {
    setNewSessionError('')
    if (!newSession.role.trim()) { setNewSessionError('Select a role'); return }
    if (!newSession.goal.trim()) { setNewSessionError('Enter a goal'); return }
    setNewSessionLoading(true)
    try {
      const res = await fetch(`${API}/api/ara/work`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role_name: newSession.role, goal: newSession.goal, workspace_path: newSession.workspace || null }),
      })
      if (res.ok) {
        const d = await res.json()
        setChatMessages(prev => [...prev, { role: 'ai', text: `🚀 ${d.message || 'Session started.'}` }])
        setNewSession({ role: '', goal: '', workspace: '' })
        setShowNewSession(false)
        loadData()
      } else {
        const e = await res.json().catch(() => ({ detail: 'Failed to start session' }))
        setNewSessionError(e.detail || e.message || 'Failed')
      }
    } catch { setNewSessionError('API unavailable') }
    setNewSessionLoading(false)
  }

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

  const handleCreateSkill = async () => {
    setSkillError('')
    if (!newSkill.name.trim()) { setSkillError('Skill name is required'); return }
    try {
      const res = await fetch(`${API}/api/ara/skills`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newSkill.name, description: newSkill.description, tags: newSkill.tags ? newSkill.tags.split(',').map((t: string) => t.trim()).filter(Boolean) : [] }),
      })
      if (!res.ok) { const e = await res.json(); setSkillError(e.detail || 'Failed'); return }
      setNewSkill({ name: '', description: '', tags: '' })
      setShowCreateSkill(false)
      loadData()
    } catch { setSkillError('API unavailable') }
  }

  const handleDeleteSkill = async (name: string) => {
    if (!confirm(`Delete skill "${name}"?`)) return
    try {
      const res = await fetch(`${API}/api/ara/skills/${encodeURIComponent(name)}`, { method: 'DELETE' })
      if (!res.ok) { const e = await res.json(); alert(e.detail || 'Failed'); return }
      setSelectedSkill(null)
      loadData()
    } catch { alert('API unavailable') }
  }

  const handleAssignSkill = async (skillName: string, roleName: string) => {
    try {
      const res = await fetch(`${API}/api/ara/skills/assign`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_name: skillName, role_name: roleName }),
      })
      if (!res.ok) { const e = await res.json(); alert(e.detail || 'Failed'); return }
      setAssignSkillRole('')
      loadData()
    } catch { alert('API unavailable') }
  }

  const handleUnassignSkill = async (skillName: string, roleName: string) => {
    try {
      const res = await fetch(`${API}/api/ara/skills/unassign`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ skill_name: skillName, role_name: roleName }),
      })
      if (!res.ok) { const e = await res.json(); alert(e.detail || 'Failed'); return }
      loadData()
    } catch { alert('API unavailable') }
  }

  const handleScanSkill = async (name: string) => {
    try {
      const res = await fetch(`${API}/api/ara/skills/${encodeURIComponent(name)}/scan`, { method: 'POST' })
      const d = await res.json()
      alert(d.message || 'Scan complete')
      loadData()
    } catch { alert('API unavailable') }
  }

  // ── WebSocket chat connection (same /ws/chat as main ChatInterface) ───
  const handleWsMessage = useCallback((event: MessageEvent) => {
    try {
      const data = JSON.parse(event.data)
      switch (data.type) {
        case 'routing':
          // Scout routing — silent debug log, don't show to user
          console.debug('[ARA Chat] Scout:', data.route, data.reasoning)
          break
        case 'status':
          setChatMessages(prev => [...prev, { role: 'ai', text: data.message, type: 'status' }])
          break
        case 'token': {
          const token = data.content as string
          streamingRef.current += token
          const currentText = streamingRef.current
          setChatMessages(prev => {
            const last = prev[prev.length - 1]
            if (last && last.type === 'streaming') {
              return [...prev.slice(0, -1), { ...last, text: currentText }]
            }
            return [...prev, { role: 'ai', text: currentText, type: 'streaming' }]
          })
          break
        }
        case 'council_phase':
          setChatMessages(prev => [...prev, { role: 'ai', text: data.message, type: 'council' }])
          break
        case 'complete':
          setChatLoading(false)
          if (streamingRef.current) {
            // Finalize streaming message
            setChatMessages(prev => {
              const last = prev[prev.length - 1]
              if (last && last.type === 'streaming') {
                return [...prev.slice(0, -1), { ...last, type: 'complete' }]
              }
              return prev
            })
            streamingRef.current = ''
          } else {
            setChatMessages(prev => [...prev, { role: 'ai', text: data.response || 'Done.', type: 'complete' }])
          }
          break
        case 'escalation':
          setChatLoading(false)
          setChatMessages(prev => [...prev, { role: 'ai', text: `ESCALATION: ${data.message}\nReason: ${data.reason}`, type: 'error' }])
          break
        case 'error':
          setChatLoading(false)
          streamingRef.current = ''
          setChatMessages(prev => [...prev, { role: 'ai', text: `Error: ${data.message}`, type: 'error' }])
          break
        case 'feedback_ack':
          break
        default:
          setChatLoading(false)
          setChatMessages(prev => [...prev, { role: 'ai', text: JSON.stringify(data, null, 2) }])
      }
    } catch {
      setChatMessages(prev => [...prev, { role: 'ai', text: event.data }])
    }
  }, [])

  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    try {
      const ws = new WebSocket(WS_URL)
      ws.onopen = () => {
        setWsConnected(true)
        if (reconnectRef.current) { clearTimeout(reconnectRef.current); reconnectRef.current = null }
      }
      ws.onclose = () => {
        if (wsRef.current === ws) {
          setWsConnected(false)
          wsRef.current = null
          reconnectRef.current = setTimeout(connectWs, 3000)
        }
      }
      ws.onerror = () => { if (wsRef.current === ws) setWsConnected(false) }
      ws.onmessage = handleWsMessage
      wsRef.current = ws
    } catch {
      setWsConnected(false)
      reconnectRef.current = setTimeout(connectWs, 3000)
    }
  }, [WS_URL, handleWsMessage])

  // Connect WebSocket + load workspace from settings
  useEffect(() => {
    connectWs()
    // Load workspace setting so chat uses the real project path
    fetch(`${API}/api/settings`).then(r => r.ok ? r.json() : null)
      .then(s => { if (s?.workspace) chatWorkspaceRef.current = s.workspace })
      .catch(() => {})
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
      wsRef.current?.close()
    }
  }, [connectWs, API])

  const sendChat = (msg: string) => {
    if (!msg.trim() || chatLoading) return
    setChatMessages(prev => [...prev, { role: 'user', text: msg.trim() }])
    setChatInput('')

    if (!wsConnected || !wsRef.current) {
      setChatMessages(prev => [...prev, { role: 'ai', text: 'Not connected to Orion API. Start the server with: uvicorn orion.api.server:app --port 8001', type: 'error' }])
      return
    }

    setChatLoading(true)
    streamingRef.current = ''
    wsRef.current.send(JSON.stringify({ message: msg.trim(), workspace: chatWorkspaceRef.current }))
  }

  const handleUpdateRole = async (name: string) => {
    try {
      const res = await fetch(`${API}/api/ara/roles/${encodeURIComponent(name)}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      })
      if (res.ok) {
        setEditingRole(null)
        setSelectedRole(null)
        loadData()
      } else {
        const e = await res.json(); alert(e.detail || 'Update failed')
      }
    } catch { alert('API unavailable') }
  }

  const handleResetDashboard = async () => {
    if (!confirm('Clear all completed, failed, and cancelled sessions? Active sessions will be preserved.')) return
    try {
      const res = await fetch(`${API}/api/ara/sessions/clear`, { method: 'POST' })
      if (res.ok) {
        const d = await res.json()
        setChatMessages(prev => [...prev, { role: 'ai', text: `Dashboard reset: ${d.message}` }])
        loadData()
      } else {
        alert('Reset failed')
      }
    } catch { alert('API unavailable') }
  }

  const handleRejectWithFeedback = async (sid?: string) => {
    const key = sid || '__pending__'
    if (rejectingGate === key) { setRejectingGate(null); setRejectFeedback(''); return }
    setRejectingGate(key)
    setRejectFeedback('')
    setExpandedReview(null)
  }

  const submitReject = async (sid?: string) => {
    if (!rejectFeedback.trim()) return
    setRejectSubmitting(true)
    try {
      // 1. Reject the session
      await fetch(`${API}/api/ara/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid || null }),
      })
      // 2. Submit feedback with rating 1 (rejection) so it enters the feedback loop
      if (sid) {
        await fetch(`${API}/api/ara/feedback`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sid, rating: 1, comment: `[Rejected] ${rejectFeedback.trim()}` }),
        })
      }
      setRejectingGate(null)
      setRejectFeedback('')
      loadData()
    } catch { alert('API unavailable') }
    setRejectSubmitting(false)
  }

  const handleReview = async (sid?: string) => {
    try {
      const params = sid ? `?session_id=${encodeURIComponent(sid)}` : ''
      const reviewRes = await fetch(`${API}/api/ara/review${params}`, { method: 'POST' })
      if (reviewRes.ok) {
        const rd = await reviewRes.json()
        if (rd.success) {
          // AEGIS gate passed — promote sandbox to workspace
          const promoteRes = await fetch(`${API}/api/ara/promote`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sid || null }),
          })
          if (promoteRes.ok) {
            const pd = await promoteRes.json()
            setChatMessages(prev => [...prev, { role: 'ai', text: `✅ ${pd.message || 'Session promoted to workspace.'}` }])
          } else {
            const pe = await promoteRes.json().catch(() => ({ detail: 'Promotion failed' }))
            setChatMessages(prev => [...prev, { role: 'ai', text: `⚠ AEGIS approved but promotion failed: ${pe.detail || pe.message}`, type: 'error' }])
          }
        } else {
          setChatMessages(prev => [...prev, { role: 'ai', text: `🔒 AEGIS Gate blocked: ${rd.message}`, type: 'error' }])
        }
      }
      loadData()
    } catch {}
  }

  const handleViewPlan = async (sid?: string) => {
    const key = sid || '__pending__'
    if (expandedReview === key) { setExpandedReview(null); setSelectedReviewFile(null); return }
    setExpandedReview(key)
    setSelectedReviewFile(null)
    if (reviewData[key] && !reviewData[key].loading) return
    const empty: ReviewDiffData = { loading: true, files: [], summary: null }
    setReviewData(prev => ({ ...prev, [key]: empty }))
    try {
      // Try structured diff endpoint first (needs session_id)
      if (sid) {
        const diffRes = await fetch(`${API}/api/ara/sessions/${encodeURIComponent(sid)}/diff`)
        if (diffRes.ok) {
          const d = await diffRes.json()
          if (d.success && d.data?.files?.length > 0) {
            setReviewData(prev => ({ ...prev, [key]: { loading: false, files: d.data.files, summary: d.data.summary } }))
            return
          }
        }
      }
      // Fallback to plan endpoint
      const params = sid ? `?session_id=${encodeURIComponent(sid)}` : ''
      const res = await fetch(`${API}/api/ara/plan${params}`)
      if (res.ok) {
        const d = await res.json()
        const planText = d.data?.plan_text || d.message || 'No plan data available.'
        setReviewData(prev => ({ ...prev, [key]: { loading: false, files: [], summary: null, fallbackText: planText } }))
      } else {
        setReviewData(prev => ({ ...prev, [key]: { loading: false, files: [], summary: null, fallbackText: 'Could not load review data.' } }))
      }
    } catch {
      setReviewData(prev => ({ ...prev, [key]: { loading: false, files: [], summary: null, fallbackText: 'API unavailable — could not fetch review data.' } }))
    }
  }

  const dashOffset = 264 - (264 * progress / 100)

  const actIcon = (t: string) => t === 'code' ? '< >' : t === 'search' ? '🔍' : t === 'check' ? '✓' : '📝'
  const actColor = (t: string) => t === 'code' ? C.glowBlue : t === 'search' ? C.glowAmber : t === 'check' ? C.glowGreen : C.glowGreen
  const actTextColor = (t: string) => t === 'code' ? C.blue : t === 'search' ? C.amber : t === 'check' ? C.green : C.green

  /* ── diff review panel renderer ───────────────────────────── */
  const renderReviewPanel = (rd: ReviewDiffData | undefined, bottomRadius: boolean) => {
    if (!rd) return null
    if (rd.loading) return <div style={{ color: C.txtMut, fontSize: 13, padding: 16, textAlign: 'center' }}>Loading review data...</div>

    // Fallback: plain text plan
    if (rd.files.length === 0 && rd.fallbackText) {
      return <div style={{ fontSize: 13, color: C.txtSec, lineHeight: 1.7, whiteSpace: 'pre-wrap', maxHeight: 400, overflowY: 'auto', fontFamily: 'monospace', background: C.bg2, borderRadius: 8, padding: 14 }}>{rd.fallbackText}</div>
    }
    if (rd.files.length === 0) return <div style={{ color: C.txtMut, fontSize: 13, padding: 12, textAlign: 'center' }}>No file changes found in sandbox.</div>

    const statusIcon = (s: string) => s === 'added' ? '+' : s === 'deleted' ? '−' : s === 'unchanged' ? '=' : '~'
    const statusColor = (s: string) => s === 'added' ? C.green : s === 'deleted' ? C.red : s === 'unchanged' ? C.blue : C.amber
    const allUnchanged = rd.files.every(f => f.status === 'unchanged')
    const sel = rd.files.find(f => f.path === selectedReviewFile) || null

    return (
      <div>
        {/* Summary bar */}
        {rd.summary && (
          <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginBottom: 12, padding: '8px 12px', background: C.bg2, borderRadius: 8, fontSize: 12, flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 600, color: C.txt }}>{rd.summary.total_files > 0 ? `${rd.summary.total_files} file${rd.summary.total_files !== 1 ? 's' : ''} changed` : `${rd.files.length} file${rd.files.length !== 1 ? 's' : ''} in sandbox`}{allUnchanged ? ' (already promoted)' : ''}</span>
            {rd.summary.added > 0 && <span style={{ color: C.green }}>{rd.summary.added} added</span>}
            {rd.summary.modified > 0 && <span style={{ color: C.amber }}>{rd.summary.modified} modified</span>}
            {rd.summary.deleted > 0 && <span style={{ color: C.red }}>{rd.summary.deleted} deleted</span>}
            <span style={{ color: C.green }}>+{rd.summary.additions}</span>
            <span style={{ color: C.red }}>−{rd.summary.deletions}</span>
            {rd.summary.conflicts > 0 && <span style={{ color: C.red, fontWeight: 600 }}>⚠ {rd.summary.conflicts} conflict{rd.summary.conflicts !== 1 ? 's' : ''}</span>}
          </div>
        )}

        {/* File tree + diff viewer */}
        <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 0, border: `1px solid ${C.border}`, borderRadius: 8, overflow: 'hidden', maxHeight: 500 }}>
          {/* File tree */}
          <div style={{ background: C.bg2, borderRight: `1px solid ${C.border}`, overflowY: 'auto', maxHeight: 500 }}>
            <div style={{ padding: '8px 10px', fontSize: 11, fontWeight: 600, color: C.txtMut, textTransform: 'uppercase', letterSpacing: 1, borderBottom: `1px solid ${C.border}` }}>Changed Files</div>
            {rd.files.map((f, fi) => {
              const isSelected = selectedReviewFile === f.path
              const parts = f.path.split('/')
              const fileName = parts[parts.length - 1]
              const dirPath = parts.length > 1 ? parts.slice(0, -1).join('/') + '/' : ''
              return (
                <div key={fi} onClick={() => setSelectedReviewFile(isSelected ? null : f.path)}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', cursor: 'pointer', background: isSelected ? C.glowBlue : 'transparent', borderBottom: `1px solid ${C.borderSub}`, transition: 'background 0.15s' }}>
                  <span style={{ width: 18, height: 18, borderRadius: 4, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: statusColor(f.status), background: `${statusColor(f.status)}20`, flexShrink: 0 }}>{statusIcon(f.status)}</span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: isSelected ? C.blue : C.txt, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{fileName}</div>
                    {dirPath && <div style={{ fontSize: 10, color: C.txtMut, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{dirPath}</div>}
                  </div>
                  <div style={{ fontSize: 10, color: C.txtMut, flexShrink: 0, textAlign: 'right' }}>
                    {f.additions > 0 && <span style={{ color: C.green }}>+{f.additions}</span>}
                    {f.additions > 0 && f.deletions > 0 && ' '}
                    {f.deletions > 0 && <span style={{ color: C.red }}>−{f.deletions}</span>}
                  </div>
                  {f.conflict && <span style={{ fontSize: 10, color: C.red, fontWeight: 700 }}>⚠</span>}
                </div>
              )
            })}
          </div>

          {/* Diff viewer */}
          <div style={{ overflowY: 'auto', maxHeight: 500, background: C.bg0 }}>
            {sel ? (
              <div>
                <div style={{ padding: '8px 14px', fontSize: 12, fontWeight: 600, color: C.txt, background: C.bg1, borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{sel.path}</span>
                  <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, background: `${statusColor(sel.status)}20`, color: statusColor(sel.status), fontWeight: 600 }}>{sel.status}</span>
                </div>
                {sel.diff ? (
                  <pre style={{ margin: 0, padding: '10px 0', fontSize: 12, lineHeight: 1.6, fontFamily: "'Fira Code', 'Cascadia Code', 'Consolas', monospace", overflow: 'auto' }}>
                    {sel.diff.split('\n').map((line, li) => {
                      let bg = 'transparent'
                      let color = C.txtSec
                      if (line.startsWith('+++') || line.startsWith('---')) { color = C.txtMut }
                      else if (line.startsWith('@@')) { bg = 'rgba(59,130,246,0.08)'; color = C.blue }
                      else if (line.startsWith('+')) { bg = 'rgba(34,197,94,0.1)'; color = C.green }
                      else if (line.startsWith('-')) { bg = 'rgba(239,68,68,0.1)'; color = C.red }
                      return <div key={li} style={{ padding: '0 14px', background: bg, color, minHeight: 20 }}>{line || ' '}</div>
                    })}
                  </pre>
                ) : sel.content ? (
                  <pre style={{ margin: 0, padding: 14, fontSize: 12, lineHeight: 1.6, color: C.txtSec, fontFamily: "'Fira Code', 'Cascadia Code', 'Consolas', monospace", overflow: 'auto' }}>{sel.content}</pre>
                ) : (
                  <div style={{ padding: 20, color: C.txtMut, fontSize: 13, textAlign: 'center' }}>No content available for this file.</div>
                )}
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: 200, color: C.txtMut, fontSize: 13 }}>
                Select a file to view changes
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

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
            <button onClick={handleResetDashboard} style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, padding: '6px 12px', color: C.red, cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
              Reset
            </button>
            {lastRefresh && <span style={{ fontSize: 11, color: C.txtMut, fontFamily: 'monospace' }}>Updated {lastRefresh.toLocaleTimeString()}</span>}
            {notifications.filter(n => !n.read).length > 0 && (
              <div style={{ position: 'relative', cursor: 'pointer' }} title={`${notifications.filter(n => !n.read).length} unread notifications`}>
                <span style={{ fontSize: 16 }}>🔔</span>
                <span style={{ position: 'absolute', top: -4, right: -6, background: C.red, color: '#fff', fontSize: 9, fontWeight: 700, borderRadius: '50%', width: 16, height: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{notifications.filter(n => !n.read).length}</span>
              </div>
            )}
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
          <NavBtn id="skills" icon="🧩" label="Skills" badge={skills.length} />
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

            {/* New Session Form */}
            {!isWorking && (
              <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, overflow: 'hidden' }}>
                {!showNewSession ? (
                  <div style={{ padding: '16px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 14, color: C.txtSec }}>No active session</span>
                    <button onClick={() => setShowNewSession(true)} style={{ padding: '10px 20px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: `linear-gradient(135deg, ${C.green}, ${C.blue})`, color: '#fff', border: 'none' }}>+ New Session</button>
                  </div>
                ) : (
                  <div style={{ padding: 20 }}>
                    <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 14 }}>Start New Work Session</div>
                    {newSessionError && <div style={{ padding: '8px 12px', background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, color: C.red, fontSize: 12, marginBottom: 12 }}>{newSessionError}</div>}
                    <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: 12, marginBottom: 12 }}>
                      <div>
                        <label style={{ fontSize: 12, color: C.txtMut, marginBottom: 4, display: 'block' }}>Role *</label>
                        <select value={newSession.role} onChange={e => setNewSession(p => ({ ...p, role: e.target.value }))} style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 13 }}>
                          <option value="">Select role...</option>
                          {roles.map(r => <option key={r.name} value={r.name}>{r.name}</option>)}
                        </select>
                      </div>
                      <div>
                        <label style={{ fontSize: 12, color: C.txtMut, marginBottom: 4, display: 'block' }}>Goal *</label>
                        <input value={newSession.goal} onChange={e => setNewSession(p => ({ ...p, goal: e.target.value }))} placeholder="Describe what the agent should accomplish..." style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 13 }} />
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <button onClick={handleStartWork} disabled={newSessionLoading} style={{ padding: '10px 20px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: newSessionLoading ? 'wait' : 'pointer', background: C.green, color: C.bg0, border: 'none', opacity: newSessionLoading ? 0.6 : 1 }}>{newSessionLoading ? 'Starting...' : 'Start Session'}</button>
                      <button onClick={() => { setShowNewSession(false); setNewSessionError('') }} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.bg2, color: C.txtSec, border: `1px solid ${C.border}` }}>Cancel</button>
                    </div>
                  </div>
                )}
              </div>
            )}

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
            {pendingCount > 0 && dashSections.filter(s => s.title.toLowerCase().includes('pending') || s.title.toLowerCase().includes('review')).map((s, i) => {
              // Use session_id from dashboard section data (added by API), with regex fallback
              let pendingSid = s.session_id || undefined
              if (!pendingSid) {
                const sidMatch = s.content.match(/[Ss]ession\s+([a-f0-9]{8,})/i)
                const sidFragment = sidMatch?.[1] || ''
                const matchedSession = sidFragment ? sessions.find(ss => ss.session_id?.startsWith(sidFragment)) : null
                pendingSid = matchedSession?.session_id || sessions.find(ss => ss.status === 'completed')?.session_id || undefined
              }
              const key = pendingSid || `__pending_${i}__`
              const isExpanded = expandedReview === key
              const rd = reviewData[key]
              return (
                <div key={i} style={{ marginBottom: 10 }}>
                  <div style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: isExpanded ? '12px 12px 0 0' : 12, padding: 16 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ color: C.amber }}>⚠</span> {s.title}</div>
                    <div style={{ fontSize: 13, color: C.txtSec, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{s.content}</div>
                    <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                      <button onClick={() => handleReview(pendingSid)} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.green, color: C.bg0, border: 'none' }}>Approve</button>
                      <button onClick={() => handleViewPlan(pendingSid)} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: isExpanded ? 'rgba(59,130,246,0.15)' : C.bg2, color: isExpanded ? C.blue : C.txtSec, border: `1px solid ${isExpanded ? 'rgba(59,130,246,0.3)' : C.border}` }}>Review First {isExpanded ? '▲' : '▼'}</button>
                      <button onClick={() => handleRejectWithFeedback(pendingSid)} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: rejectingGate === key ? 'rgba(239,68,68,0.15)' : 'rgba(239,68,68,0.08)', color: C.red, border: '1px solid rgba(239,68,68,0.25)' }}>Reject {rejectingGate === key ? '▲' : ''}</button>
                    </div>
                  </div>
                  {isExpanded && (
                    <div style={{ background: C.bg1, border: '1px solid rgba(245,158,11,0.2)', borderTop: 'none', borderRadius: rejectingGate === key ? 0 : '0 0 12px 12px', padding: 16 }}>
                      {renderReviewPanel(rd, !(rejectingGate === key))}
                    </div>
                  )}
                  {rejectingGate === key && (
                    <div style={{ background: 'rgba(239,68,68,0.04)', border: '1px solid rgba(239,68,68,0.2)', borderTop: isExpanded ? 'none' : undefined, borderRadius: '0 0 12px 12px', padding: 16 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: C.red, marginBottom: 8 }}>Why are you rejecting this?</div>
                      <div style={{ fontSize: 12, color: C.txtMut, marginBottom: 10 }}>Your feedback will be sent to Orion so it can learn from this and improve future work.</div>
                      <textarea value={rejectFeedback} onChange={e => setRejectFeedback(e.target.value)} placeholder="Explain what was wrong or what you expected instead..." rows={4} style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 13, fontFamily: 'inherit', resize: 'vertical', marginBottom: 10 }} />
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button disabled={!rejectFeedback.trim() || rejectSubmitting} onClick={() => submitReject(pendingSid)} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: rejectFeedback.trim() ? 'pointer' : 'not-allowed', background: rejectFeedback.trim() ? C.red : C.bg3, color: rejectFeedback.trim() ? '#fff' : C.txtMut, border: 'none', opacity: rejectSubmitting ? 0.6 : 1 }}>{rejectSubmitting ? 'Rejecting...' : 'Reject & Send Feedback'}</button>
                        <button onClick={() => { setRejectingGate(null); setRejectFeedback('') }} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.bg2, color: C.txtSec, border: `1px solid ${C.border}` }}>Cancel</button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
            {sessions.filter(s => s.status === 'completed').map((s, i) => {
              const key = s.session_id || `completed-${i}`
              const isExpanded = expandedReview === key
              const rd = reviewData[key]
              return (
                <div key={i} style={{ marginBottom: 10 }}>
                  <div style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: isExpanded ? '12px 12px 0 0' : 12, padding: 16 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ color: C.amber }}>🔒</span> Review: {s.goal?.slice(0, 60)}</div>
                    <div style={{ fontSize: 13, color: C.txtSec, marginBottom: 12 }}>Session {s.session_id?.slice(0, 8)} completed by {s.role}. Ready for sandbox review and promotion.</div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => handleReview(s.session_id)} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.green, color: C.bg0, border: 'none' }}>Approve & Promote</button>
                      <button onClick={() => handleViewPlan(s.session_id)} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: isExpanded ? 'rgba(59,130,246,0.15)' : C.bg2, color: isExpanded ? C.blue : C.txtSec, border: `1px solid ${isExpanded ? 'rgba(59,130,246,0.3)' : C.border}` }}>Review Diff {isExpanded ? '▲' : '▼'}</button>
                      <button onClick={() => handleRejectWithFeedback(s.session_id)} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: rejectingGate === key ? 'rgba(239,68,68,0.15)' : 'rgba(239,68,68,0.08)', color: C.red, border: '1px solid rgba(239,68,68,0.25)' }}>Reject {rejectingGate === key ? '▲' : ''}</button>
                    </div>
                  </div>
                  {isExpanded && (
                    <div style={{ background: C.bg1, border: '1px solid rgba(245,158,11,0.2)', borderTop: 'none', borderRadius: rejectingGate === key ? 0 : '0 0 12px 12px', padding: 16 }}>
                      {renderReviewPanel(rd, !(rejectingGate === key))}
                    </div>
                  )}
                  {rejectingGate === key && (
                    <div style={{ background: 'rgba(239,68,68,0.04)', border: '1px solid rgba(239,68,68,0.2)', borderTop: isExpanded ? 'none' : undefined, borderRadius: '0 0 12px 12px', padding: 16 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: C.red, marginBottom: 8 }}>Why are you rejecting this?</div>
                      <div style={{ fontSize: 12, color: C.txtMut, marginBottom: 10 }}>Your feedback will be sent to Orion so it can learn from this and improve future work.</div>
                      <textarea value={rejectFeedback} onChange={e => setRejectFeedback(e.target.value)} placeholder="Explain what was wrong or what you expected instead..." rows={4} style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 13, fontFamily: 'inherit', resize: 'vertical', marginBottom: 10 }} />
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button disabled={!rejectFeedback.trim() || rejectSubmitting} onClick={() => submitReject(s.session_id)} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: rejectFeedback.trim() ? 'pointer' : 'not-allowed', background: rejectFeedback.trim() ? C.red : C.bg3, color: rejectFeedback.trim() ? '#fff' : C.txtMut, border: 'none', opacity: rejectSubmitting ? 0.6 : 1 }}>{rejectSubmitting ? 'Rejecting...' : 'Reject & Send Feedback'}</button>
                        <button onClick={() => { setRejectingGate(null); setRejectFeedback('') }} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.bg2, color: C.txtSec, border: `1px solid ${C.border}` }}>Cancel</button>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
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
                </div>
                <div style={{ marginBottom: 12 }}>
                  <label style={{ fontSize: 12, color: C.txtMut, marginBottom: 4, display: 'block' }}>Description</label>
                  <textarea value={newRole.description} onChange={e => setNewRole(p => ({ ...p, description: e.target.value }))} placeholder="Describe the role's responsibilities, context, and expected behavior in detail..." rows={4} style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14, fontFamily: 'inherit', resize: 'vertical' }} />
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
                      <button onClick={e => { e.stopPropagation(); setEditingRole(r.name); setEditForm({ scope: r.scope, auth_method: r.auth_method, description: r.description || '' }); setSelectedRole(r) }} style={{ padding: '4px 10px', borderRadius: 6, fontSize: 11, cursor: 'pointer', background: C.glowBlue, color: C.blue, border: '1px solid rgba(59,130,246,0.2)' }}>Edit</button>
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
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>Role: {selectedRole.name}</div>
                  {editingRole !== selectedRole.name && (
                    <button onClick={() => { setEditingRole(selectedRole.name); setEditForm({ scope: selectedRole.scope, auth_method: selectedRole.auth_method, description: selectedRole.description || '' }) }} style={{ padding: '6px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: C.glowBlue, color: C.blue, border: '1px solid rgba(59,130,246,0.3)' }}>Edit Role</button>
                  )}
                </div>

                {editingRole === selectedRole.name ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                      <div>
                        <label style={{ fontSize: 11, color: C.txtMut, display: 'block', marginBottom: 4 }}>Scope</label>
                        <select value={editForm.scope} onChange={e => setEditForm(p => ({ ...p, scope: e.target.value }))} style={{ width: '100%', padding: '10px 14px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14 }}>
                          <option value="coding">coding</option>
                          <option value="research">research</option>
                          <option value="devops">devops</option>
                          <option value="full">full</option>
                        </select>
                      </div>
                      <div>
                        <label style={{ fontSize: 11, color: C.txtMut, display: 'block', marginBottom: 4 }}>Auth Method</label>
                        <select value={editForm.auth_method} onChange={e => setEditForm(p => ({ ...p, auth_method: e.target.value }))} style={{ width: '100%', padding: '10px 14px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14 }}>
                          <option value="pin">pin</option>
                          <option value="totp">totp</option>
                        </select>
                      </div>
                    </div>
                    <div>
                      <label style={{ fontSize: 11, color: C.txtMut, display: 'block', marginBottom: 4 }}>Description</label>
                      <textarea value={editForm.description} onChange={e => setEditForm(p => ({ ...p, description: e.target.value }))} placeholder="Describe the role's responsibilities, context, and expected behavior in detail..." rows={5} style={{ width: '100%', padding: '10px 14px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14, fontFamily: 'inherit', resize: 'vertical' }} />
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button onClick={() => handleUpdateRole(selectedRole.name)} style={{ padding: '8px 20px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.green, color: C.bg0, border: 'none' }}>Save Changes</button>
                      <button onClick={() => setEditingRole(null)} style={{ padding: '8px 20px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: C.bg2, color: C.txtSec, border: `1px solid ${C.border}` }}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8 }}><div style={{ fontSize: 11, color: C.txtMut }}>Scope</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{selectedRole.scope}</div></div>
                    <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8 }}><div style={{ fontSize: 11, color: C.txtMut }}>Auth Method</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{selectedRole.auth_method}</div></div>
                    <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8 }}><div style={{ fontSize: 11, color: C.txtMut }}>Source</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{selectedRole.source}</div></div>
                    <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8, gridColumn: '1 / -1' }}><div style={{ fontSize: 11, color: C.txtMut }}>Description</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4, whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{selectedRole.description || 'No description'}</div></div>
                  </div>
                )}

                {/* Assigned Skills */}
                <div style={{ borderTop: `1px solid ${C.border}`, marginTop: 16, paddingTop: 16 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>Assigned Skills</div>
                  {(selectedRole.assigned_skills && selectedRole.assigned_skills.length > 0) ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {selectedRole.assigned_skills.map((sk, si) => {
                        const skillInfo = skills.find(s => s.name === sk)
                        return (
                          <div key={si} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: C.bg2, borderRadius: 8, border: `1px solid ${C.borderSub}` }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                              <span style={{ fontSize: 14 }}>🧩</span>
                              <div>
                                <div style={{ fontSize: 13, fontWeight: 500 }}>{sk}</div>
                                {skillInfo && <div style={{ fontSize: 11, color: C.txtMut }}>{skillInfo.description?.slice(0, 80) || 'No description'}</div>}
                              </div>
                            </div>
                            <button onClick={() => handleUnassignSkill(sk, selectedRole.name)} style={{ padding: '4px 12px', borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: 'pointer', background: 'rgba(239,68,68,0.1)', color: C.red, border: '1px solid rgba(239,68,68,0.2)' }}>Remove</button>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <div style={{ padding: '14px 16px', background: C.bg2, borderRadius: 8, color: C.txtMut, fontSize: 13 }}>No skills assigned. Go to Skills → select a skill → Assign to Role.</div>
                  )}
                  {(selectedRole.assigned_skill_groups && selectedRole.assigned_skill_groups.length > 0) && (
                    <div style={{ marginTop: 12 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: C.txtSec, marginBottom: 6 }}>Skill Groups</div>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {selectedRole.assigned_skill_groups.map((sg, sgi) => (
                          <span key={sgi} style={{ fontSize: 12, padding: '4px 12px', borderRadius: 6, background: C.glowBlue, color: C.blue, border: '1px solid rgba(59,130,246,0.2)' }}>{sg}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </>)}

          {/* ═══ SKILLS VIEW ═══ */}
          {activeNav === 'skills' && (<>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>Skills ({skills.length})</div>
              <button onClick={() => setShowCreateSkill(!showCreateSkill)} style={{ padding: '8px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: 'pointer', background: showCreateSkill ? 'rgba(239,68,68,0.1)' : C.glowBlue, color: showCreateSkill ? C.red : C.blue, border: `1px solid ${showCreateSkill ? 'rgba(239,68,68,0.3)' : 'rgba(59,130,246,0.3)'}` }}>
                {showCreateSkill ? 'Cancel' : '+ Create Skill'}
              </button>
            </div>

            {/* Create Skill Form */}
            {showCreateSkill && (
              <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, padding: 20 }}>
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Create New Skill</div>
                {skillError && <div style={{ color: C.red, fontSize: 13, marginBottom: 12, padding: '8px 12px', background: 'rgba(239,68,68,0.1)', borderRadius: 8 }}>{skillError}</div>}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
                  <div>
                    <label style={{ fontSize: 12, color: C.txtMut, marginBottom: 4, display: 'block' }}>Skill Name *</label>
                    <input value={newSkill.name} onChange={e => setNewSkill(p => ({ ...p, name: e.target.value }))} placeholder="e.g. code-review" style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14 }} />
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: C.txtMut, marginBottom: 4, display: 'block' }}>Tags (comma-separated)</label>
                    <input value={newSkill.tags} onChange={e => setNewSkill(p => ({ ...p, tags: e.target.value }))} placeholder="e.g. quality, testing" style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14 }} />
                  </div>
                </div>
                <div style={{ marginBottom: 12 }}>
                  <label style={{ fontSize: 12, color: C.txtMut, marginBottom: 4, display: 'block' }}>Description</label>
                  <textarea value={newSkill.description} onChange={e => setNewSkill(p => ({ ...p, description: e.target.value }))} placeholder="Describe what this skill does, when it should be used, and what context it provides to the agent..." rows={4} style={{ width: '100%', padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14, fontFamily: 'inherit', resize: 'vertical' }} />
                </div>
                <button onClick={handleCreateSkill} style={{ padding: '10px 20px', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', background: C.green, color: C.bg0, border: 'none' }}>Create Skill</button>
              </div>
            )}

            {/* Skills List */}
            <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, overflow: 'hidden' }}>
              <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
                {skills.map((s, i) => (
                  <div key={i} onClick={() => setSelectedSkill(selectedSkill?.name === s.name ? null : s)} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', background: selectedSkill?.name === s.name ? C.glowBlue : C.bg2, borderRadius: 10, border: `1px solid ${selectedSkill?.name === s.name ? 'rgba(59,130,246,0.3)' : C.borderSub}`, cursor: 'pointer', transition: 'all 0.2s ease' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ width: 36, height: 36, borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', background: s.aegis_approved ? C.glowGreen : 'rgba(239,68,68,0.1)', color: s.aegis_approved ? C.green : C.red, fontSize: 16, fontWeight: 600 }}>{s.aegis_approved ? '✓' : '✗'}</div>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 500 }}>{s.name}</div>
                        <div style={{ fontSize: 12, color: C.txtMut }}>{s.description?.slice(0, 60) || 'No description'}</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      {s.tags?.slice(0, 2).map((t, ti) => <span key={ti} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 6, background: C.bg3, color: C.txtSec }}>{t}</span>)}
                      <span style={{ fontSize: 10, padding: '3px 10px', borderRadius: 6, background: s.trust_level === 'verified' ? C.glowGreen : s.trust_level === 'blocked' ? 'rgba(239,68,68,0.1)' : C.glowBlue, color: s.trust_level === 'verified' ? C.green : s.trust_level === 'blocked' ? C.red : C.blue }}>{s.trust_level}</span>
                      <span style={{ fontSize: 10, padding: '3px 10px', borderRadius: 6, background: s.source === 'imported' ? C.glowBlue : 'rgba(34,197,94,0.1)', color: s.source === 'imported' ? C.blue : C.green }}>{s.source}</span>
                    </div>
                  </div>
                ))}
                {skills.length === 0 && <div style={{ padding: 30, textAlign: 'center', color: C.txtMut }}>No skills found. Click &quot;+ Create Skill&quot; or use /skill create in the CLI.</div>}
              </div>
            </div>

            {/* Skill Detail (expanded) */}
            {selectedSkill && (
              <div style={{ background: C.bg1, border: `1px solid ${C.border}`, borderRadius: 16, padding: 20 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>Skill: {selectedSkill.name}</div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button onClick={() => handleScanSkill(selectedSkill.name)} style={{ padding: '6px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: C.glowBlue, color: C.blue, border: '1px solid rgba(59,130,246,0.3)' }}>Re-scan</button>
                    {selectedSkill.source !== 'imported' && <button onClick={() => handleDeleteSkill(selectedSkill.name)} style={{ padding: '6px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: 'rgba(239,68,68,0.1)', color: C.red, border: '1px solid rgba(239,68,68,0.2)' }}>Delete</button>}
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                  <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8 }}><div style={{ fontSize: 11, color: C.txtMut }}>Version</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{selectedSkill.version}</div></div>
                  <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8 }}><div style={{ fontSize: 11, color: C.txtMut }}>Trust Level</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{selectedSkill.trust_level}</div></div>
                  <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8 }}><div style={{ fontSize: 11, color: C.txtMut }}>AEGIS Approved</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4, color: selectedSkill.aegis_approved ? C.green : C.red }}>{selectedSkill.aegis_approved ? 'Yes' : 'No'}</div></div>
                  <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8 }}><div style={{ fontSize: 11, color: C.txtMut }}>Source</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{selectedSkill.source}</div></div>
                  <div style={{ padding: '10px 14px', background: C.bg2, borderRadius: 8, gridColumn: '1 / -1' }}><div style={{ fontSize: 11, color: C.txtMut }}>Tags</div><div style={{ fontSize: 14, fontWeight: 500, marginTop: 4 }}>{selectedSkill.tags?.join(', ') || 'None'}</div></div>
                </div>

                {/* Assign to Role */}
                <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 16 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>Assign to Role</div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <select value={assignSkillRole} onChange={e => setAssignSkillRole(e.target.value)} style={{ flex: 1, padding: '10px 12px', background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 8, color: C.txt, fontSize: 14 }}>
                      <option value="">Select a role...</option>
                      {roles.map(r => <option key={r.name} value={r.name}>{r.name}</option>)}
                    </select>
                    <button onClick={() => assignSkillRole && handleAssignSkill(selectedSkill.name, assignSkillRole)} disabled={!assignSkillRole} style={{ padding: '10px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: assignSkillRole ? 'pointer' : 'not-allowed', background: assignSkillRole ? C.green : C.bg3, color: assignSkillRole ? C.bg0 : C.txtMut, border: 'none' }}>Assign</button>
                  </div>
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
                  <button onClick={() => handleViewPlan(s.session_id)} style={{ padding: '8px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer', background: C.bg2, color: C.txtSec, border: `1px solid ${C.border}` }}>Review First</button>
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

          {/* Chat Panel — WebSocket streaming (full Orion pipeline) */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <div style={{ padding: '16px 20px', borderBottom: `1px solid ${C.border}` }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>Talk to Orion</div>
                  <div style={{ fontSize: 12, color: C.txtMut }}>Full pipeline — streaming, memory, NLA</div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: wsConnected ? C.green : C.amber }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: wsConnected ? C.green : C.amber, boxShadow: wsConnected ? `0 0 6px ${C.green}` : 'none' }} />
                  {wsConnected ? 'Connected' : 'Reconnecting...'}
                </div>
              </div>
            </div>
            <div style={{ flex: 1, padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {chatMessages.map((m, i) => {
                const isUser = m.role === 'user'
                const isError = m.type === 'error'
                const isStreaming = m.type === 'streaming'
                const isCouncil = m.type === 'council'
                const isStatus = m.type === 'status'
                const bg = isUser ? C.blue : isError ? 'rgba(239,68,68,0.12)' : isCouncil ? 'rgba(168,85,247,0.1)' : isStatus ? 'rgba(245,158,11,0.08)' : isStreaming ? 'rgba(52,211,153,0.06)' : C.bg2
                const border = isError ? 'rgba(239,68,68,0.25)' : isCouncil ? 'rgba(168,85,247,0.25)' : isStatus ? 'rgba(245,158,11,0.2)' : 'transparent'
                return (
                  <div key={i} style={{ maxWidth: '90%', padding: '10px 14px', borderRadius: 12, fontSize: 13, lineHeight: 1.55, whiteSpace: 'pre-wrap', alignSelf: isUser ? 'flex-end' : 'flex-start', background: bg, border: `1px solid ${border}`, borderBottomRightRadius: isUser ? 4 : 12, borderBottomLeftRadius: !isUser ? 4 : 12 }}>
                    {!isUser && m.type && m.type !== 'complete' && (
                      <div style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: isError ? C.red : isCouncil ? C.purple : isStatus ? C.amber : C.green, marginBottom: 4 }}>
                        {isError ? 'Error' : isCouncil ? 'Council' : isStatus ? 'Status' : isStreaming ? 'Streaming' : m.type}
                      </div>
                    )}
                    {m.text}
                    {isStreaming && <span style={{ animation: 'pulse 1s ease-in-out infinite', color: C.txtMut }}> ▊</span>}
                  </div>
                )
              })}
              {chatLoading && !streamingRef.current && (
                <div style={{ maxWidth: '90%', padding: '10px 14px', borderRadius: 12, fontSize: 13, color: C.txtMut, background: C.bg2, borderBottomLeftRadius: 4, alignSelf: 'flex-start', animation: 'pulse 1.5s ease-in-out infinite' }}>Orion is thinking...</div>
              )}
            </div>
            <div style={{ padding: '12px 16px', borderTop: `1px solid ${C.border}`, display: 'flex', gap: 8, alignItems: 'flex-end' }}>
              <textarea value={chatInput} onChange={e => setChatInput(e.target.value)} onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey && chatInput.trim()) {
                  e.preventDefault()
                  sendChat(chatInput)
                }
              }} placeholder={wsConnected ? 'Ask Orion something...' : 'Waiting for connection...'} rows={2} style={{ flex: 1, background: C.bg2, border: `1px solid ${C.border}`, borderRadius: 12, padding: '12px 14px', color: C.txt, fontSize: 14, fontFamily: 'inherit', resize: 'none' }} />
              <button onClick={() => sendChat(chatInput)} disabled={chatLoading || !chatInput.trim()} style={{ padding: '12px 16px', borderRadius: 12, border: 'none', background: chatLoading || !chatInput.trim() ? C.bg3 : C.blue, color: chatLoading || !chatInput.trim() ? C.txtMut : '#fff', cursor: chatLoading || !chatInput.trim() ? 'not-allowed' : 'pointer', fontSize: 16, fontWeight: 700, flexShrink: 0 }}>↑</button>
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
