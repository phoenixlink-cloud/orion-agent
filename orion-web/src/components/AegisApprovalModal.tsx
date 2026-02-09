'use client'

import React, { useState, useEffect, useCallback, useRef } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface PendingApproval {
  id: string
  prompt: string
  age_seconds: number
}

export default function AegisApprovalModal() {
  const [pending, setPending] = useState<PendingApproval[]>([])
  const [responding, setResponding] = useState<string | null>(null)
  const pollRef = useRef<NodeJS.Timeout | null>(null)

  const pollPending = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/aegis/pending`)
      if (res.ok) {
        const data = await res.json()
        setPending(data.pending || [])
      }
    } catch {
      // Server not available — silently ignore
    }
  }, [])

  useEffect(() => {
    // Poll every 1 second for pending approvals
    pollPending()
    pollRef.current = setInterval(pollPending, 1000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [pollPending])

  const respond = useCallback(async (id: string, approved: boolean) => {
    setResponding(id)
    try {
      await fetch(`${API_BASE}/api/aegis/respond/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved }),
      })
      // Remove from local state immediately
      setPending(prev => prev.filter(p => p.id !== id))
    } catch {
      // Will be cleaned up on next poll
    } finally {
      setResponding(null)
    }
  }, [])

  if (pending.length === 0) return null

  const current = pending[0]

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        {/* Header */}
        <div style={headerStyle}>
          <span style={{ fontSize: 22 }}>⚠</span>
          <span style={headerTextStyle}>AEGIS APPROVAL REQUIRED</span>
        </div>

        {/* Body */}
        <div style={bodyStyle}>
          <p style={labelStyle}>
            Orion is requesting permission to perform an external action:
          </p>
          <pre style={promptStyle}>{current.prompt}</pre>
          <p style={timerStyle}>
            Waiting for your decision ({Math.round(current.age_seconds)}s)
            {current.age_seconds > 90 && (
              <span style={{ color: '#ff6b6b' }}>
                {' '}— auto-denies in {Math.round(120 - current.age_seconds)}s
              </span>
            )}
          </p>
        </div>

        {/* Actions */}
        <div style={actionsStyle}>
          <button
            style={denyButtonStyle}
            onClick={() => respond(current.id, false)}
            disabled={responding === current.id}
          >
            ✗ Deny
          </button>
          <button
            style={approveButtonStyle}
            onClick={() => respond(current.id, true)}
            disabled={responding === current.id}
          >
            ✓ Approve
          </button>
        </div>

        {pending.length > 1 && (
          <p style={queueStyle}>
            +{pending.length - 1} more approval{pending.length > 2 ? 's' : ''} waiting
          </p>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Styles (inline — matches Orion design tokens)
// ---------------------------------------------------------------------------

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: 'rgba(0, 0, 0, 0.75)',
  backdropFilter: 'blur(6px)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 10000,
  animation: 'fadeIn 200ms ease',
}

const modalStyle: React.CSSProperties = {
  background: 'linear-gradient(135deg, #0a1628, #091429)',
  border: '1px solid rgba(255, 180, 50, 0.4)',
  borderRadius: 14,
  padding: 0,
  maxWidth: 520,
  width: '90vw',
  boxShadow: '0 0 60px rgba(255, 180, 50, 0.15), 0 4px 32px rgba(0,0,0,0.5)',
  overflow: 'hidden',
}

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  padding: '16px 24px',
  background: 'rgba(255, 180, 50, 0.08)',
  borderBottom: '1px solid rgba(255, 180, 50, 0.2)',
}

const headerTextStyle: React.CSSProperties = {
  fontSize: 14,
  fontWeight: 600,
  letterSpacing: 1.5,
  color: '#ffb432',
  textTransform: 'uppercase' as const,
}

const bodyStyle: React.CSSProperties = {
  padding: '20px 24px',
}

const labelStyle: React.CSSProperties = {
  fontSize: 14,
  color: '#AFC3D6',
  marginBottom: 12,
}

const promptStyle: React.CSSProperties = {
  background: 'rgba(0,0,0,0.35)',
  border: '1px solid rgba(159, 214, 255, 0.12)',
  borderRadius: 8,
  padding: '14px 16px',
  fontSize: 13,
  lineHeight: 1.6,
  color: '#EAF4FF',
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
  maxHeight: 200,
  overflowY: 'auto',
}

const timerStyle: React.CSSProperties = {
  fontSize: 12,
  color: '#7a8ea0',
  marginTop: 12,
}

const actionsStyle: React.CSSProperties = {
  display: 'flex',
  gap: 12,
  padding: '0 24px 20px',
  justifyContent: 'flex-end',
}

const buttonBase: React.CSSProperties = {
  padding: '10px 24px',
  borderRadius: 8,
  fontSize: 14,
  fontWeight: 600,
  cursor: 'pointer',
  border: 'none',
  transition: 'all 150ms ease',
}

const denyButtonStyle: React.CSSProperties = {
  ...buttonBase,
  background: 'rgba(255, 80, 80, 0.15)',
  color: '#ff6b6b',
  border: '1px solid rgba(255, 80, 80, 0.3)',
}

const approveButtonStyle: React.CSSProperties = {
  ...buttonBase,
  background: 'rgba(80, 220, 100, 0.15)',
  color: '#50dc64',
  border: '1px solid rgba(80, 220, 100, 0.3)',
}

const queueStyle: React.CSSProperties = {
  fontSize: 12,
  color: '#7a8ea0',
  textAlign: 'center',
  padding: '0 24px 16px',
}
