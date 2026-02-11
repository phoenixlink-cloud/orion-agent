'use client'

import React, { useState, useEffect, useRef, useCallback } from 'react'
import Link from 'next/link'
import Button from './Button'

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8001/ws/chat'
const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

interface Message {
  role: 'user' | 'orion' | 'system'
  content: string
  timestamp: Date
  type?: 'routing' | 'status' | 'complete' | 'escalation' | 'error' | 'streaming' | 'council'
  meta?: Record<string, unknown>
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'orion',
      content: "I'm here to help you think — safely. What would you like to work on?",
      timestamp: new Date(),
    },
  ])
  const [input, setInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [workspace, setWorkspace] = useState('')
  const [mode, setMode] = useState('safe')
  const wsRef = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const reconnectTimer = useRef<NodeJS.Timeout | null>(null)
  const streamingRef = useRef<string>('')  // Accumulates streaming tokens

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, scrollToBottom])

  // Load workspace from settings on mount
  useEffect(() => {
    fetch(`${API_BASE}/api/settings`)
      .then(r => r.ok ? r.json() : null)
      .then(s => {
        if (s?.workspace) setWorkspace(s.workspace)
        if (s?.default_mode) setMode(s.default_mode)
      })
      .catch(() => {})
  }, [])

  // WebSocket connection with auto-reconnect
  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(WS_URL)

      ws.onopen = () => {
        setIsConnected(true)
        if (reconnectTimer.current) {
          clearTimeout(reconnectTimer.current)
          reconnectTimer.current = null
        }
      }

      ws.onclose = () => {
        // Only update state if this is still the active WebSocket
        // (prevents React Strict Mode race where stale WS1.onclose overwrites active WS2)
        if (wsRef.current === ws) {
          setIsConnected(false)
          wsRef.current = null
          reconnectTimer.current = setTimeout(connectWs, 3000)
        }
      }

      ws.onerror = () => {
        if (wsRef.current === ws) {
          setIsConnected(false)
        }
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          handleServerMessage(data)
        } catch {
          // Non-JSON message
          addOrionMessage(event.data, 'complete')
        }
      }

      wsRef.current = ws
    } catch {
      setIsConnected(false)
      reconnectTimer.current = setTimeout(connectWs, 3000)
    }
  }, [])

  useEffect(() => {
    connectWs()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connectWs])

  const addOrionMessage = (content: string, type?: string, meta?: Record<string, unknown>) => {
    setMessages(prev => [...prev, {
      role: 'orion' as const,
      content,
      timestamp: new Date(),
      type: type as Message['type'],
      meta,
    }])
  }

  const handleServerMessage = (data: Record<string, unknown>) => {
    const msgType = data.type as string

    switch (msgType) {
      case 'routing': {
        // Internal routing info — don't show to user, just log for debugging
        console.debug('[Orion Scout]', data.route, data.reasoning)
        break
      }
      case 'status':
        addOrionMessage(data.message as string, 'status')
        break
      case 'token': {
        // Token-by-token streaming: accumulate and update the last message
        const token = data.content as string
        streamingRef.current += token
        const currentText = streamingRef.current
        setMessages(prev => {
          const last = prev[prev.length - 1]
          if (last && last.type === 'streaming') {
            // Update the existing streaming message
            return [...prev.slice(0, -1), { ...last, content: currentText }]
          } else {
            // Create a new streaming message
            return [...prev, {
              role: 'orion' as const,
              content: currentText,
              timestamp: new Date(),
              type: 'streaming' as const,
            }]
          }
        })
        break
      }
      case 'council_phase': {
        const phase = data.phase as string
        const message = data.message as string
        addOrionMessage(message, 'council')
        break
      }
      case 'complete': {
        setIsProcessing(false)
        // If we were streaming, finalize the streaming message
        if (streamingRef.current) {
          setMessages(prev => {
            const last = prev[prev.length - 1]
            if (last && last.type === 'streaming') {
              return [...prev.slice(0, -1), { ...last, type: 'complete' as const, meta: data }]
            }
            return prev
          })
          streamingRef.current = ''
        } else {
          addOrionMessage(
            (data.response as string) || 'Done.',
            'complete',
            data
          )
        }
        break
      }
      case 'feedback_ack':
        // Silent acknowledgment — could show a toast
        break
      case 'escalation':
        setIsProcessing(false)
        addOrionMessage(
          `ESCALATION: ${data.message}\nReason: ${data.reason}`,
          'escalation',
          data
        )
        break
      case 'error':
        setIsProcessing(false)
        streamingRef.current = ''
        addOrionMessage(`Error: ${data.message}`, 'error')
        break
      default:
        setIsProcessing(false)
        addOrionMessage(JSON.stringify(data, null, 2), 'complete')
    }
  }

  const handleSend = () => {
    if (!input.trim()) return

    const userMessage: Message = {
      role: 'user',
      content: input,
      timestamp: new Date(),
    }

    setMessages((prev) => [...prev, userMessage])
    const currentInput = input
    setInput('')

    // Handle local commands FIRST — these don't need connection or workspace
    if (currentInput.trim() === '/help') {
      addOrionMessage(
        `Available commands:\n\n` +
        `WORKSPACE\n` +
        `  /workspace <path>  — Set your project folder\n` +
        `  /mode safe|pro|project  — Change safety mode\n\n` +
        `SAFETY MODES\n` +
        `  safe  — Orion asks before every change (default)\n` +
        `  pro  — Auto-approve safe edits, ask for risky ones\n` +
        `  project  — Full autonomy within your project\n\n` +
        `Or just type your question in plain English!\n` +
        `Example: "Create a hello world Flask app"\n` +
        `Example: "Explain what main.py does"\n\n` +
        `For full settings, click Settings in the top right.`,
        'status'
      )
      return
    }

    if (currentInput.startsWith('/workspace ')) {
      const newWs = currentInput.replace('/workspace ', '').trim()
      setWorkspace(newWs)
      addOrionMessage(`Workspace set to: ${newWs}`, 'status')
      fetch(`${API_BASE}/api/settings/workspace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newWs),
      }).catch(() => {})
      return
    }

    if (currentInput.startsWith('/mode ')) {
      const newMode = currentInput.replace('/mode ', '').trim()
      if (['safe', 'pro', 'project'].includes(newMode)) {
        setMode(newMode)
        addOrionMessage(`Mode set to: ${newMode}`, 'status')
        fetch(`${API_BASE}/api/settings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ default_mode: newMode }),
        }).catch(() => {})
      } else {
        addOrionMessage('Invalid mode. Use: safe, pro, or project', 'error')
      }
      return
    }

    // Server-bound messages require connection + workspace
    if (!isConnected || !wsRef.current) {
      addOrionMessage(
        `Not connected to Orion API. Start the server with: uvicorn orion.api.server:app --port 8001`,
        'error'
      )
      return
    }

    if (!workspace) {
      addOrionMessage(
        'No workspace set. Use /workspace <path> or set it in Settings.',
        'error'
      )
      return
    }

    setIsProcessing(true)

    wsRef.current.send(JSON.stringify({
      message: currentInput,
      workspace: workspace,
      mode: mode,
    }))
  }

  const getMessageStyle = (msg: Message) => {
    if (msg.role === 'user') return { bg: 'rgba(6, 9, 19, 0.9)', border: 'var(--line)' }
    switch (msg.type) {
      case 'routing': return { bg: 'rgba(34, 211, 238, 0.08)', border: 'rgba(34, 211, 238, 0.3)' }
      case 'status': return { bg: 'rgba(251, 191, 36, 0.08)', border: 'rgba(251, 191, 36, 0.3)' }
      case 'error': return { bg: 'rgba(248, 113, 113, 0.08)', border: 'rgba(248, 113, 113, 0.3)' }
      case 'escalation': return { bg: 'rgba(251, 146, 60, 0.08)', border: 'rgba(251, 146, 60, 0.3)' }
      case 'complete': return { bg: 'rgba(52, 211, 153, 0.08)', border: 'rgba(52, 211, 153, 0.3)' }
      case 'streaming': return { bg: 'rgba(52, 211, 153, 0.05)', border: 'rgba(52, 211, 153, 0.2)' }
      case 'council': return { bg: 'rgba(168, 85, 247, 0.08)', border: 'rgba(168, 85, 247, 0.3)' }
      default: return { bg: 'var(--tile)', border: 'var(--line)' }
    }
  }

  const getMessageLabel = (msg: Message) => {
    if (msg.role === 'user') return 'You'
    switch (msg.type) {
      case 'routing': return 'Scout'
      case 'status': return 'Orion'
      case 'error': return 'Error'
      case 'escalation': return 'AEGIS'
      case 'streaming': return 'Orion'
      case 'council': return 'Council'
      default: return 'Orion'
    }
  }

  return (
    <div
      style={{
        maxWidth: 900,
        margin: '0 auto',
        padding: '32px 20px',
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
        }}
      >
        <div>
          <div style={{ fontSize: 28, fontWeight: 500, color: 'var(--text)' }}>
            Ask Orion
          </div>
          <div style={{ fontSize: 14, color: 'var(--muted)', marginTop: 4 }}>
            Governed AI Assistant
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <Link href="/settings">
            <Button variant="secondary">Settings</Button>
          </Link>
          <Link href="/">
            <Button variant="secondary">Home</Button>
          </Link>
        </div>
      </div>

      {/* Connection + Workspace Status */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '12px 16px',
          background: isConnected
            ? 'rgba(100, 255, 100, 0.1)'
            : 'rgba(255, 200, 100, 0.1)',
          border: `1px solid ${isConnected ? 'rgba(100, 255, 100, 0.3)' : 'rgba(255, 200, 100, 0.3)'}`,
          borderRadius: 'var(--r-md)',
          marginBottom: 20,
          flexWrap: 'wrap',
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: isConnected ? '#64ff64' : '#ffcc66',
          }}
        />
        <span style={{ fontSize: 14, color: 'var(--text)' }}>
          {isConnected ? 'Connected to Orion API' : 'Not connected — Start API server'}
        </span>
        {isConnected && (
          <span style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 'auto' }}>
            {workspace ? `Workspace: ${workspace}` : 'No workspace set'}
            {' | '}
            Mode: {mode}
          </span>
        )}
        {!isConnected && (
          <span style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 'auto' }}>
            <code style={{ color: 'var(--glow)' }}>uvicorn api.server:app --port 8000</code>
          </span>
        )}
      </div>

      {/* Messages */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          marginBottom: 20,
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {messages.map((msg, i) => {
          const style = getMessageStyle(msg)
          return (
            <div
              key={i}
              style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
              }}
            >
              <div
                style={{
                  maxWidth: '85%',
                  padding: '14px 18px',
                  borderRadius: 'var(--r-md)',
                  background: style.bg,
                  border: `1px solid ${style.border}`,
                }}
              >
                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    textTransform: 'uppercase' as const,
                    letterSpacing: '0.5px',
                    color: 'var(--muted)',
                    marginBottom: 6,
                  }}
                >
                  {getMessageLabel(msg)}
                </div>
                <div style={{
                  fontSize: 14,
                  color: 'var(--text)',
                  lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                  fontFamily: msg.type === 'routing' ? 'monospace' : 'inherit',
                }}>
                  {msg.content}
                </div>
              </div>
            </div>
          )
        })}

        {/* Processing indicator */}
        {isProcessing && (
          <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
            <div
              style={{
                padding: '14px 18px',
                borderRadius: 'var(--r-md)',
                background: 'var(--tile)',
                border: '1px solid var(--line)',
              }}
            >
              <div style={{ fontSize: 14, color: 'var(--muted)' }}>
                Orion is thinking...
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{ display: 'flex', gap: 12 }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !isProcessing && handleSend()}
          placeholder={isProcessing ? 'Orion is processing...' : 'Ask Orion anything...'}
          disabled={isProcessing}
          style={{
            flex: 1,
            padding: '14px 18px',
            fontSize: 15,
            background: 'var(--tile)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--r-md)',
            color: 'var(--text)',
            outline: 'none',
            opacity: isProcessing ? 0.6 : 1,
          }}
        />
        <button
          onClick={handleSend}
          disabled={isProcessing || !input.trim()}
          style={{
            padding: '14px 24px', fontSize: 15, fontWeight: 600,
            background: isProcessing || !input.trim() ? 'rgba(159,214,255,0.2)' : 'var(--glow)',
            color: isProcessing || !input.trim() ? 'var(--muted)' : '#000',
            border: 'none', borderRadius: 'var(--r-md)', cursor: isProcessing ? 'not-allowed' : 'pointer',
          }}
        >
          {isProcessing ? 'Thinking...' : 'Send'}
        </button>
      </div>

      {/* Quick Commands */}
      <div style={{ marginTop: 16 }}>
        <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
          Quick commands:
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {['/help', '/mode safe', '/mode pro', '/mode project'].map((cmd) => (
            <button
              key={cmd}
              onClick={() => { setInput(cmd); }}
              style={{
                padding: '6px 12px',
                fontSize: 13,
                background: 'var(--tile)',
                border: '1px solid var(--line)',
                borderRadius: 999,
                color: 'var(--glow)',
                cursor: 'pointer',
              }}
            >
              {cmd}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
