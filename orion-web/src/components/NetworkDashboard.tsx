'use client'

import React, { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import Button from './Button'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ProxyStatus {
  enforce: boolean
  content_inspection: boolean
  dns_filtering: boolean
  proxy_port: number
  global_rate_limit_rpm: number
  hardcoded_domain_count: number
  user_domain_count: number
}

interface DomainRule {
  domain: string
  allow_write: boolean
  protocols: string[]
  rate_limit_rpm: number
  added_by: string
  description: string
}

interface AuditEntry {
  timestamp: string
  event_type: string
  method: string
  url: string
  hostname: string
  status_code: number
  blocked_reason: string
  rule_matched: string
  duration_ms: number
}

interface AuditData {
  stats: Record<string, number>
  entries: AuditEntry[]
}

interface GoogleService {
  domain: string
  name: string
  description: string
  risk: 'low' | 'medium' | 'high'
  enabled: boolean
}

interface GoogleServicesData {
  services: GoogleService[]
  enabled_count: number
  total_count: number
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusBadge({ active, label }: { active: boolean; label: string }) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 14px',
        background: 'var(--tile)',
        border: '1px solid var(--line)',
        borderRadius: 999,
        fontSize: 13,
        fontWeight: 500,
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: active ? '#4ade80' : '#f87171',
          boxShadow: active ? '0 0 8px rgba(74,222,128,0.5)' : '0 0 8px rgba(248,113,113,0.4)',
        }}
      />
      <span style={{ color: active ? '#4ade80' : '#f87171' }}>{label}</span>
    </div>
  )
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div
      style={{
        padding: '20px 24px',
        background: 'var(--tile)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)',
        flex: '1 1 140px',
      }}
    >
      <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 600, color: 'var(--glow)' }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

function DomainRow({
  rule,
  removable,
  onRemove,
}: {
  rule: DomainRule
  removable: boolean
  onRemove?: (domain: string) => void
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        background: 'var(--tile)',
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-sm)',
        marginBottom: 8,
        fontSize: 14,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1 }}>
        <span
          style={{
            padding: '2px 8px',
            borderRadius: 6,
            fontSize: 11,
            fontWeight: 600,
            background: rule.added_by === 'system' ? 'rgba(159,214,255,0.15)' : 'rgba(74,222,128,0.15)',
            color: rule.added_by === 'system' ? 'var(--glow)' : '#4ade80',
          }}
        >
          {rule.added_by === 'system' ? 'SYSTEM' : 'USER'}
        </span>
        <span style={{ fontWeight: 500, color: 'var(--text)' }}>{rule.domain}</span>
        {rule.description && (
          <span style={{ color: 'var(--muted)', fontSize: 12 }}>{rule.description}</span>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span
          style={{
            fontSize: 11,
            padding: '2px 6px',
            borderRadius: 4,
            background: rule.allow_write ? 'rgba(251,191,36,0.15)' : 'rgba(159,214,255,0.1)',
            color: rule.allow_write ? '#fbbf24' : 'var(--muted)',
          }}
        >
          {rule.allow_write ? 'READ+WRITE' : 'READ ONLY'}
        </span>
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>{rule.rate_limit_rpm} rpm</span>
        {removable && onRemove && (
          <button
            onClick={() => onRemove(rule.domain)}
            style={{
              background: 'rgba(248,113,113,0.15)',
              border: '1px solid rgba(248,113,113,0.3)',
              borderRadius: 6,
              color: '#f87171',
              fontSize: 12,
              padding: '4px 10px',
              cursor: 'pointer',
              transition: 'all 200ms ease',
            }}
          >
            Remove
          </button>
        )}
      </div>
    </div>
  )
}

function AuditRow({ entry }: { entry: AuditEntry }) {
  const isBlocked = entry.event_type === 'blocked'
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 16px',
        background: 'var(--tile)',
        border: `1px solid ${isBlocked ? 'rgba(248,113,113,0.25)' : 'var(--line)'}`,
        borderRadius: 'var(--r-sm)',
        marginBottom: 6,
        fontSize: 13,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: isBlocked ? '#f87171' : '#4ade80',
          flexShrink: 0,
        }}
      />
      <span style={{ color: 'var(--muted)', fontSize: 12, minWidth: 60 }}>
        {entry.method}
      </span>
      <span style={{ color: 'var(--text)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {entry.hostname}
      </span>
      {isBlocked && entry.blocked_reason && (
        <span style={{ color: '#f87171', fontSize: 11 }}>{entry.blocked_reason}</span>
      )}
      <span style={{ color: 'var(--muted)', fontSize: 11 }}>
        {entry.duration_ms > 0 ? `${Math.round(entry.duration_ms)}ms` : '—'}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Add Domain Form
// ---------------------------------------------------------------------------

function AddDomainForm({ onAdd }: { onAdd: (domain: string, allowWrite: boolean, desc: string) => void }) {
  const [domain, setDomain] = useState('')
  const [allowWrite, setAllowWrite] = useState(false)
  const [desc, setDesc] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const d = domain.trim()
    if (!d) {
      setError('Domain is required')
      return
    }
    if (!/^[a-zA-Z0-9*][\w.-]*\.[a-zA-Z]{2,}$/.test(d)) {
      setError('Invalid domain format')
      return
    }
    onAdd(d, allowWrite, desc.trim())
    setDomain('')
    setDesc('')
    setAllowWrite(false)
    setError('')
  }

  const inputStyle: React.CSSProperties = {
    background: 'rgba(6, 9, 19, 0.9)',
    border: '1px solid var(--line)',
    borderRadius: 'var(--r-sm)',
    padding: '10px 14px',
    fontSize: 14,
    color: 'var(--text)',
    outline: 'none',
    width: '100%',
  }

  return (
    <form onSubmit={handleSubmit} style={{ marginBottom: 24 }}>
      <div style={{ display: 'flex', gap: 10, marginBottom: 10 }}>
        <input
          type="text"
          value={domain}
          onChange={(e) => { setDomain(e.target.value); setError('') }}
          placeholder="e.g. api.example.com"
          style={{ ...inputStyle, flex: 2 }}
        />
        <input
          type="text"
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          placeholder="Description (optional)"
          style={{ ...inputStyle, flex: 1 }}
        />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--muted)', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={allowWrite}
            onChange={(e) => setAllowWrite(e.target.checked)}
            style={{ accentColor: 'var(--glow)' }}
          />
          Allow write operations (POST/PUT/DELETE)
        </label>
        <button
          type="submit"
          style={{
            background: 'var(--tile)',
            border: '1px solid var(--line)',
            borderRadius: 999,
            color: 'var(--glow)',
            fontSize: 13,
            fontWeight: 500,
            padding: '8px 20px',
            cursor: 'pointer',
            transition: 'all 200ms ease',
            marginLeft: 'auto',
          }}
        >
          Add Domain
        </button>
      </div>
      {error && (
        <div style={{ color: '#f87171', fontSize: 12, marginTop: 8 }}>{error}</div>
      )}
    </form>
  )
}

// ---------------------------------------------------------------------------
// Main Dashboard
// ---------------------------------------------------------------------------

export default function NetworkDashboard() {
  const [status, setStatus] = useState<ProxyStatus | null>(null)
  const [hardcoded, setHardcoded] = useState<DomainRule[]>([])
  const [userDomains, setUserDomains] = useState<DomainRule[]>([])
  const [audit, setAudit] = useState<AuditData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [googleServices, setGoogleServices] = useState<GoogleServicesData | null>(null)
  const [tab, setTab] = useState<'whitelist' | 'services' | 'audit' | 'security'>('whitelist')

  const fetchData = useCallback(async () => {
    try {
      const [statusRes, whitelistRes, auditRes, servicesRes] = await Promise.all([
        fetch(`${API_BASE}/api/egress/status`),
        fetch(`${API_BASE}/api/egress/whitelist`),
        fetch(`${API_BASE}/api/egress/audit?limit=50`),
        fetch(`${API_BASE}/api/egress/google-services`),
      ])

      if (statusRes.ok) setStatus(await statusRes.json())
      if (whitelistRes.ok) {
        const wl = await whitelistRes.json()
        setHardcoded(wl.hardcoded_domains || [])
        setUserDomains(wl.user_domains || [])
      }
      if (auditRes.ok) setAudit(await auditRes.json())
      if (servicesRes.ok) setGoogleServices(await servicesRes.json())

      setError('')
    } catch {
      setError('Could not connect to Orion API. Make sure the backend is running.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [fetchData])

  const handleAddDomain = async (domain: string, allowWrite: boolean, description: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/egress/whitelist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain, allow_write: allowWrite, description }),
      })
      if (!res.ok) {
        const data = await res.json()
        setError(data.detail || 'Failed to add domain')
        return
      }
      await fetchData()
    } catch {
      setError('Failed to add domain')
    }
  }

  const handleRemoveDomain = async (domain: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/egress/whitelist/${encodeURIComponent(domain)}`, {
        method: 'DELETE',
      })
      if (!res.ok) {
        const data = await res.json()
        setError(data.detail || 'Failed to remove domain')
        return
      }
      await fetchData()
    } catch {
      setError('Failed to remove domain')
    }
  }

  const sectionHeader: React.CSSProperties = {
    fontSize: 20,
    fontWeight: 500,
    color: 'var(--text)',
    marginBottom: 20,
  }

  const tabStyle = (active: boolean): React.CSSProperties => ({
    padding: '10px 20px',
    fontSize: 14,
    fontWeight: 500,
    color: active ? 'var(--glow)' : 'var(--muted)',
    background: active ? 'rgba(159,214,255,0.1)' : 'transparent',
    border: `1px solid ${active ? 'rgba(159,214,255,0.3)' : 'var(--line)'}`,
    borderRadius: 999,
    cursor: 'pointer',
    transition: 'all 200ms ease',
  })

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: '56px 20px' }}>
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
          Network
        </div>
        <div style={{ fontSize: 18, color: 'var(--muted)', marginBottom: 24 }}>
          Egress Proxy — The Narrow Door
        </div>
        <div style={{ fontSize: 15, color: 'var(--text)', lineHeight: 1.7, opacity: 0.9 }}>
          All outbound network traffic from the Docker sandbox passes through the egress proxy.
          Only whitelisted domains are allowed. This dashboard lets you manage the whitelist,
          monitor traffic, and review the security posture of the network layer.
        </div>
      </div>

      {/* Status Badges */}
      {status && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 32, flexWrap: 'wrap' }}>
          <StatusBadge active={status.enforce} label={status.enforce ? 'Enforcing' : 'Permissive'} />
          <StatusBadge active={status.content_inspection} label="Content Inspection" />
          <StatusBadge active={status.dns_filtering} label="DNS Filtering" />
        </div>
      )}

      {/* Stats Row */}
      {status && (
        <div style={{ display: 'flex', gap: 16, marginBottom: 32, flexWrap: 'wrap' }}>
          <StatCard label="System Domains" value={status.hardcoded_domain_count} sub="LLM endpoints (immutable)" />
          <StatCard label="User Domains" value={status.user_domain_count} sub="Custom whitelist" />
          <StatCard label="Proxy Port" value={status.proxy_port} />
          <StatCard label="Rate Limit" value={`${status.global_rate_limit_rpm}`} sub="requests/min" />
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div
          style={{
            padding: '12px 16px',
            background: 'rgba(248,113,113,0.1)',
            border: '1px solid rgba(248,113,113,0.3)',
            borderRadius: 'var(--r-sm)',
            color: '#f87171',
            fontSize: 14,
            marginBottom: 24,
          }}
        >
          {error}
        </div>
      )}

      {/* Tab Navigation */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 32 }}>
        <button style={tabStyle(tab === 'whitelist')} onClick={() => setTab('whitelist')}>
          Domain Whitelist
        </button>
        <button style={tabStyle(tab === 'services')} onClick={() => setTab('services')}>
          Google Services
        </button>
        <button style={tabStyle(tab === 'audit')} onClick={() => setTab('audit')}>
          Audit Log
        </button>
        <button style={tabStyle(tab === 'security')} onClick={() => setTab('security')}>
          Security Layers
        </button>
      </div>

      {/* Whitelist Tab */}
      {tab === 'whitelist' && (
        <div style={{ marginBottom: 48 }}>
          <div style={sectionHeader}>Add Domain</div>
          <AddDomainForm onAdd={handleAddDomain} />

          {userDomains.length > 0 && (
            <>
              <div style={sectionHeader}>User Whitelist ({userDomains.length})</div>
              {userDomains.map((r) => (
                <DomainRow key={r.domain} rule={r} removable onRemove={handleRemoveDomain} />
              ))}
            </>
          )}

          <div style={{ ...sectionHeader, marginTop: 32 }}>
            System Domains ({hardcoded.length})
          </div>
          <div style={{ fontSize: 13, color: 'var(--muted)', marginBottom: 16 }}>
            These domains are hardcoded for LLM access and cannot be removed.
          </div>
          {hardcoded.map((r) => (
            <DomainRow key={r.domain} rule={r} removable={false} />
          ))}

          {loading && hardcoded.length === 0 && (
            <div style={{ color: 'var(--muted)', fontSize: 14, textAlign: 'center', padding: 40 }}>
              Loading whitelist...
            </div>
          )}
        </div>
      )}

      {/* Google Services Tab */}
      {tab === 'services' && (
        <div style={{ marginBottom: 48 }}>
          <div style={sectionHeader}>Google Service Access</div>
          <div style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.7, marginBottom: 24 }}>
            By default, all Google services except LLM endpoints are blocked (AEGIS Invariant 7).
            Enable individual services below. Each toggle is an explicit, conscious decision
            recorded in the host-side AEGIS configuration. Orion cannot modify these settings.
          </div>

          {googleServices && googleServices.services.length > 0 ? (
            <>
              <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
                <StatCard
                  label="Enabled Services"
                  value={googleServices.enabled_count}
                  sub={`of ${googleServices.total_count} available`}
                />
                <StatCard
                  label="Risk Profile"
                  value={
                    googleServices.enabled_count === 0
                      ? 'Minimal'
                      : googleServices.services.filter(s => s.enabled && s.risk === 'high').length > 0
                        ? 'Elevated'
                        : 'Moderate'
                  }
                  sub="Based on enabled services"
                />
              </div>

              {googleServices.services.map((svc) => {
                const riskColor = svc.risk === 'high' ? '#f87171' : svc.risk === 'medium' ? '#fbbf24' : '#4ade80'
                return (
                  <div
                    key={svc.domain}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '16px 20px',
                      background: 'var(--tile)',
                      border: `1px solid ${svc.enabled ? 'rgba(74,222,128,0.25)' : 'var(--line)'}`,
                      borderRadius: 'var(--r-md)',
                      marginBottom: 10,
                      transition: 'all 200ms ease',
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                        <span style={{ fontSize: 15, fontWeight: 500, color: 'var(--text)' }}>
                          {svc.name}
                        </span>
                        <span
                          style={{
                            fontSize: 10,
                            fontWeight: 600,
                            padding: '2px 8px',
                            borderRadius: 999,
                            background: `${riskColor}20`,
                            color: riskColor,
                            textTransform: 'uppercase',
                          }}
                        >
                          {svc.risk} risk
                        </span>
                      </div>
                      <div style={{ fontSize: 13, color: 'var(--muted)' }}>{svc.description}</div>
                      <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4, opacity: 0.7 }}>
                        {svc.domain}
                      </div>
                    </div>
                    <button
                      onClick={async () => {
                        try {
                          const res = await fetch(
                            `${API_BASE}/api/egress/google-services/${encodeURIComponent(svc.domain)}`,
                            {
                              method: 'PUT',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ enabled: !svc.enabled }),
                            }
                          )
                          if (res.ok) await fetchData()
                          else {
                            const data = await res.json()
                            setError(data.detail || 'Failed to toggle service')
                          }
                        } catch {
                          setError('Failed to toggle service')
                        }
                      }}
                      style={{
                        minWidth: 80,
                        padding: '8px 16px',
                        fontSize: 13,
                        fontWeight: 500,
                        border: `1px solid ${svc.enabled ? 'rgba(74,222,128,0.3)' : 'var(--line)'}`,
                        borderRadius: 999,
                        background: svc.enabled ? 'rgba(74,222,128,0.15)' : 'var(--tile)',
                        color: svc.enabled ? '#4ade80' : 'var(--muted)',
                        cursor: 'pointer',
                        transition: 'all 200ms ease',
                      }}
                    >
                      {svc.enabled ? 'Enabled' : 'Disabled'}
                    </button>
                  </div>
                )
              })}
            </>
          ) : (
            <div style={{ color: 'var(--muted)', fontSize: 14, textAlign: 'center', padding: 40 }}>
              {loading ? 'Loading services...' : 'No Google services available.'}
            </div>
          )}
        </div>
      )}

      {/* Audit Tab */}
      {tab === 'audit' && (
        <div style={{ marginBottom: 48 }}>
          {audit && audit.stats && (
            <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
              <StatCard label="Total Requests" value={audit.stats.total_requests || 0} />
              <StatCard label="Allowed" value={audit.stats.allowed || 0} />
              <StatCard label="Blocked" value={audit.stats.blocked || 0} />
              <StatCard
                label="Block Rate"
                value={
                  audit.stats.total_requests
                    ? `${Math.round(((audit.stats.blocked || 0) / audit.stats.total_requests) * 100)}%`
                    : '0%'
                }
              />
            </div>
          )}

          <div style={sectionHeader}>Recent Activity</div>
          {audit && audit.entries.length > 0 ? (
            audit.entries.map((entry, i) => <AuditRow key={i} entry={entry} />)
          ) : (
            <div style={{ color: 'var(--muted)', fontSize: 14, textAlign: 'center', padding: 40 }}>
              {loading ? 'Loading audit log...' : 'No audit entries yet. Traffic will appear here once the proxy is active.'}
            </div>
          )}
        </div>
      )}

      {/* Security Layers Tab */}
      {tab === 'security' && (
        <div style={{ marginBottom: 48 }}>
          <div style={sectionHeader}>7-Layer Defense in Depth</div>
          <div style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.7, marginBottom: 24 }}>
            Each layer operates independently. Compromising one layer does not affect the others.
          </div>

          {[
            {
              id: 'L1',
              title: 'AEGIS Configuration',
              desc: 'Governance config lives OUTSIDE the Docker sandbox. Orion can never modify its own rules, approve its own requests, or self-escalate privileges.',
              active: true,
            },
            {
              id: 'L2',
              title: 'Docker Network Isolation',
              desc: 'The sandbox container is restricted to an internal-only network. It has no direct internet access — all traffic must flow through the egress proxy.',
              active: status?.enforce ?? false,
            },
            {
              id: 'L3',
              title: 'Egress Proxy (The Narrow Door)',
              desc: 'Host-side proxy with additive domain whitelist. Only explicitly allowed domains can be reached. HTTPS-only. Full content inspection and rate limiting.',
              active: status?.enforce ?? false,
            },
            {
              id: 'L4',
              title: 'DNS Filtering',
              desc: 'Secondary DNS proxy resolves only whitelisted domains. Blocked domains receive NXDOMAIN responses, preventing even DNS-level information leakage.',
              active: status?.dns_filtering ?? false,
            },
            {
              id: 'L5',
              title: 'Approval Queue',
              desc: 'Write operations require explicit human approval before execution. Requests time out if not approved. Full audit trail of all approval decisions.',
              active: true,
            },
            {
              id: 'L6',
              title: 'Credential Isolation',
              desc: 'Google OAuth credentials stored encrypted on the host. Container receives a read-only file with access token only — no refresh capability inside the sandbox.',
              active: true,
            },
            {
              id: 'L7',
              title: 'AEGIS Invariant 7 — Network Gate',
              desc: 'Hardcoded rules block non-LLM Google services (Drive, Gmail, Calendar, YouTube, etc.). The dedicated Google account is scoped to LLM access only.',
              active: true,
            },
          ].map((layer) => (
            <div
              key={layer.id}
              style={{
                padding: '20px 24px',
                background: 'var(--tile)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--r-md)',
                marginBottom: 12,
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
                  {layer.id}
                </span>
                <span style={{ fontSize: 16, fontWeight: 500, color: 'var(--text)' }}>
                  {layer.title}
                </span>
                <span style={{ marginLeft: 'auto' }}>
                  <StatusBadge active={layer.active} label={layer.active ? 'Active' : 'Inactive'} />
                </span>
              </div>
              <div style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.6 }}>
                {layer.desc}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Navigation */}
      <div style={{ display: 'flex', gap: 12 }}>
        <Link href="/aegis">
          <Button variant="primary">AEGIS Governance</Button>
        </Link>
        <Link href="/chat">
          <Button variant="secondary">Ask Orion</Button>
        </Link>
        <Link href="/">
          <Button variant="secondary">Home</Button>
        </Link>
      </div>
    </div>
  )
}
