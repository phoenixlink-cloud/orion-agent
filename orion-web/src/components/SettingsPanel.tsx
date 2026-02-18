'use client'

import React, { useState, useEffect } from 'react'
import Link from 'next/link'
import Button from './Button'
import * as api from '@/lib/api'

// Tooltip component — hover "?" icon shows helpful explanation
function Tooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false)
  return (
    <span
      style={{ position: 'relative', display: 'inline-flex', marginLeft: 6, cursor: 'help' }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onClick={() => setShow(!show)}
    >
      <span style={{
        width: 16, height: 16, borderRadius: '50%', fontSize: 10, fontWeight: 700,
        background: 'rgba(159,214,255,0.15)', color: 'var(--glow)',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        border: '1px solid rgba(159,214,255,0.3)',
      }}>?</span>
      {show && (
        <div style={{
          position: 'absolute', bottom: '100%', left: '50%', transform: 'translateX(-50%)',
          marginBottom: 8, padding: '10px 14px', width: 260,
          background: '#1a2236', border: '1px solid var(--line)',
          borderRadius: 'var(--r-sm)', fontSize: 12, lineHeight: 1.5,
          color: 'var(--text)', boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
          zIndex: 100, pointerEvents: 'none',
        }}>
          {text}
          <div style={{
            position: 'absolute', top: '100%', left: '50%', transform: 'translateX(-50%)',
            width: 0, height: 0, borderLeft: '6px solid transparent',
            borderRight: '6px solid transparent', borderTop: '6px solid #1a2236',
          }} />
        </div>
      )}
    </span>
  )
}

// Save status toast
function SaveToast({ status, onDismiss }: { status: 'saving' | 'saved' | 'error'; onDismiss: () => void }) {
  useEffect(() => {
    if (status === 'saved') {
      const t = setTimeout(onDismiss, 3000)
      return () => clearTimeout(t)
    }
  }, [status, onDismiss])

  const config = {
    saving: { bg: 'rgba(255,200,100,0.15)', border: 'rgba(255,200,100,0.4)', color: '#ffcc66', text: 'Saving...' },
    saved: { bg: 'rgba(100,255,100,0.15)', border: 'rgba(100,255,100,0.4)', color: '#64ff64', text: 'Settings saved successfully' },
    error: { bg: 'rgba(255,100,100,0.15)', border: 'rgba(255,100,100,0.4)', color: '#ff6464', text: 'Failed to save. Check your connection.' },
  }[status]

  return (
    <div style={{
      position: 'fixed', top: 20, right: 20, zIndex: 1000,
      padding: '12px 20px', borderRadius: 'var(--r-md)',
      background: config.bg, border: `1px solid ${config.border}`,
      color: config.color, fontSize: 14, fontWeight: 500,
      boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
      animation: 'fadeIn 0.2s ease',
    }}>
      {config.text}
    </div>
  )
}

interface FeatureToggleProps {
  label: string
  description: string
  enabled: boolean
  onToggle: () => void
}

function FeatureToggle({ label, description, enabled, onToggle }: FeatureToggleProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '12px 16px',
        background: 'var(--tile)',
        borderRadius: 'var(--r-sm)',
        marginBottom: 8,
      }}
    >
      <div>
        <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>{label}</div>
        <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>{description}</div>
      </div>
      <button
        onClick={onToggle}
        style={{
          width: 44,
          height: 24,
          borderRadius: 999,
          border: 'none',
          cursor: 'pointer',
          background: enabled ? 'var(--glow)' : 'rgba(159, 214, 255, 0.2)',
          position: 'relative',
          transition: 'background 0.3s ease',
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: 18,
            height: 18,
            borderRadius: '50%',
            background: 'var(--bg0)',
            position: 'absolute',
            top: 3,
            left: enabled ? 23 : 3,
            transition: 'left 0.3s ease',
          }}
        />
      </button>
    </div>
  )
}

interface NumberInputProps {
  label: string
  description: string
  value: number
  onChange: (val: number) => void
  min?: number
  max?: number
}

function NumberInput({ label, description, value, onChange, min, max }: NumberInputProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '12px 16px',
        background: 'var(--tile)',
        borderRadius: 'var(--r-sm)',
        marginBottom: 8,
      }}
    >
      <div>
        <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>{label}</div>
        <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>{description}</div>
      </div>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        min={min}
        max={max}
        style={{
          width: 80,
          padding: '6px 10px',
          fontSize: 14,
          background: 'rgba(159, 214, 255, 0.08)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--r-sm)',
          color: 'var(--text)',
          textAlign: 'right',
        }}
      />
    </div>
  )
}

interface TextInputProps {
  label: string
  description: string
  value: string
  onChange: (val: string) => void
  placeholder?: string
}

function TextInput({ label, description, value, onChange, placeholder }: TextInputProps) {
  return (
    <div
      style={{
        padding: '12px 16px',
        background: 'var(--tile)',
        borderRadius: 'var(--r-sm)',
        marginBottom: 8,
      }}
    >
      <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>{label}</div>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2, marginBottom: 8 }}>{description}</div>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          width: '100%',
          padding: '8px 12px',
          fontSize: 14,
          background: 'rgba(159, 214, 255, 0.08)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--r-sm)',
          color: 'var(--text)',
        }}
      />
    </div>
  )
}

interface SecureInputProps {
  label: string
  description: string
  value: string
  onChange: (val: string) => void
  placeholder?: string
}

function SecureInput({ label, description, value, onChange, placeholder }: SecureInputProps) {
  const [showKey, setShowKey] = useState(false)
  const hasValue = value.length > 0

  return (
    <div
      style={{
        padding: '12px 16px',
        background: 'var(--tile)',
        borderRadius: 'var(--r-sm)',
        marginBottom: 8,
      }}
    >
      <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>{label}</div>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2, marginBottom: 8 }}>{description}</div>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          type={showKey ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder || 'sk-...'}
          style={{
            flex: 1,
            padding: '8px 12px',
            fontSize: 14,
            background: 'rgba(159, 214, 255, 0.08)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--r-sm)',
            color: 'var(--text)',
            fontFamily: 'monospace',
          }}
        />
        <button
          onClick={() => setShowKey(!showKey)}
          style={{
            padding: '8px 12px',
            fontSize: 12,
            background: 'rgba(159, 214, 255, 0.08)',
            border: '1px solid var(--line)',
            borderRadius: 'var(--r-sm)',
            color: 'var(--glow)',
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          {showKey ? 'Hide' : 'Show'}
        </button>
      </div>
      {hasValue && (
        <div style={{ fontSize: 11, color: 'var(--glow)', marginTop: 6 }}>
          ✓ Key configured
        </div>
      )}
    </div>
  )
}

interface SelectInputProps {
  label: string
  description: string
  value: string
  onChange: (val: string) => void
  options: { value: string; label: string }[]
}

function SelectInput({ label, description, value, onChange, options }: SelectInputProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '12px 16px',
        background: 'var(--tile)',
        borderRadius: 'var(--r-sm)',
        marginBottom: 8,
      }}
    >
      <div>
        <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>{label}</div>
        <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>{description}</div>
      </div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          padding: '6px 12px',
          fontSize: 14,
          background: 'rgba(159, 214, 255, 0.08)',
          border: '1px solid var(--line)',
          borderRadius: 'var(--r-sm)',
          color: 'var(--text)',
          cursor: 'pointer',
        }}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} style={{ background: 'var(--bg0)' }}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  )
}

interface CollapsibleSectionProps {
  title: string
  description: string
  children: React.ReactNode
  defaultOpen?: boolean
}

function CollapsibleSection({ title, description, children, defaultOpen = false }: CollapsibleSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div
      style={{
        marginBottom: 16,
        border: '1px solid var(--line)',
        borderRadius: 'var(--r-md)',
        overflow: 'hidden',
      }}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: '100%',
          padding: '16px 20px',
          background: 'var(--tile)',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          textAlign: 'left',
        }}
      >
        <div>
          <div style={{ fontSize: 16, fontWeight: 500, color: 'var(--text)' }}>{title}</div>
          <div style={{ fontSize: 13, color: 'var(--muted)', marginTop: 4 }}>{description}</div>
        </div>
        <div
          style={{
            width: 24,
            height: 24,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--glow)',
            fontSize: 18,
            transition: 'transform 0.3s ease',
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
          }}
        >
          ▼
        </div>
      </button>
      {isOpen && (
        <div style={{ padding: '16px 20px', background: 'rgba(0,0,0,0.4)' }}>
          {children}
        </div>
      )}
    </div>
  )
}

interface CommandItemProps {
  command: string
  description: string
}

function CommandItem({ command, description }: CommandItemProps) {
  return (
    <div
      style={{
        padding: '10px 14px',
        background: 'var(--tile)',
        borderRadius: 'var(--r-sm)',
        marginBottom: 6,
      }}
    >
      <code style={{ fontSize: 13, color: 'var(--glow)', fontFamily: 'monospace' }}>{command}</code>
      <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>{description}</div>
    </div>
  )
}

export default function SettingsPanel() {
  // Connection status
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  // API Keys (stored securely)
  const [apiKeys, setApiKeys] = useState({
    openai: '',
    anthropic: '',
    openaiDalle: '', // Separate key for DALL-E if different
  })
  const [apiKeyStatus, setApiKeyStatus] = useState<{[key: string]: boolean}>({})

  // Workspace
  const [workspace, setWorkspace] = useState('')

  // Check API connection on mount
  useEffect(() => {
    const checkConnection = async () => {
      try {
        const healthy = await api.checkHealth()
        setIsConnected(healthy)
        if (healthy) {
          // Load API key status
          const keyStatus = await api.getAPIKeyStatus()
          const statusMap: {[key: string]: boolean} = {}
          keyStatus.forEach(k => { statusMap[k.provider] = k.configured })
          setApiKeyStatus(statusMap)
        }
      } catch {
        setIsConnected(false)
      } finally {
        setIsLoading(false)
      }
    }
    checkConnection()
  }, [])

  // Core Features
  const [coreFeatures, setCoreFeatures] = useState({
    tableOfThree: true,
    fileTools: true,
    passiveMemory: true,
    intelligentOrion: true,
    streaming: true,
  })

  // Intelligent Orion
  const [qualityThreshold, setQualityThreshold] = useState(0.7)
  const [maxRefinementIterations, setMaxRefinementIterations] = useState(3)

  // Governance
  const [defaultMode, setDefaultMode] = useState('safe')
  const [aegisStrictMode, setAegisStrictMode] = useState(true)

  // Command Execution
  const [commandExecution, setCommandExecution] = useState({
    enabled: false,
    timeout: 30,
  })

  // Limits
  const [limits, setLimits] = useState({
    maxEvidenceFiles: 20,
    maxFileSizeBytes: 100000,
    maxEvidenceRetry: 2,
  })

  // Web Access
  const [webAccess, setWebAccess] = useState({
    enabled: false,
    cacheTTL: 3600,
  })

  // ARA Settings
  const [araSettings, setAraSettings] = useState({
    enabled: true,
    defaultAuth: 'pin',
    maxCostUsd: 5,
    maxSessionHours: 8,
    sandboxMode: 'branch',
    promptGuard: true,
    auditLog: true,
  })

  const [allowedDomains, setAllowedDomains] = useState(
    'github.com, raw.githubusercontent.com, api.github.com, pypi.org, docs.python.org, stackoverflow.com'
  )

  // Image Generation
  const [imageProvider, setImageProvider] = useState('auto')
  const [imageSettings, setImageSettings] = useState({
    sdxlEnabled: true,
    sdxlEndpoint: 'http://127.0.0.1:8188',
    sdxlTimeout: 120,
    fluxEnabled: false,
    fluxEndpoint: 'http://127.0.0.1:8188',
    fluxTimeout: 180,
    dalleEnabled: false,
    dalleModel: 'dall-e-3',
    dalleTimeout: 60,
  })

  // Flexible Model Config (v2.3.0) + Light/Heavy Tiers (v4.9.0)
  const [modelMode, setModelMode] = useState<'single' | 'dual'>('single')
  const [builderProvider, setBuilderProvider] = useState('ollama')
  const [builderModel, setBuilderModel] = useState('qwen2.5:14b')
  const [builderLightModel, setBuilderLightModel] = useState('')
  const [builderUseTiers, setBuilderUseTiers] = useState(false)
  const [reviewerProvider, setReviewerProvider] = useState('ollama')
  const [reviewerModel, setReviewerModel] = useState('qwen2.5:14b')
  const [reviewerLightModel, setReviewerLightModel] = useState('')
  const [reviewerUseTiers, setReviewerUseTiers] = useState(false)

  // Fallback providers data so dropdowns are always populated
  const DEFAULT_PROVIDERS: Record<string, any> = {
    openai: {
      name: 'OpenAI', cost: 'paid', enabled: true,
      default_light: 'gpt-4o-mini', default_heavy: 'gpt-4o',
      models: [
        { id: 'gpt-4o', label: 'GPT-4o', tier: 'heavy' },
        { id: 'gpt-4o-mini', label: 'GPT-4o Mini', tier: 'light' },
        { id: 'gpt-4-turbo', label: 'GPT-4 Turbo', tier: 'heavy' },
        { id: 'o3', label: 'o3 (Deep Reasoning)', tier: 'heavy' },
        { id: 'o4-mini', label: 'o4-mini (Fast Reasoning)', tier: 'light' },
      ],
    },
    anthropic: {
      name: 'Anthropic', cost: 'paid', enabled: true,
      default_light: 'claude-3-5-haiku-20241022', default_heavy: 'claude-sonnet-4-20250514',
      models: [
        { id: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4', tier: 'heavy' },
        { id: 'claude-opus-4-20250514', label: 'Claude Opus 4', tier: 'heavy' },
        { id: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet', tier: 'heavy' },
        { id: 'claude-3-5-haiku-20241022', label: 'Claude 3.5 Haiku', tier: 'light' },
      ],
    },
    ollama: {
      name: 'Ollama (Local)', cost: 'free', enabled: true,
      default_light: 'qwen2.5:7b', default_heavy: 'qwen2.5:14b',
      models: [
        { id: 'qwen3:32b', label: 'Qwen 3 32B', tier: 'heavy' },
        { id: 'qwen2.5:14b', label: 'Qwen 2.5 14B', tier: 'heavy' },
        { id: 'qwen2.5-coder:14b', label: 'Qwen 2.5 Coder 14B', tier: 'heavy' },
        { id: 'deepseek-coder-v2:16b', label: 'DeepSeek Coder V2 16B', tier: 'heavy' },
        { id: 'llama3.3:70b', label: 'Llama 3.3 70B', tier: 'heavy' },
        { id: 'qwen3:8b', label: 'Qwen 3 8B', tier: 'light' },
        { id: 'qwen2.5:7b', label: 'Qwen 2.5 7B', tier: 'light' },
        { id: 'qwen2.5-coder:7b', label: 'Qwen 2.5 Coder 7B', tier: 'light' },
        { id: 'llama3.1:8b', label: 'Llama 3.1 8B', tier: 'light' },
        { id: 'mistral:7b', label: 'Mistral 7B', tier: 'light' },
      ],
    },
    google: {
      name: 'Google Gemini', cost: 'free_tier', enabled: true,
      default_light: 'gemini-2.5-flash', default_heavy: 'gemini-2.5-pro',
      models: [
        { id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro', tier: 'heavy' },
        { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', tier: 'light' },
        { id: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash', tier: 'light' },
        { id: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro', tier: 'heavy' },
      ],
    },
    groq: {
      name: 'Groq', cost: 'free_tier', enabled: true,
      default_light: 'llama-3.1-8b-instant', default_heavy: 'llama-3.3-70b-versatile',
      models: [
        { id: 'llama-3.3-70b-versatile', label: 'Llama 3.3 70B', tier: 'heavy' },
        { id: 'llama-3.1-8b-instant', label: 'Llama 3.1 8B Instant', tier: 'light' },
      ],
    },
  }

  const DEFAULT_PRESETS: Record<string, any> = {
    local_free: {
      mode: 'single',
      builder: { provider: 'ollama', model: 'qwen2.5:14b' },
      reviewer: { provider: 'ollama', model: 'qwen2.5:14b' },
      required_keys: [],
    },
    cloud_dual: {
      mode: 'dual',
      builder: { provider: 'openai', model: 'gpt-4o' },
      reviewer: { provider: 'anthropic', model: 'claude-sonnet-4-20250514' },
      required_keys: ['openai', 'anthropic'],
    },
    cloud_budget: {
      mode: 'dual',
      builder: { provider: 'openai', model: 'gpt-4o' },
      reviewer: { provider: 'anthropic', model: 'claude-sonnet-4-20250514' },
      required_keys: ['openai', 'anthropic'],
    },
    cloud_openai_only: {
      mode: 'single',
      builder: { provider: 'openai', model: 'gpt-4o' },
      reviewer: { provider: 'openai', model: 'gpt-4o' },
      required_keys: ['openai'],
    },
    cloud_anthropic_only: {
      mode: 'single',
      builder: { provider: 'anthropic', model: 'claude-sonnet-4-20250514' },
      reviewer: { provider: 'anthropic', model: 'claude-sonnet-4-20250514' },
      required_keys: ['anthropic'],
    },
    google_free: {
      mode: 'single',
      builder: { provider: 'google', model: 'gemini-2.5-pro' },
      reviewer: { provider: 'google', model: 'gemini-2.5-pro' },
      required_keys: [],
    },
    hybrid_budget: {
      mode: 'dual',
      builder: { provider: 'ollama', model: 'qwen2.5:14b' },
      reviewer: { provider: 'anthropic', model: 'claude-sonnet-4-20250514' },
      required_keys: ['anthropic'],
    },
  }

  const DEFAULT_OAUTH: Record<string, any> = {
    google: {
      name: 'Google',
      description: 'Access Gemini AI, Google Workspace, YouTube',
      scopes: 'gemini, drive, docs, sheets',
      free_tier: '1500 req/day Gemini free',
      configured: false, authenticated: false,
    },
    github: {
      name: 'GitHub',
      description: 'Repository access, issues, pull requests, Copilot',
      scopes: 'repo, read:org, read:user',
      free_tier: 'Public repos free',
      configured: false, authenticated: false,
    },
    gitlab: {
      name: 'GitLab',
      description: 'Repository access, CI/CD, merge requests',
      scopes: 'api, read_user, read_repository',
      free_tier: 'Public repos free',
      configured: false, authenticated: false,
    },
    microsoft: {
      name: 'Microsoft',
      description: 'Azure OpenAI, OneDrive, Office 365',
      scopes: 'openid, profile, User.Read',
      free_tier: 'Azure free tier available',
      configured: false, authenticated: false,
    },
  }

  const [presets, setPresets] = useState<Record<string, any>>(DEFAULT_PRESETS)
  const [providers, setProviders] = useState<Record<string, any>>(DEFAULT_PROVIDERS)

  // OAuth (v2.4.0)
  const [oauthStatus, setOauthStatus] = useState<Record<string, any>>(DEFAULT_OAUTH)
  const [oauthLoading, setOauthLoading] = useState<string | null>(null)

  // Provider auth status (v7.0.0 — OAuth sign-in for AI providers)
  const [providerAuthStatus, setProviderAuthStatus] = useState<Record<string, any>>({})
  const [providerKeyInput, setProviderKeyInput] = useState<Record<string, string>>({})
  const [providerKeyExpanded, setProviderKeyExpanded] = useState<string | null>(null)
  const [providerMessage, setProviderMessage] = useState<Record<string, string>>({})
  // Inline OAuth setup wizard state
  const [providerSetupMode, setProviderSetupMode] = useState<string | null>(null)
  const [providerSetupInfo, setProviderSetupInfo] = useState<Record<string, any>>({})
  const [providerSetupClientId, setProviderSetupClientId] = useState<string>('')
  const [providerSetupClientSecret, setProviderSetupClientSecret] = useState<string>('')
  const [providerSetupSaving, setProviderSetupSaving] = useState(false)

  // Connected Services (v6.4.0) — All platforms
  const [platformData, setPlatformData] = useState<any>(null)
  const [oauthProviders, setOauthProviders] = useState<Record<string, any>>({})
  const [connectingPlatform, setConnectingPlatform] = useState<string | null>(null)
  const [tokenInput, setTokenInput] = useState<Record<string, string>>({})
  const [oauthSetup, setOauthSetup] = useState<Record<string, { clientId: string; clientSecret?: string }>>({})
  const [platformMessage, setPlatformMessage] = useState<Record<string, string>>({})
  const [deviceFlow, setDeviceFlow] = useState<{ provider: string; userCode: string; verificationUri: string; deviceCode: string; interval: number } | null>(null)
  const [devicePollTimer, setDevicePollTimer] = useState<any>(null)

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

  const loadOAuthStatus = () => {
    fetch(`${API_BASE}/api/oauth/status`)
      .then(r => r.ok ? r.json() : null)
      .then(s => { if (s) setOauthStatus(s) })
      .catch(() => {})
  }

  const loadPlatforms = () => {
    fetch(`${API_BASE}/api/platforms`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setPlatformData(data) })
      .catch(() => {})
  }

  const loadOAuthProviders = () => {
    fetch(`${API_BASE}/api/oauth/providers`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setOauthProviders(data) })
      .catch(() => {})
  }

  const loadProviderAuthStatus = () => {
    fetch(`${API_BASE}/api/models/providers/auth-status`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setProviderAuthStatus(data) })
      .catch(() => {})
  }

  // Listen for OAuth popup success
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'oauth_success') {
        loadOAuthStatus()
        loadPlatforms()
        loadOAuthProviders()
        loadProviderAuthStatus()
        const prov = event.data.provider
        setProviderMessage(prev => ({ ...prev, [prov]: `✓ Signed in to ${prov}` }))
        setTimeout(() => setProviderMessage(prev => { const n = { ...prev }; delete n[prov]; return n }), 5000)
        setPlatformMessage(prev => ({ ...prev, [prov]: `✓ ${prov} connected successfully!` }))
        setTimeout(() => setPlatformMessage(prev => { const n = { ...prev }; delete n[prov]; return n }), 5000)
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [])

  // Cleanup device flow polling on unmount
  useEffect(() => {
    return () => { if (devicePollTimer) clearInterval(devicePollTimer) }
  }, [devicePollTimer])

  // Load all settings + model config + OAuth status on mount
  useEffect(() => {
    if (!isConnected) return
    loadPlatforms()
    loadOAuthProviders()
    loadProviderAuthStatus()
    // Load general settings
    fetch(`${API_BASE}/api/settings`)
      .then(r => r.ok ? r.json() : null)
      .then(s => {
        if (!s) return
        setCoreFeatures({
          tableOfThree: s.enable_table_of_three ?? true,
          fileTools: s.enable_file_tools ?? true,
          passiveMemory: s.enable_passive_memory ?? true,
          intelligentOrion: s.enable_intelligent_orion ?? true,
          streaming: s.enable_streaming ?? true,
        })
        setQualityThreshold(s.quality_threshold ?? 0.8)
        setMaxRefinementIterations(s.max_refinement_iterations ?? 3)
        setDefaultMode(s.default_mode ?? 'safe')
        setAegisStrictMode(s.aegis_strict_mode ?? true)
        setCommandExecution({
          enabled: s.enable_command_execution ?? false,
          timeout: s.command_timeout_seconds ?? 60,
        })
        setLimits({
          maxEvidenceFiles: s.max_evidence_files ?? 250,
          maxFileSizeBytes: s.max_file_size_bytes ?? 100000,
          maxEvidenceRetry: s.max_evidence_retry ?? 1,
        })
        setWebAccess({
          enabled: s.enable_web_access ?? false,
          cacheTTL: s.web_cache_ttl ?? 3600,
        })
        setAllowedDomains(s.allowed_domains ?? 'github.com, docs.python.org')
        setImageProvider(s.image_provider ?? 'auto')
        setImageSettings(prev => ({
          ...prev,
          sdxlEnabled: s.sdxl_enabled ?? prev.sdxlEnabled,
          sdxlEndpoint: s.sdxl_endpoint ?? prev.sdxlEndpoint,
          fluxEnabled: s.flux_enabled ?? prev.fluxEnabled,
          dalleEnabled: s.dalle_enabled ?? prev.dalleEnabled,
          dalleModel: s.dalle_model ?? prev.dalleModel,
        }))
        setPaths({
          dataDir: s.data_dir ?? 'data',
          ledgerFile: s.ledger_file ?? 'data/ledger.jsonl',
        })
        if (s.workspace) setWorkspace(s.workspace)
        // Load ARA settings
        if (s.ara_enabled !== undefined) setAraSettings(prev => ({
          ...prev,
          enabled: s.ara_enabled ?? prev.enabled,
          defaultAuth: s.ara_default_auth ?? prev.defaultAuth,
          maxCostUsd: s.ara_max_cost_usd ?? prev.maxCostUsd,
          maxSessionHours: s.ara_max_session_hours ?? prev.maxSessionHours,
          sandboxMode: s.ara_sandbox_mode ?? prev.sandboxMode,
          promptGuard: s.ara_prompt_guard ?? prev.promptGuard,
          auditLog: s.ara_audit_log ?? prev.auditLog,
        }))
      })
      .catch(() => {})
    loadOAuthStatus()
    fetch(`${API_BASE}/api/models/config`)
      .then(r => r.ok ? r.json() : null)
      .then(cfg => {
        if (cfg) {
          setModelMode(cfg.mode)
          setBuilderProvider(cfg.builder.provider)
          setBuilderModel(cfg.builder.model)
          setBuilderLightModel(cfg.builder.light_model || '')
          setBuilderUseTiers(cfg.builder.use_tiers || false)
          setReviewerProvider(cfg.reviewer.provider)
          setReviewerModel(cfg.reviewer.model)
          setReviewerLightModel(cfg.reviewer.light_model || '')
          setReviewerUseTiers(cfg.reviewer.use_tiers || false)
        }
      })
      .catch(() => {})
    fetch(`${API_BASE}/api/models/presets`)
      .then(r => r.ok ? r.json() : null)
      .then(p => { if (p) setPresets(p) })
      .catch(() => {})
    fetch(`${API_BASE}/api/models/providers`)
      .then(r => r.ok ? r.json() : null)
      .then(p => { if (p) setProviders(p) })
      .catch(() => {})
  }, [isConnected])

  const handleToggleProvider = async (provider: string, enabled: boolean) => {
    if (!isConnected) return
    try {
      const res = await fetch(`${API_BASE}/api/models/providers/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, enabled }),
      })
      if (res.ok) {
        setProviders((prev: Record<string, any>) => ({
          ...prev,
          [provider]: { ...prev[provider], enabled },
        }))
      }
    } catch (err) {
      console.error('Failed to toggle provider:', err)
    }
  }

  const handleApplyPreset = async (name: string) => {
    if (!isConnected) return
    try {
      const res = await fetch(`${API_BASE}/api/models/preset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      if (res.ok) {
        const data = await res.json()
        const cfg = data.config
        setModelMode(cfg.mode)
        setBuilderProvider(cfg.builder.provider)
        setBuilderModel(cfg.builder.model)
        setBuilderLightModel(cfg.builder.light_model || '')
        setBuilderUseTiers(cfg.builder.use_tiers || false)
        setReviewerProvider(cfg.reviewer.provider)
        setReviewerModel(cfg.reviewer.model)
        setReviewerLightModel(cfg.reviewer.light_model || '')
        setReviewerUseTiers(cfg.reviewer.use_tiers || false)
      }
    } catch (err) {
      console.error('Failed to apply preset:', err)
    }
  }

  const handleSaveModelConfig = async (overrideMode?: string) => {
    if (!isConnected) return
    try {
      await fetch(`${API_BASE}/api/models/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mode: overrideMode || modelMode,
          builder: {
            provider: builderProvider,
            model: builderModel,
            light_model: builderLightModel,
            use_tiers: builderUseTiers,
          },
          reviewer: {
            provider: reviewerProvider,
            model: reviewerModel,
            light_model: reviewerLightModel,
            use_tiers: reviewerUseTiers,
          },
        }),
      })
    } catch (err) {
      console.error('Failed to save model config:', err)
    }
  }

  // Helper: get model options for a provider as dropdown items
  const getModelOptions = (providerKey: string, tierFilter?: string) => {
    const p = providers[providerKey]
    if (!p?.models) return []
    const models = tierFilter
      ? p.models.filter((m: any) => m.tier === tierFilter)
      : p.models
    return models.map((m: any) => ({
      value: m.id,
      label: `${m.label} (${m.tier === 'light' ? 'Light' : 'Heavy'})`,
    }))
  }

  // OAuth handlers
  const handleOAuthLogin = async (provider: string) => {
    if (!isConnected) return
    setOauthLoading(provider)
    try {
      const res = await fetch(`${API_BASE}/api/oauth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.status === 'redirect' && data.auth_url) {
          const popup = window.open(data.auth_url, `orion_oauth_${provider}`, 'width=600,height=700,menubar=no,toolbar=no')
          if (!popup) {
            setProviderMessage(prev => ({ ...prev, [provider]: 'Popup blocked — please allow popups for this site.' }))
          }
        } else {
          loadOAuthStatus()
          loadProviderAuthStatus()
        }
      }
    } catch (err) {
      console.error('OAuth login failed:', err)
    } finally {
      setOauthLoading(null)
    }
  }

  // AI Provider sign-in handler — opens browser OAuth popup for OAuth-capable providers
  const handleProviderSignIn = async (providerKey: string) => {
    if (!isConnected) return
    setOauthLoading(providerKey)
    setProviderMessage(prev => ({ ...prev, [providerKey]: '' }))
    try {
      const res = await fetch(`${API_BASE}/api/oauth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: providerKey }),
      })
      const data = await res.json()
      if (data.status === 'redirect' && data.auth_url) {
        const popup = window.open(data.auth_url, `orion_oauth_${providerKey}`, 'width=600,height=700,menubar=no,toolbar=no')
        if (!popup) {
          setProviderMessage(prev => ({ ...prev, [providerKey]: 'Popup blocked — please allow popups for this site.' }))
        }
      } else if (data.detail?.toLowerCase().includes('not registered') || data.detail?.toLowerCase().includes('not configured') || data.detail?.toLowerCase().includes('client_id')) {
        // OAuth app not set up yet — open the inline setup wizard
        openSetupWizard(providerKey)
      } else if (data.detail) {
        setProviderMessage(prev => ({ ...prev, [providerKey]: data.detail }))
      }
    } catch (err) {
      setProviderMessage(prev => ({ ...prev, [providerKey]: 'Sign-in failed. Try again or use an API key.' }))
    } finally {
      setOauthLoading(null)
    }
  }

  // Open inline setup wizard — fetches setup info from backend
  const openSetupWizard = async (providerKey: string) => {
    setProviderSetupMode(providerKey)
    setProviderSetupClientId('')
    setProviderSetupClientSecret('')
    setProviderKeyExpanded(null) // close API key input if open
    try {
      const res = await fetch(`${API_BASE}/api/oauth/setup-info/${providerKey}`)
      if (res.ok) {
        const info = await res.json()
        setProviderSetupInfo(prev => ({ ...prev, [providerKey]: info }))
      }
    } catch { /* ignore — wizard still works with basic UI */ }
  }

  // Save client_id from setup wizard, then auto-trigger sign-in
  const handleSetupWizardSave = async (providerKey: string) => {
    if (!providerSetupClientId || providerSetupClientId.length < 5) {
      setProviderMessage(prev => ({ ...prev, [providerKey]: 'Client ID is too short.' }))
      return
    }
    setProviderSetupSaving(true)
    try {
      const body: any = { provider: providerKey, client_id: providerSetupClientId }
      if (providerSetupClientSecret) body.client_secret = providerSetupClientSecret
      const res = await fetch(`${API_BASE}/api/oauth/quick-setup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        setProviderSetupMode(null)
        setProviderSetupClientId('')
        setProviderSetupClientSecret('')
        setProviderMessage(prev => ({ ...prev, [providerKey]: '✓ OAuth app registered! Opening sign-in...' }))
        setTimeout(() => setProviderMessage(prev => { const n = { ...prev }; delete n[providerKey]; return n }), 3000)
        // Auto-trigger sign-in now that client_id is saved
        setTimeout(() => handleProviderSignIn(providerKey), 500)
      } else {
        const err = await res.json()
        setProviderMessage(prev => ({ ...prev, [providerKey]: err.detail || 'Failed to save. Check the Client ID and try again.' }))
      }
    } catch {
      setProviderMessage(prev => ({ ...prev, [providerKey]: 'Failed to save. Check your connection.' }))
    } finally {
      setProviderSetupSaving(false)
    }
  }

  // AI Provider inline API key save
  const handleProviderKeySave = async (providerKey: string) => {
    const key = providerKeyInput[providerKey]
    if (!key || key.length < 8) return
    try {
      const res = await fetch(`${API_BASE}/api/keys/set`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: providerKey, key }),
      })
      if (res.ok) {
        setProviderKeyInput(prev => ({ ...prev, [providerKey]: '' }))
        setProviderKeyExpanded(null)
        setProviderMessage(prev => ({ ...prev, [providerKey]: '✓ API key saved' }))
        loadProviderAuthStatus()
        setTimeout(() => setProviderMessage(prev => { const n = { ...prev }; delete n[providerKey]; return n }), 3000)
      } else {
        const err = await res.json()
        setProviderMessage(prev => ({ ...prev, [providerKey]: err.detail || 'Failed to save key' }))
      }
    } catch {
      setProviderMessage(prev => ({ ...prev, [providerKey]: 'Failed to save key' }))
    }
  }

  // AI Provider disconnect
  const handleProviderDisconnect = async (providerKey: string) => {
    try {
      // Remove API key
      await fetch(`${API_BASE}/api/keys/${providerKey}`, { method: 'DELETE' })
      // Revoke OAuth if any
      await fetch(`${API_BASE}/api/oauth/revoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: providerKey }),
      })
      loadProviderAuthStatus()
      setProviderMessage(prev => ({ ...prev, [providerKey]: 'Disconnected' }))
      setTimeout(() => setProviderMessage(prev => { const n = { ...prev }; delete n[providerKey]; return n }), 3000)
    } catch {
      setProviderMessage(prev => ({ ...prev, [providerKey]: 'Failed to disconnect' }))
    }
  }

  const handleOAuthRevoke = async (provider: string) => {
    if (!isConnected) return
    try {
      await fetch(`${API_BASE}/api/oauth/revoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider }),
      })
      loadOAuthStatus()
    } catch (err) {
      console.error('OAuth revoke failed:', err)
    }
  }

  // Platform connect handlers (v6.4.0 — one-click OAuth)
  const handlePlatformConnect = async (platformId: string, authMethod?: string) => {
    if (!isConnected) return
    setConnectingPlatform(platformId)

    try {
      // Check if this is an OAuth provider (from /api/oauth/providers)
      const oauthProv = oauthProviders[platformId]
      if (oauthProv && !oauthProv.connected) {
        // Use the new one-click connect endpoint
        const res = await fetch(`${API_BASE}/api/oauth/connect/${platformId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        })
        const data = await res.json()

        if (data.status === 'device_flow') {
          // GitHub Device Flow — show user_code and start polling
          setDeviceFlow({
            provider: platformId,
            userCode: data.user_code,
            verificationUri: data.verification_uri,
            deviceCode: data.device_code,
            interval: data.interval || 5,
          })
          window.open(data.verification_uri, '_blank')

          // Start polling
          const timer = setInterval(async () => {
            try {
              const pollRes = await fetch(`${API_BASE}/api/oauth/device-poll/${platformId}?device_code=${data.device_code}`, { method: 'POST' })
              const pollData = await pollRes.json()
              if (pollData.status === 'success') {
                clearInterval(timer)
                setDeviceFlow(null)
                setDevicePollTimer(null)
                setPlatformMessage(prev => ({ ...prev, [platformId]: `✓ ${pollData.name} connected!` }))
                loadOAuthProviders()
                loadPlatforms()
                setTimeout(() => setPlatformMessage(prev => { const n = { ...prev }; delete n[platformId]; return n }), 5000)
              } else if (pollData.status === 'error') {
                clearInterval(timer)
                setDeviceFlow(null)
                setDevicePollTimer(null)
                setPlatformMessage(prev => ({ ...prev, [platformId]: pollData.message }))
              }
            } catch { /* keep polling */ }
          }, (data.interval || 5) * 1000)
          setDevicePollTimer(timer)
          return // Don't clear connectingPlatform yet

        } else if (data.status === 'redirect' && data.auth_url) {
          // PKCE/OAuth popup
          const popup = window.open(data.auth_url, `orion_oauth_${platformId}`, 'width=600,height=700,menubar=no,toolbar=no')
          if (!popup) {
            setPlatformMessage(prev => ({ ...prev, [platformId]: 'Popup blocked — please allow popups for this site.' }))
          }
        } else if (data.status === 'needs_setup') {
          // Show setup form inline
          setPlatformMessage(prev => ({ ...prev, [platformId]: data.message }))
        }
      } else if (tokenInput[platformId]) {
        // Manual token/key — use new endpoint
        const res = await fetch(`${API_BASE}/api/oauth/token/${platformId}?token=${encodeURIComponent(tokenInput[platformId])}`, {
          method: 'POST',
        })
        if (res.ok) {
          setPlatformMessage(prev => ({ ...prev, [platformId]: '✓ Connected!' }))
          setTokenInput(prev => ({ ...prev, [platformId]: '' }))
          loadPlatforms()
          loadOAuthProviders()
          setTimeout(() => setPlatformMessage(prev => { const n = { ...prev }; delete n[platformId]; return n }), 3000)
        } else {
          const err = await res.json()
          setPlatformMessage(prev => ({ ...prev, [platformId]: err.detail || 'Failed to connect' }))
        }
      }
    } catch (err) {
      console.error('Platform connect failed:', err)
      setPlatformMessage(prev => ({ ...prev, [platformId]: 'Connection failed. Is the API server running?' }))
    } finally {
      if (!deviceFlow) setConnectingPlatform(null)
    }
  }

  const handlePlatformDisconnect = async (platformId: string) => {
    if (!isConnected) return
    try {
      // Try new endpoint first, fall back to old
      const res = await fetch(`${API_BASE}/api/oauth/disconnect/${platformId}`, { method: 'POST' })
      if (!res.ok) {
        await fetch(`${API_BASE}/api/platforms/disconnect`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ platform_id: platformId }),
        })
      }
      loadPlatforms()
      loadOAuthProviders()
    } catch (err) {
      console.error('Platform disconnect failed:', err)
    }
  }

  const handleOAuthSetup = async (platformId: string) => {
    if (!isConnected) return
    const setup = oauthSetup[platformId]
    if (!setup?.clientId) return
    try {
      const params = new URLSearchParams({ client_id: setup.clientId })
      if (setup.clientSecret) params.append('client_secret', setup.clientSecret)
      const res = await fetch(`${API_BASE}/api/oauth/setup/${platformId}?${params}`, { method: 'POST' })
      if (res.ok) {
        setPlatformMessage(prev => ({ ...prev, [platformId]: '✓ Configured! Now click Connect to sign in.' }))
        setOauthSetup(prev => { const n = { ...prev }; delete n[platformId]; return n })
        loadOAuthProviders()
      }
    } catch (err) {
      console.error('OAuth setup failed:', err)
    }
  }

  const handleSaveAllSettings = async () => {
    if (!isConnected) return
    setSaveStatus('saving')
    try {
      await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enable_table_of_three: coreFeatures.tableOfThree,
          enable_file_tools: coreFeatures.fileTools,
          enable_passive_memory: coreFeatures.passiveMemory,
          enable_intelligent_orion: coreFeatures.intelligentOrion,
          enable_streaming: coreFeatures.streaming,
          quality_threshold: qualityThreshold,
          max_refinement_iterations: maxRefinementIterations,
          default_mode: defaultMode,
          aegis_strict_mode: aegisStrictMode,
          enable_command_execution: commandExecution.enabled,
          command_timeout_seconds: commandExecution.timeout,
          max_evidence_files: limits.maxEvidenceFiles,
          max_file_size_bytes: limits.maxFileSizeBytes,
          max_evidence_retry: limits.maxEvidenceRetry,
          enable_web_access: webAccess.enabled,
          web_cache_ttl: webAccess.cacheTTL,
          allowed_domains: allowedDomains,
          image_provider: imageProvider,
          sdxl_enabled: imageSettings.sdxlEnabled,
          sdxl_endpoint: imageSettings.sdxlEndpoint,
          flux_enabled: imageSettings.fluxEnabled,
          dalle_enabled: imageSettings.dalleEnabled,
          dalle_model: imageSettings.dalleModel,
          data_dir: paths.dataDir,
          ledger_file: paths.ledgerFile,
          workspace: workspace,
          ara_enabled: araSettings.enabled,
          ara_default_auth: araSettings.defaultAuth,
          ara_max_cost_usd: araSettings.maxCostUsd,
          ara_max_session_hours: araSettings.maxSessionHours,
          ara_sandbox_mode: araSettings.sandboxMode,
          ara_prompt_guard: araSettings.promptGuard,
          ara_audit_log: araSettings.auditLog,
        }),
      })
      await handleSaveModelConfig()
      // Save each API key that has a value
      for (const [provider, key] of Object.entries(apiKeys)) {
        if (key) await api.setAPIKey(provider === 'openaiDalle' ? 'openai_dalle' : provider, key)
      }
      setSaveStatus('saved')
    } catch (err) {
      console.error('Failed to save settings:', err)
      setSaveStatus('error')
    }
  }

  const [oauthCredentials, setOauthCredentials] = useState<Record<string, { clientId: string; clientSecret: string }>>({})
  const getOauthCred = (provider: string) => oauthCredentials[provider] || { clientId: '', clientSecret: '' }
  const setOauthCred = (provider: string, field: 'clientId' | 'clientSecret', value: string) =>
    setOauthCredentials(prev => ({ ...prev, [provider]: { ...getOauthCred(provider), [field]: value } }))

  const handleOAuthConfigure = async (provider: string) => {
    const cred = getOauthCred(provider)
    if (!isConnected || !cred.clientId) return
    try {
      const res = await fetch(`${API_BASE}/api/oauth/configure`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          client_id: cred.clientId,
          client_secret: cred.clientSecret || undefined,
        }),
      })
      if (res.ok) {
        setOauthCredentials(prev => { const next = { ...prev }; delete next[provider]; return next })
        loadOAuthStatus()
      }
    } catch (err) {
      console.error('OAuth configure failed:', err)
    }
  }

  // Paths
  const [paths, setPaths] = useState({
    dataDir: 'data',
    ledgerFile: 'data/ledger.jsonl',
  })

  // Save API key to backend
  const handleSaveAPIKey = async (provider: string, key: string) => {
    if (!isConnected || !key) return
    try {
      await api.setAPIKey(provider, key)
      setApiKeyStatus(prev => ({ ...prev, [provider]: true }))
    } catch (err) {
      console.error('Failed to save API key:', err)
    }
  }

  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '40px 20px' }}>
      {saveStatus !== 'idle' && (
        <SaveToast status={saveStatus} onDismiss={() => setSaveStatus('idle')} />
      )}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 32 }}>
        <div>
          <div style={{ fontSize: 28, fontWeight: 500, color: 'var(--text)' }}>Settings</div>
          <div style={{ fontSize: 14, color: 'var(--muted)', marginTop: 4 }}>Customize how Orion works for you. Hover over <Tooltip text="Tooltips provide extra details about technical settings. Look for the ? icon next to settings you're unsure about." /> for help.</div>
        </div>
        <Link href="/">
          <Button variant="secondary">← Back</Button>
        </Link>
      </div>

      {/* Connection Status */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '12px 16px',
          background: isConnected ? 'rgba(100, 255, 100, 0.1)' : 'rgba(255, 100, 100, 0.1)',
          border: `1px solid ${isConnected ? 'rgba(100, 255, 100, 0.3)' : 'rgba(255, 100, 100, 0.3)'}`,
          borderRadius: 'var(--r-md)',
          marginBottom: 20,
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: isLoading ? '#ffcc66' : isConnected ? '#64ff64' : '#ff6464',
          }}
        />
        <span style={{ fontSize: 14, color: 'var(--text)' }}>
          {isLoading ? 'Connecting to Orion API...' : isConnected ? 'Connected to Orion API Server' : 'Not connected to Orion API'}
        </span>
        {!isConnected && !isLoading && (
          <span style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 'auto' }}>
            Start API: <code style={{ color: 'var(--glow)' }}>uvicorn api.server:app --port 8000</code>
          </span>
        )}
      </div>

      {/* API Keys */}
      <CollapsibleSection title="API Keys" description="Connect to cloud AI services like OpenAI and Anthropic. Not needed if you only use free local models." defaultOpen={true}>
        <div style={{ padding: '12px 16px', background: 'rgba(255, 200, 100, 0.1)', borderRadius: 'var(--r-sm)', marginBottom: 12, border: '1px solid rgba(255, 200, 100, 0.3)' }}>
          <div style={{ fontSize: 13, color: '#ffcc66' }}>
            🔐 API keys are stored securely and never exposed in logs or responses.
          </div>
        </div>
        <SecureInput
          label="OpenAI API Key"
          description="Required for GPT models (Table of Three builder)"
          value={apiKeys.openai}
          onChange={(v) => setApiKeys((p) => ({ ...p, openai: v }))}
          placeholder="sk-..."
        />
        <SecureInput
          label="Anthropic API Key"
          description="Required for Claude models (Table of Three reviewer)"
          value={apiKeys.anthropic}
          onChange={(v) => setApiKeys((p) => ({ ...p, anthropic: v }))}
          placeholder="sk-ant-..."
        />
        <SecureInput
          label="OpenAI API Key (DALL-E)"
          description="For DALL-E image generation (leave blank to use main OpenAI key)"
          value={apiKeys.openaiDalle}
          onChange={(v) => setApiKeys((p) => ({ ...p, openaiDalle: v }))}
          placeholder="sk-... (optional)"
        />
      </CollapsibleSection>

      {/* LLM Provider Enable/Disable (v5.1.0 → v7.0.0 with OAuth sign-in) */}
      <CollapsibleSection title="AI Providers" description="Sign in to your AI provider accounts or set API keys. OAuth-capable providers open a browser login.">
        <div style={{ padding: '12px 16px', background: 'rgba(34, 211, 238, 0.08)', borderRadius: 'var(--r-sm)', marginBottom: 16, border: '1px solid rgba(34, 211, 238, 0.2)' }}>
          <div style={{ fontSize: 13, color: 'var(--glow)' }}>
            Sign in with your existing account to use your subscription, or enter an API key. Local providers like Ollama need no authentication.
          </div>
        </div>
        {Object.entries(providers).map(([key, info]: [string, any]) => {
          const auth = providerAuthStatus[key] || {}
          const authType = auth.auth_type || (key === 'ollama' ? 'local' : 'api_key')
          const isConnected = auth.connected || false
          const source = auth.source || 'none'
          const oauthReady = auth.oauth_ready || false  // true = client_id available, one-click sign-in
          const isExpanded = providerKeyExpanded === key
          const msg = providerMessage[key]
          const isLoading = oauthLoading === key

          return (
            <div key={key} style={{ marginBottom: 8 }}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '12px 16px', background: 'rgba(0,0,0,0.15)',
                borderRadius: (isExpanded || providerSetupMode === key) ? 'var(--r-sm) var(--r-sm) 0 0' : 'var(--r-sm)',
                border: `1px solid ${isConnected ? 'rgba(34,211,238,0.2)' : providerSetupMode === key ? 'rgba(34,211,238,0.2)' : 'var(--line)'}`,
                borderBottom: (isExpanded || providerSetupMode === key) ? '1px solid var(--line)' : undefined,
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{info.name || key}</span>
                    <span style={{ fontSize: 11, color: 'var(--muted)' }}>
                      {(info.models || []).length} models · {info.cost || '?'}
                    </span>
                  </div>
                  {isConnected && (
                    <div style={{ fontSize: 11, marginTop: 2, color: 'rgba(34, 211, 238, 0.7)' }}>
                      {source === 'oauth' ? '✓ Signed in' : source === 'local' ? '✓ Local' : source === 'env' ? '✓ Environment variable' : '✓ API key configured'}
                    </div>
                  )}
                  {msg && <div style={{ fontSize: 11, marginTop: 2, color: msg.startsWith('✓') ? 'rgba(34, 211, 238, 0.8)' : '#f59e0b' }}>{msg}</div>}
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  {/* Connected: show Disconnect */}
                  {isConnected && key !== 'ollama' && (
                    <button onClick={() => handleProviderDisconnect(key)} style={{
                      padding: '4px 10px', fontSize: 11, borderRadius: 'var(--r-sm)', cursor: 'pointer',
                      background: 'rgba(255,255,255,0.03)', color: 'var(--muted)', border: '1px solid var(--line)',
                    }}>Disconnect</button>
                  )}
                  {/* Not connected: show Sign in (OAuth) or Set API Key */}
                  {!isConnected && authType === 'oauth' && (
                    <>
                      <button onClick={() => handleProviderSignIn(key)} disabled={isLoading} style={{
                        padding: '5px 14px', fontSize: 12, fontWeight: 600, borderRadius: 'var(--r-sm)', cursor: 'pointer',
                        background: 'rgba(34,211,238,0.15)', color: 'var(--glow)', border: '1px solid rgba(34,211,238,0.3)',
                        opacity: isLoading ? 0.6 : 1,
                      }}>{isLoading ? 'Opening...' : `Sign in`}</button>
                      <button onClick={() => setProviderKeyExpanded(isExpanded ? null : key)} style={{
                        padding: '4px 10px', fontSize: 11, borderRadius: 'var(--r-sm)', cursor: 'pointer',
                        background: 'rgba(255,255,255,0.03)', color: 'var(--muted)', border: '1px solid var(--line)',
                      }}>API Key</button>
                    </>
                  )}
                  {!isConnected && authType === 'api_key' && (
                    <button onClick={() => setProviderKeyExpanded(isExpanded ? null : key)} style={{
                      padding: '5px 14px', fontSize: 12, fontWeight: 600, borderRadius: 'var(--r-sm)', cursor: 'pointer',
                      background: 'rgba(34,211,238,0.15)', color: 'var(--glow)', border: '1px solid rgba(34,211,238,0.3)',
                    }}>Set API Key</button>
                  )}
                  {authType === 'local' && (
                    <span style={{ padding: '4px 12px', fontSize: 12, fontWeight: 600, color: 'rgba(34, 211, 238, 0.7)' }}>Local</span>
                  )}
                </div>
              </div>
              {/* Inline API key input (expanded) */}
              {isExpanded && providerSetupMode !== key && (
                <div style={{
                  padding: '10px 16px', background: 'rgba(0,0,0,0.1)', borderRadius: '0 0 var(--r-sm) var(--r-sm)',
                  border: '1px solid var(--line)', borderTop: 'none',
                  display: 'flex', gap: 8, alignItems: 'center',
                }}>
                  <input
                    type="password"
                    placeholder={`Paste ${(info.name || key)} API key...`}
                    value={providerKeyInput[key] || ''}
                    onChange={e => setProviderKeyInput(prev => ({ ...prev, [key]: e.target.value }))}
                    onKeyDown={e => e.key === 'Enter' && handleProviderKeySave(key)}
                    style={{
                      flex: 1, padding: '6px 10px', fontSize: 13, background: 'rgba(0,0,0,0.3)',
                      border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', color: 'var(--text)',
                      outline: 'none', fontFamily: 'monospace',
                    }}
                  />
                  <button onClick={() => handleProviderKeySave(key)} style={{
                    padding: '6px 14px', fontSize: 12, fontWeight: 600, borderRadius: 'var(--r-sm)', cursor: 'pointer',
                    background: 'rgba(34,211,238,0.15)', color: 'var(--glow)', border: '1px solid rgba(34,211,238,0.3)',
                  }}>Save</button>
                  <button onClick={() => setProviderKeyExpanded(null)} style={{
                    padding: '6px 10px', fontSize: 12, borderRadius: 'var(--r-sm)', cursor: 'pointer',
                    background: 'transparent', color: 'var(--muted)', border: '1px solid var(--line)',
                  }}>Cancel</button>
                </div>
              )}
              {/* Inline OAuth setup wizard (first-time registration) */}
              {providerSetupMode === key && (() => {
                const setupInfo = providerSetupInfo[key] || {}
                return (
                  <div style={{
                    padding: '16px', background: 'rgba(34, 211, 238, 0.06)', borderRadius: '0 0 var(--r-sm) var(--r-sm)',
                    border: '1px solid rgba(34, 211, 238, 0.2)', borderTop: 'none',
                  }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--glow)', marginBottom: 10 }}>
                      One-time setup — Register an OAuth app
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text)', marginBottom: 12, lineHeight: 1.5 }}>
                      {setupInfo.setup_instructions ? (
                        setupInfo.setup_instructions.split('\n').map((line: string, i: number) => (
                          <div key={i} style={{ marginBottom: 2 }}>{line}</div>
                        ))
                      ) : (
                        <div>Register an OAuth application at your provider's developer console, then paste the Client ID below.</div>
                      )}
                    </div>
                    {setupInfo.redirect_uri && (
                      <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 10, background: 'rgba(0,0,0,0.2)', padding: '6px 10px', borderRadius: 'var(--r-sm)', fontFamily: 'monospace' }}>
                        Redirect URI: <span style={{ color: 'var(--text)', userSelect: 'all', cursor: 'pointer' }} onClick={() => navigator.clipboard?.writeText(setupInfo.redirect_uri)} title="Click to copy">{setupInfo.redirect_uri}</span>
                      </div>
                    )}
                    {setupInfo.setup_url && (
                      <div style={{ marginBottom: 12 }}>
                        <a href={setupInfo.setup_url} target="_blank" rel="noopener noreferrer" style={{
                          fontSize: 12, color: 'var(--glow)', textDecoration: 'underline',
                        }}>Open {info.name || key} developer console →</a>
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                      <input
                        type="text"
                        placeholder="Paste Client ID..."
                        value={providerSetupClientId}
                        onChange={e => setProviderSetupClientId(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleSetupWizardSave(key)}
                        style={{
                          flex: 1, padding: '7px 10px', fontSize: 13, background: 'rgba(0,0,0,0.3)',
                          border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', color: 'var(--text)',
                          outline: 'none', fontFamily: 'monospace',
                        }}
                      />
                    </div>
                    {setupInfo.needs_secret && (
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                        <input
                          type="password"
                          placeholder="Client Secret (if required)..."
                          value={providerSetupClientSecret}
                          onChange={e => setProviderSetupClientSecret(e.target.value)}
                          style={{
                            flex: 1, padding: '7px 10px', fontSize: 13, background: 'rgba(0,0,0,0.3)',
                            border: '1px solid var(--line)', borderRadius: 'var(--r-sm)', color: 'var(--text)',
                            outline: 'none', fontFamily: 'monospace',
                          }}
                        />
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        onClick={() => handleSetupWizardSave(key)}
                        disabled={providerSetupSaving || !providerSetupClientId}
                        style={{
                          padding: '7px 18px', fontSize: 12, fontWeight: 600, borderRadius: 'var(--r-sm)', cursor: 'pointer',
                          background: 'rgba(34,211,238,0.15)', color: 'var(--glow)', border: '1px solid rgba(34,211,238,0.3)',
                          opacity: (providerSetupSaving || !providerSetupClientId) ? 0.5 : 1,
                        }}
                      >{providerSetupSaving ? 'Saving...' : 'Save & Sign in'}</button>
                      <button onClick={() => { setProviderSetupMode(null); setProviderSetupClientId(''); setProviderSetupClientSecret('') }} style={{
                        padding: '7px 12px', fontSize: 12, borderRadius: 'var(--r-sm)', cursor: 'pointer',
                        background: 'transparent', color: 'var(--muted)', border: '1px solid var(--line)',
                      }}>Cancel</button>
                      <button onClick={() => { setProviderSetupMode(null); setProviderKeyExpanded(key) }} style={{
                        padding: '7px 12px', fontSize: 12, borderRadius: 'var(--r-sm)', cursor: 'pointer',
                        background: 'transparent', color: 'var(--muted)', border: '1px solid var(--line)',
                      }}>Use API Key instead</button>
                    </div>
                  </div>
                )
              })()}
            </div>
          )
        })}
      </CollapsibleSection>

      {/* Connected Services (v6.4.0) — One-Click OAuth */}
      <CollapsibleSection title="Connected Services" description="Connect platforms so Orion can use them. Most require a one-time OAuth app setup, then it's one-click." defaultOpen={true}>
        {/* Device Flow Modal — shown when GitHub auth is in progress */}
        {deviceFlow && (
          <div style={{
            padding: '16px 20px', background: 'rgba(34, 211, 238, 0.12)', borderRadius: 'var(--r-sm)',
            marginBottom: 16, border: '1px solid rgba(34, 211, 238, 0.3)', textAlign: 'center',
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--glow)', marginBottom: 8 }}>
              Connecting to GitHub...
            </div>
            <div style={{ fontSize: 13, color: 'var(--text)', marginBottom: 12 }}>
              Enter this code at <a href={deviceFlow.verificationUri} target="_blank" rel="noopener noreferrer"
                style={{ color: 'var(--glow)' }}>{deviceFlow.verificationUri}</a>:
            </div>
            <div style={{
              fontSize: 28, fontWeight: 700, fontFamily: 'monospace', letterSpacing: 4,
              color: '#fff', background: 'rgba(0,0,0,0.4)', padding: '12px 24px',
              borderRadius: 'var(--r-sm)', display: 'inline-block', marginBottom: 8,
              userSelect: 'all', cursor: 'pointer',
            }}
              title="Click to copy"
              onClick={() => navigator.clipboard?.writeText(deviceFlow.userCode)}
            >{deviceFlow.userCode}</div>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>
              Click the code to copy. Waiting for authorization...
            </div>
            <button onClick={() => {
              if (devicePollTimer) clearInterval(devicePollTimer)
              setDeviceFlow(null)
              setDevicePollTimer(null)
              setConnectingPlatform(null)
            }} style={{
              marginTop: 10, padding: '4px 12px', fontSize: 11, background: 'transparent',
              color: '#ff6b6b', border: '1px solid rgba(255,107,107,0.4)', borderRadius: 'var(--r-sm)', cursor: 'pointer',
            }}>Cancel</button>
          </div>
        )}

        {/* OAuth Providers section */}
        {Object.keys(oauthProviders).length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span>🔗</span> Sign-In Services
              <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 400 }}>
                ({Object.values(oauthProviders).filter((p: any) => p.connected).length}/{Object.keys(oauthProviders).length} connected)
              </span>
            </div>

            {Object.entries(oauthProviders).map(([pid, p]: [string, any]) => (
              <div key={pid} style={{
                padding: '12px 16px',
                background: p.connected ? 'rgba(34, 211, 238, 0.05)' : 'rgba(0,0,0,0.15)',
                borderRadius: 'var(--r-sm)', marginBottom: 6,
                border: p.connected ? '1px solid rgba(34, 211, 238, 0.2)' : '1px solid var(--line)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 18 }}>{p.icon}</span>
                      <span style={{ fontSize: 14, fontWeight: 600, color: p.connected ? 'var(--glow)' : 'var(--text)' }}>
                        {p.name}
                      </span>
                      {p.connected && (
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: '2px 8px',
                          background: 'rgba(100, 255, 100, 0.15)', color: '#64ff64',
                          borderRadius: 10, border: '1px solid rgba(100, 255, 100, 0.3)',
                        }}>Connected</span>
                      )}
                      {!p.connected && p.configured && (
                        <span style={{ fontSize: 10, color: '#64c864' }}>Ready</span>
                      )}
                      {!p.connected && p.needs_setup && (
                        <span style={{ fontSize: 10, color: '#ffcc66' }}>Setup needed</span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>{p.description}</div>
                  </div>

                  <div style={{ display: 'flex', gap: 6, marginLeft: 12, flexShrink: 0 }}>
                    {p.connected && (
                      <button onClick={() => handlePlatformDisconnect(pid)} style={{
                        padding: '5px 12px', fontSize: 11, fontWeight: 500,
                        background: 'transparent', color: '#ff6b6b', border: '1px solid rgba(255,107,107,0.4)',
                        borderRadius: 'var(--r-sm)', cursor: 'pointer',
                      }}>Disconnect</button>
                    )}

                    {!p.connected && p.configured && (
                      <button
                        onClick={() => handlePlatformConnect(pid)}
                        disabled={connectingPlatform === pid}
                        style={{
                          padding: '5px 14px', fontSize: 12, fontWeight: 600,
                          background: 'var(--glow)', color: '#000', border: 'none',
                          borderRadius: 'var(--r-sm)', cursor: 'pointer',
                          opacity: connectingPlatform === pid ? 0.5 : 1,
                        }}
                      >{connectingPlatform === pid ? 'Connecting...' : 'Sign In & Connect'}</button>
                    )}

                    {!p.connected && p.needs_setup && !oauthSetup[pid] && (
                      <button onClick={() => setOauthSetup(prev => ({ ...prev, [pid]: { clientId: '' } }))} style={{
                        padding: '5px 14px', fontSize: 12, fontWeight: 600,
                        background: 'rgba(34,211,238,0.15)', color: 'var(--glow)',
                        border: '1px solid rgba(34,211,238,0.3)', borderRadius: 'var(--r-sm)', cursor: 'pointer',
                      }}>Set Up</button>
                    )}
                  </div>
                </div>

                {/* Setup steps (shown when needs_setup) */}
                {!p.connected && p.needs_setup && p.setup_steps?.length > 0 && oauthSetup[pid] !== undefined && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
                      {p.setup_steps.map((step: any, i: number) => (
                        <div key={i} style={{ marginBottom: 3 }}>{step.text}</div>
                      ))}
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <input
                        type="text" placeholder="Client ID"
                        value={oauthSetup[pid]?.clientId || ''}
                        onChange={(e) => setOauthSetup(prev => ({ ...prev, [pid]: { ...prev[pid], clientId: e.target.value } }))}
                        style={{
                          flex: 1, minWidth: 160, padding: '7px 12px', fontSize: 13,
                          background: 'var(--tile)', border: '1px solid var(--line)',
                          borderRadius: 'var(--r-sm)', color: 'var(--text)',
                        }}
                      />
                      {p.auth_type === 'oauth_secret' && (
                        <input
                          type="password" placeholder="Client Secret"
                          value={oauthSetup[pid]?.clientSecret || ''}
                          onChange={(e) => setOauthSetup(prev => ({ ...prev, [pid]: { ...prev[pid], clientSecret: e.target.value } }))}
                          style={{
                            flex: 1, minWidth: 160, padding: '7px 12px', fontSize: 13,
                            background: 'var(--tile)', border: '1px solid var(--line)',
                            borderRadius: 'var(--r-sm)', color: 'var(--text)',
                          }}
                        />
                      )}
                      <button
                        onClick={() => handleOAuthSetup(pid)}
                        disabled={!oauthSetup[pid]?.clientId}
                        style={{
                          padding: '7px 14px', fontSize: 12, fontWeight: 600,
                          background: oauthSetup[pid]?.clientId ? 'var(--glow)' : 'var(--tile)',
                          color: oauthSetup[pid]?.clientId ? '#000' : 'var(--muted)',
                          border: 'none', borderRadius: 'var(--r-sm)', cursor: 'pointer',
                        }}
                      >Save & Connect</button>
                    </div>
                  </div>
                )}

                {/* Status message */}
                {platformMessage[pid] && (
                  <div style={{
                    marginTop: 6, fontSize: 12, padding: '4px 8px', borderRadius: 'var(--r-sm)',
                    color: platformMessage[pid].includes('✓') ? '#64ff64' : '#ffcc66',
                    background: platformMessage[pid].includes('✓') ? 'rgba(100,255,100,0.1)' : 'rgba(255,200,100,0.1)',
                  }}>
                    {platformMessage[pid]}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Platform Registry — all other platforms grouped by category */}
        {platformData && Object.entries(platformData.platforms || {}).map(([categoryKey, platforms]: [string, any]) => {
          const catInfo = (platformData.categories || {})[categoryKey] || { label: categoryKey, icon: '📦' }
          // Filter out platforms already shown in OAuth providers section
          const filteredPlatforms = (platforms as any[]).filter((p: any) => !oauthProviders[p.id])
          if (filteredPlatforms.length === 0) return null
          return (
            <div key={categoryKey} style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                <span>{catInfo.icon}</span> {catInfo.label}
                <span style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 400 }}>
                  ({filteredPlatforms.filter((p: any) => p.connected).length}/{filteredPlatforms.length} connected)
                </span>
              </div>

              {filteredPlatforms.map((p: any) => (
                <div key={p.id} style={{
                  padding: '12px 16px',
                  background: p.connected ? 'rgba(34, 211, 238, 0.05)' : 'rgba(0,0,0,0.15)',
                  borderRadius: 'var(--r-sm)', marginBottom: 6,
                  border: p.connected ? '1px solid rgba(34, 211, 238, 0.2)' : '1px solid var(--line)',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 18 }}>{p.icon}</span>
                        <span style={{ fontSize: 14, fontWeight: 600, color: p.connected ? 'var(--glow)' : 'var(--text)' }}>
                          {p.name}
                        </span>
                        {p.connected && (
                          <span style={{
                            fontSize: 10, fontWeight: 700, padding: '2px 8px',
                            background: 'rgba(100, 255, 100, 0.15)', color: '#64ff64',
                            borderRadius: 10, border: '1px solid rgba(100, 255, 100, 0.3)',
                          }}>Connected</span>
                        )}
                        {p.free_tier && !p.connected && (
                          <span style={{ fontSize: 10, color: '#64c864' }}>{p.free_tier}</span>
                        )}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {p.description}
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: 6, marginLeft: 12, flexShrink: 0 }}>
                      {p.connected && !p.is_local && (
                        <button onClick={() => handlePlatformDisconnect(p.id)} style={{
                          padding: '5px 12px', fontSize: 11, fontWeight: 500,
                          background: 'transparent', color: '#ff6b6b', border: '1px solid rgba(255,107,107,0.4)',
                          borderRadius: 'var(--r-sm)', cursor: 'pointer',
                        }}>Disconnect</button>
                      )}

                      {p.is_local && p.connected && (
                        <span style={{ fontSize: 11, color: '#64c864', padding: '5px 12px' }}>Available locally</span>
                      )}

                      {!p.connected && (p.auth_method === 'api_key' || p.auth_method === 'token') && (
                        <button onClick={() => {
                          if (tokenInput[p.id]) {
                            handlePlatformConnect(p.id, p.auth_method)
                          } else {
                            setTokenInput(prev => ({ ...prev, [p.id]: ' ' }))
                            setTimeout(() => setTokenInput(prev => ({ ...prev, [p.id]: '' })), 0)
                          }
                        }} style={{
                          padding: '5px 14px', fontSize: 12, fontWeight: 600,
                          background: tokenInput[p.id] ? 'var(--glow)' : 'rgba(34,211,238,0.15)',
                          color: tokenInput[p.id] ? '#000' : 'var(--glow)',
                          border: tokenInput[p.id] ? 'none' : '1px solid rgba(34,211,238,0.3)',
                          borderRadius: 'var(--r-sm)', cursor: 'pointer',
                        }}>{tokenInput[p.id] ? 'Save' : 'Provide Key'}</button>
                      )}

                      {!p.connected && p.auth_method === 'none' && !p.is_local && (
                        <span style={{ fontSize: 11, color: 'var(--muted)', padding: '5px 12px' }}>No setup needed</span>
                      )}
                    </div>
                  </div>

                  {/* Token/key input */}
                  {!p.connected && (p.auth_method === 'api_key' || p.auth_method === 'token') && tokenInput[p.id] !== undefined && (
                    <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
                      <input
                        type="password"
                        placeholder={`Paste ${p.name} ${p.auth_method === 'api_key' ? 'API key' : 'token'}...`}
                        value={tokenInput[p.id] || ''}
                        onChange={(e) => setTokenInput(prev => ({ ...prev, [p.id]: e.target.value }))}
                        style={{
                          flex: 1, padding: '7px 12px', fontSize: 13,
                          background: 'var(--tile)', border: '1px solid var(--line)',
                          borderRadius: 'var(--r-sm)', color: 'var(--text)',
                        }}
                      />
                      {p.setup_url && (
                        <a href={p.setup_url} target="_blank" rel="noopener noreferrer" style={{
                          fontSize: 11, color: 'var(--glow)', textDecoration: 'none', whiteSpace: 'nowrap',
                        }}>Get key →</a>
                      )}
                    </div>
                  )}

                  {/* Capabilities preview */}
                  {p.connected && p.capabilities?.length > 0 && (
                    <div style={{ marginTop: 6, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {p.capabilities.slice(0, 4).map((cap: any) => (
                        <span key={cap.name} style={{
                          fontSize: 10, padding: '2px 8px', borderRadius: 10,
                          background: 'rgba(34,211,238,0.1)', color: 'var(--glow)',
                          border: '1px solid rgba(34,211,238,0.15)',
                        }}>{cap.description}</span>
                      ))}
                      {p.capabilities.length > 4 && (
                        <span style={{ fontSize: 10, color: 'var(--muted)', alignSelf: 'center' }}>+{p.capabilities.length - 4} more</span>
                      )}
                    </div>
                  )}

                  {/* Status message */}
                  {platformMessage[p.id] && (
                    <div style={{
                      marginTop: 6, fontSize: 12, padding: '4px 8px', borderRadius: 'var(--r-sm)',
                      color: platformMessage[p.id].includes('✓') ? '#64ff64' : '#ffcc66',
                      background: platformMessage[p.id].includes('✓') ? 'rgba(100,255,100,0.1)' : 'rgba(255,200,100,0.1)',
                    }}>
                      {platformMessage[p.id]}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )
        })}

        {!platformData && Object.keys(oauthProviders).length === 0 && (
          <div style={{ fontSize: 13, color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
            Connect to the Orion API server to see available platforms.
          </div>
        )}
      </CollapsibleSection>

      {/* Workspace */}
      <CollapsibleSection title="Workspace" description="Current project workspace path">
        <TextInput
          label="Workspace Path"
          description="Root directory for Orion to operate in (AEGIS-1 confinement)"
          value={workspace}
          onChange={setWorkspace}
          placeholder="C:\Projects\MyProject or /home/user/project"
        />
        <div style={{ padding: '12px 16px', background: 'var(--tile)', borderRadius: 'var(--r-sm)' }}>
          <div style={{ fontSize: 13, color: 'var(--muted)' }}>
            Orion can only read and write files within this workspace. This is enforced by AEGIS-1.
          </div>
        </div>
      </CollapsibleSection>

      {/* Core Features */}
      <CollapsibleSection title="Core Features" description="Turn Orion's main capabilities on or off. All are enabled by default.">
        <FeatureToggle
          label="Table of Three"
          description="GPT → Claude → Orion deliberation pipeline"
          enabled={coreFeatures.tableOfThree}
          onToggle={() => setCoreFeatures((p) => ({ ...p, tableOfThree: !p.tableOfThree }))}
        />
        <FeatureToggle
          label="File Tools"
          description="Create, modify, and delete files"
          enabled={coreFeatures.fileTools}
          onToggle={() => setCoreFeatures((p) => ({ ...p, fileTools: !p.fileTools }))}
        />
        <FeatureToggle
          label="Passive Memory"
          description="Read-only memory ingestion"
          enabled={coreFeatures.passiveMemory}
          onToggle={() => setCoreFeatures((p) => ({ ...p, passiveMemory: !p.passiveMemory }))}
        />
        <FeatureToggle
          label="Intelligent Orion"
          description="4-layer memory with quality gates"
          enabled={coreFeatures.intelligentOrion}
          onToggle={() => setCoreFeatures((p) => ({ ...p, intelligentOrion: !p.intelligentOrion }))}
        />
        <FeatureToggle
          label="Streaming"
          description="Stream LLM responses token-by-token"
          enabled={coreFeatures.streaming}
          onToggle={() => setCoreFeatures((p) => ({ ...p, streaming: !p.streaming }))}
        />
      </CollapsibleSection>

      {/* Intelligent Orion Settings */}
      <CollapsibleSection title="Quality Control" description="Control how strict Orion is when checking its own work before showing you results.">
        <NumberInput
          label="Quality Threshold"
          description="Minimum quality score to pass (0.0 to 1.0)"
          value={qualityThreshold}
          onChange={setQualityThreshold}
          min={0}
          max={1}
        />
        <NumberInput
          label="Max Refinement Iterations"
          description="Maximum attempts to meet quality threshold"
          value={maxRefinementIterations}
          onChange={setMaxRefinementIterations}
          min={1}
          max={10}
        />
      </CollapsibleSection>

      {/* Governance */}
      <CollapsibleSection title="Safety Mode" description="Choose how cautious Orion should be. Safe mode asks before every action. Pro mode is faster.">
        <SelectInput
          label="Default Mode"
          description="Starting governance mode"
          value={defaultMode}
          onChange={setDefaultMode}
          options={[
            { value: 'safe', label: 'Safe - Approval for everything' },
            { value: 'pro', label: 'Pro - Auto-approve safe actions' },
            { value: 'project', label: 'Project - Includes command execution' },
          ]}
        />
        <FeatureToggle
          label="AEGIS Strict Mode"
          description="AEGIS governance is always enforced (cannot be disabled)"
          enabled={aegisStrictMode}
          onToggle={() => {}}
        />
      </CollapsibleSection>

      {/* Command Execution */}
      <CollapsibleSection title="Run Commands" description="Allow Orion to run terminal commands like npm install or pytest. Only available in Project mode.">
        <FeatureToggle
          label="Enable Command Execution"
          description="Allow commands in PROJECT mode"
          enabled={commandExecution.enabled}
          onToggle={() => setCommandExecution((p) => ({ ...p, enabled: !p.enabled }))}
        />
        <NumberInput
          label="Command Timeout"
          description="Max time for a single command (seconds)"
          value={commandExecution.timeout}
          onChange={(v) => setCommandExecution((p) => ({ ...p, timeout: v }))}
          min={10}
          max={300}
        />
        <div style={{ padding: '12px 16px', background: 'var(--tile)', borderRadius: 'var(--r-sm)' }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>Allowed Commands</div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>
            dotnet, msbuild, npm, npx, yarn, pnpm, python, pip, pytest, cargo, rustc, go, make, cmake, git
          </div>
        </div>
      </CollapsibleSection>

      {/* Limits */}
      <CollapsibleSection title="Processing Limits" description="Control how many files Orion reads at once. Lower values = faster, higher values = more thorough.">
        <NumberInput
          label="Max Evidence Files"
          description="Maximum files in evidence snapshot"
          value={limits.maxEvidenceFiles}
          onChange={(v) => setLimits((p) => ({ ...p, maxEvidenceFiles: v }))}
          min={10}
          max={1000}
        />
        <NumberInput
          label="Max File Size"
          description="Maximum single file size to read (bytes)"
          value={limits.maxFileSizeBytes}
          onChange={(v) => setLimits((p) => ({ ...p, maxFileSizeBytes: v }))}
          min={10000}
          max={1000000}
        />
        <NumberInput
          label="Max Evidence Retry"
          description="Maximum NEED_MORE_EVIDENCE retries"
          value={limits.maxEvidenceRetry}
          onChange={(v) => setLimits((p) => ({ ...p, maxEvidenceRetry: v }))}
          min={0}
          max={5}
        />
      </CollapsibleSection>

      {/* Web Access */}
      <CollapsibleSection title="Web Access" description="Let Orion fetch documentation and code from the internet. Only allowed domains are accessed.">
        <FeatureToggle
          label="Enable Web Access"
          description="Allow fetching from allowed domains"
          enabled={webAccess.enabled}
          onToggle={() => setWebAccess((p) => ({ ...p, enabled: !p.enabled }))}
        />
        <NumberInput
          label="Cache TTL"
          description="Cache time-to-live in seconds"
          value={webAccess.cacheTTL}
          onChange={(v) => setWebAccess((p) => ({ ...p, cacheTTL: v }))}
          min={60}
          max={86400}
        />
        <TextInput
          label="Allowed Domains"
          description="Comma-separated list of allowed domains"
          value={allowedDomains}
          onChange={setAllowedDomains}
          placeholder="github.com, docs.python.org"
        />
      </CollapsibleSection>

      {/* Image Generation */}
      <CollapsibleSection title="Image Generation" description="Generate images using local (free) or cloud (paid) AI. SDXL runs on your GPU, DALL-E uses OpenAI.">
        <SelectInput
          label="Image Provider"
          description="Which provider to use for image generation"
          value={imageProvider}
          onChange={setImageProvider}
          options={[
            { value: 'auto', label: 'Auto - Best available' },
            { value: 'sdxl', label: 'SDXL - Local offline' },
            { value: 'flux', label: 'FLUX - Premium local' },
            { value: 'dalle', label: 'DALL-E - Cloud' },
          ]}
        />
        <div style={{ marginTop: 16, marginBottom: 8, fontSize: 13, color: 'var(--muted)' }}>SDXL (Local)</div>
        <FeatureToggle
          label="SDXL Enabled"
          description="Enable local SDXL generation"
          enabled={imageSettings.sdxlEnabled}
          onToggle={() => setImageSettings((p) => ({ ...p, sdxlEnabled: !p.sdxlEnabled }))}
        />
        <TextInput
          label="SDXL Endpoint"
          description="ComfyUI endpoint URL"
          value={imageSettings.sdxlEndpoint}
          onChange={(v) => setImageSettings((p) => ({ ...p, sdxlEndpoint: v }))}
        />
        <div style={{ marginTop: 16, marginBottom: 8, fontSize: 13, color: 'var(--muted)' }}>FLUX (Premium Local)</div>
        <FeatureToggle
          label="FLUX Enabled"
          description="Enable FLUX generation (requires more VRAM)"
          enabled={imageSettings.fluxEnabled}
          onToggle={() => setImageSettings((p) => ({ ...p, fluxEnabled: !p.fluxEnabled }))}
        />
        <div style={{ marginTop: 16, marginBottom: 8, fontSize: 13, color: 'var(--muted)' }}>DALL-E (Cloud)</div>
        <FeatureToggle
          label="DALL-E Enabled"
          description="Enable DALL-E cloud fallback"
          enabled={imageSettings.dalleEnabled}
          onToggle={() => setImageSettings((p) => ({ ...p, dalleEnabled: !p.dalleEnabled }))}
        />
        <SelectInput
          label="DALL-E Model"
          description="Which DALL-E model to use"
          value={imageSettings.dalleModel}
          onChange={(v) => setImageSettings((p) => ({ ...p, dalleModel: v }))}
          options={[
            { value: 'dall-e-3', label: 'DALL-E 3' },
            { value: 'dall-e-2', label: 'DALL-E 2' },
          ]}
        />
      </CollapsibleSection>

      {/* Model Configuration */}
      <CollapsibleSection title="AI Model Setup" description="Pick which AI models Orion uses. Start with a preset or customize each role individually.">
        {/* Quick Presets */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)', marginBottom: 12 }}>Quick Presets</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {Object.entries(presets).map(([name, preset]: [string, any]) => {
              const isActive = builderProvider === preset.builder.provider
                && builderModel === preset.builder.model
                && reviewerProvider === preset.reviewer.provider
                && reviewerModel === preset.reviewer.model
              return (
                <button
                  key={name}
                  onClick={() => handleApplyPreset(name)}
                  style={{
                    padding: '10px 16px',
                    background: isActive ? 'rgba(159, 214, 255, 0.15)' : 'var(--tile)',
                    border: isActive ? '2px solid var(--glow)' : '1px solid var(--line)',
                    borderRadius: 'var(--r-md)',
                    cursor: 'pointer',
                    textAlign: 'left',
                    minWidth: 140,
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600, color: isActive ? 'var(--glow)' : 'var(--text)' }}>
                    {name.replace(/_/g, ' ')}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
                    {preset.required_keys.length === 0 ? 'Free' : `Keys: ${preset.required_keys.join(', ')}`}
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* Mode Toggle */}
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)', marginBottom: 8 }}>Mode</div>
          <div style={{ display: 'flex', gap: 12 }}>
            <button
              onClick={() => { setModelMode('single'); handleSaveModelConfig('single') }}
              style={{
                flex: 1, padding: '12px 16px',
                background: modelMode === 'single' ? 'rgba(159, 214, 255, 0.15)' : 'var(--tile)',
                border: modelMode === 'single' ? '2px solid var(--glow)' : '1px solid var(--line)',
                borderRadius: 'var(--r-md)', cursor: 'pointer', textAlign: 'left',
              }}
            >
              <div style={{ fontSize: 14, fontWeight: 500, color: modelMode === 'single' ? 'var(--glow)' : 'var(--text)' }}>
                Single Model
              </div>
              <div style={{ fontSize: 12, color: 'var(--muted)' }}>One model for both Builder and Reviewer</div>
            </button>
            <button
              onClick={() => { setModelMode('dual'); handleSaveModelConfig('dual') }}
              style={{
                flex: 1, padding: '12px 16px',
                background: modelMode === 'dual' ? 'rgba(159, 214, 255, 0.15)' : 'var(--tile)',
                border: modelMode === 'dual' ? '2px solid var(--glow)' : '1px solid var(--line)',
                borderRadius: 'var(--r-md)', cursor: 'pointer', textAlign: 'left',
              }}
            >
              <div style={{ fontSize: 14, fontWeight: 500, color: modelMode === 'dual' ? 'var(--glow)' : 'var(--text)' }}>
                Dual Model
              </div>
              <div style={{ fontSize: 12, color: 'var(--muted)' }}>Different models for Builder and Reviewer</div>
            </button>
          </div>
        </div>

        {/* Builder Config */}
        <div style={{ padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--r-md)', marginBottom: 12 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--glow)', marginBottom: 12 }}>Builder {modelMode === 'single' ? '(+ Reviewer)' : ''}</div>
          <SelectInput
            label="Provider"
            description="AI provider for code generation"
            value={builderProvider}
            onChange={(v) => {
              setBuilderProvider(v)
              const p = providers[v]
              if (p) {
                setBuilderModel(p.default_heavy || p.models?.[0]?.id || '')
                setBuilderLightModel(p.default_light || '')
              }
              if (modelMode === 'single') {
                setReviewerProvider(v)
                if (p) {
                  setReviewerModel(p.default_heavy || p.models?.[0]?.id || '')
                  setReviewerLightModel(p.default_light || '')
                }
              }
            }}
            options={Object.entries(providers).map(([key, info]: [string, any]) => ({
              value: key, label: `${info.name} (${info.cost})`,
            }))}
          />
          <SelectInput
            label="Heavy Model (Reasoning)"
            description="Used for code generation, deep review, complex tasks"
            value={builderModel}
            onChange={(v) => { setBuilderModel(v); if (modelMode === 'single') setReviewerModel(v) }}
            options={getModelOptions(builderProvider)}
          />
          <FeatureToggle
            label="Enable Light/Heavy Tiers"
            description="Use a cheaper model for simple tasks (routing, formatting) to save costs"
            enabled={builderUseTiers}
            onToggle={() => {
              const next = !builderUseTiers
              setBuilderUseTiers(next)
              if (next && !builderLightModel) {
                const p = providers[builderProvider]
                setBuilderLightModel(p?.default_light || '')
              }
              if (modelMode === 'single') {
                setReviewerUseTiers(next)
                if (next && !reviewerLightModel) {
                  const p = providers[reviewerProvider]
                  setReviewerLightModel(p?.default_light || '')
                }
              }
            }}
          />
          {builderUseTiers && (
            <SelectInput
              label="Light Model (Fast/Cheap)"
              description="Used for routing, classification, formatting — saves tokens"
              value={builderLightModel}
              onChange={(v) => { setBuilderLightModel(v); if (modelMode === 'single') setReviewerLightModel(v) }}
              options={getModelOptions(builderProvider, 'light')}
            />
          )}
        </div>

        {/* Reviewer Config - Only in dual mode */}
        {modelMode === 'dual' && (
          <div style={{ padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: 'var(--r-md)', marginBottom: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--glow)', marginBottom: 12 }}>Reviewer</div>
            <SelectInput
              label="Provider"
              description="AI provider for code review"
              value={reviewerProvider}
              onChange={(v) => {
                setReviewerProvider(v)
                const p = providers[v]
                if (p) {
                  setReviewerModel(p.default_heavy || p.models?.[0]?.id || '')
                  setReviewerLightModel(p.default_light || '')
                }
              }}
              options={Object.entries(providers).map(([key, info]: [string, any]) => ({
                value: key, label: `${info.name} (${info.cost})`,
              }))}
            />
            <SelectInput
              label="Heavy Model (Reasoning)"
              description="Used for deep code review, complex analysis"
              value={reviewerModel}
              onChange={(v) => setReviewerModel(v)}
              options={getModelOptions(reviewerProvider)}
            />
            <FeatureToggle
              label="Enable Light/Heavy Tiers"
              description="Use a cheaper model for simple review tasks to save costs"
              enabled={reviewerUseTiers}
              onToggle={() => {
                const next = !reviewerUseTiers
                setReviewerUseTiers(next)
                if (next && !reviewerLightModel) {
                  const p = providers[reviewerProvider]
                  setReviewerLightModel(p?.default_light || '')
                }
              }}
            />
            {reviewerUseTiers && (
              <SelectInput
                label="Light Model (Fast/Cheap)"
                description="Used for simple checks and formatting — saves tokens"
                value={reviewerLightModel}
                onChange={(v) => setReviewerLightModel(v)}
                options={getModelOptions(reviewerProvider, 'light')}
              />
            )}
          </div>
        )}

        {/* Governor (always Orion) */}
        <div style={{ padding: '12px 16px', background: 'rgba(34, 211, 238, 0.08)', border: '1px solid rgba(34, 211, 238, 0.2)', borderRadius: 'var(--r-md)', marginBottom: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--glow)' }}>Governor: Orion (hardcoded)</div>
          <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>
            The Governor is Orion's internal decision layer. It learns over time and is never user-configurable.
          </div>
        </div>

        {/* Save Button */}
        <button
          onClick={() => handleSaveModelConfig()}
          style={{
            width: '100%', padding: '12px', fontSize: 14, fontWeight: 600,
            background: 'var(--glow)', color: '#000', border: 'none',
            borderRadius: 'var(--r-md)', cursor: 'pointer',
          }}
        >
          Save Model Configuration
        </button>
      </CollapsibleSection>

      {/* Autonomous Roles (ARA) */}
      <CollapsibleSection title="Autonomous Roles (ARA)" description="Configure background task execution with configurable roles, AEGIS-gated promotion, and session controls.">
        <div style={{ padding: '12px 16px', background: 'rgba(59, 130, 246, 0.08)', borderRadius: 'var(--r-sm)', marginBottom: 16, border: '1px solid rgba(59, 130, 246, 0.2)' }}>
          <div style={{ fontSize: 13, color: 'var(--glow)' }}>
            ARA lets Orion work autonomously in the background with configurable roles, security gates, and human-in-the-loop promotion. <a href="/ara" style={{ color: 'var(--glow)', textDecoration: 'underline' }}>Open ARA Dashboard →</a>
          </div>
        </div>
        <FeatureToggle
          label="ARA Enabled"
          description="Enable the Autonomous Role Architecture for background tasks"
          enabled={araSettings.enabled}
          onToggle={() => setAraSettings(p => ({ ...p, enabled: !p.enabled }))}
        />
        <SelectInput
          label="Default Auth Method"
          description="Authentication method for autonomous sessions"
          value={araSettings.defaultAuth}
          onChange={(v) => setAraSettings(p => ({ ...p, defaultAuth: v }))}
          options={[
            { value: 'pin', label: 'PIN (4-digit)' },
            { value: 'totp', label: 'TOTP (authenticator app)' },
            { value: 'none', label: 'None (no auth)' },
          ]}
        />
        <NumberInput
          label="Max Cost Per Session (USD)"
          description="Maximum USD cost per autonomous session before auto-stop"
          value={araSettings.maxCostUsd}
          onChange={(v) => setAraSettings(p => ({ ...p, maxCostUsd: v }))}
          min={1}
          max={100}
        />
        <NumberInput
          label="Max Session Duration (hours)"
          description="Maximum hours an autonomous session can run"
          value={araSettings.maxSessionHours}
          onChange={(v) => setAraSettings(p => ({ ...p, maxSessionHours: v }))}
          min={1}
          max={24}
        />
        <SelectInput
          label="ARA Sandbox Mode"
          description="Isolation strategy for autonomous work"
          value={araSettings.sandboxMode}
          onChange={(v) => setAraSettings(p => ({ ...p, sandboxMode: v }))}
          options={[
            { value: 'docker', label: 'Docker (full isolation)' },
            { value: 'branch', label: 'Branch (git branch sandbox)' },
            { value: 'local', label: 'Local (temp directory)' },
          ]}
        />
        <FeatureToggle
          label="Prompt Guard"
          description="Enable prompt injection defence for ARA sessions (12 patterns)"
          enabled={araSettings.promptGuard}
          onToggle={() => setAraSettings(p => ({ ...p, promptGuard: !p.promptGuard }))}
        />
        <FeatureToggle
          label="Audit Log"
          description="Enable tamper-proof HMAC-SHA256 audit logging for ARA sessions"
          enabled={araSettings.auditLog}
          onToggle={() => setAraSettings(p => ({ ...p, auditLog: !p.auditLog }))}
        />

        <div style={{ marginTop: 16, marginBottom: 8, fontSize: 13, color: 'var(--muted)' }}>ARA CLI Commands</div>
        <CommandItem command="/setup" description="Run first-time ARA setup wizard" />
        <CommandItem command="/work <role> <goal>" description="Start an autonomous background session" />
        <CommandItem command="/pause / /resume / /cancel" description="Control the running session" />
        <CommandItem command="/review" description="Review sandbox changes for promotion" />
        <CommandItem command="/sessions" description="List all sessions" />
        <CommandItem command="/dashboard" description="Show morning dashboard TUI" />
        <CommandItem command="/role list | show | create | delete" description="Manage roles" />
        <CommandItem command="/ara-settings" description="View or update ARA-specific settings" />
      </CollapsibleSection>

      {/* Paths */}
      <CollapsibleSection title="Storage Paths" description="Where Orion keeps its data files. Usually you don't need to change these.">
        <TextInput
          label="Data Directory"
          description="Directory for Orion data files"
          value={paths.dataDir}
          onChange={(v) => setPaths((p) => ({ ...p, dataDir: v }))}
        />
        <TextInput
          label="Ledger File"
          description="Path to immutable ledger"
          value={paths.ledgerFile}
          onChange={(v) => setPaths((p) => ({ ...p, ledgerFile: v }))}
        />
      </CollapsibleSection>

      {/* Privacy & Data (GDPR) */}
      <CollapsibleSection title="Privacy & Your Data" description="See what data Orion stores, export it, or delete everything. Your data never leaves your computer.">
        <div style={{ padding: '12px 16px', background: 'rgba(100, 200, 100, 0.1)', borderRadius: 'var(--r-sm)', marginBottom: 12, border: '1px solid rgba(100, 200, 100, 0.3)' }}>
          <div style={{ fontSize: 13, color: '#64c864' }}>
            🔒 All your data stays on your machine and is never shared with third parties.
          </div>
        </div>
        
        <div style={{ padding: '16px', background: 'var(--tile)', borderRadius: 'var(--r-md)', marginBottom: 12 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)', marginBottom: 8 }}>Data Storage</div>
          <div style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6 }}>
            • API keys are stored locally in ~/.orion/<br/>
            • Settings stored locally in JSON files<br/>
            • No data is sent to external servers (except your chosen AI provider API calls)<br/>
            • You can export or delete all data at any time using the buttons below
          </div>
        </div>

        <div style={{ padding: '16px', background: 'var(--tile)', borderRadius: 'var(--r-md)', marginBottom: 12 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)', marginBottom: 8 }}>Your Rights (GDPR)</div>
          <div style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
            <button
              onClick={async () => {
                if (!isConnected) return
                try {
                  const data = await api.exportAllData()
                  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `orion-data-export-${new Date().toISOString().split('T')[0]}.json`
                  a.click()
                  URL.revokeObjectURL(url)
                } catch (err) {
                  console.error('Export failed:', err)
                }
              }}
              disabled={!isConnected}
              style={{
                padding: '10px 16px',
                fontSize: 13,
                background: 'rgba(159, 214, 255, 0.1)',
                border: '1px solid var(--line)',
                borderRadius: 'var(--r-sm)',
                color: isConnected ? 'var(--glow)' : 'var(--muted)',
                cursor: isConnected ? 'pointer' : 'not-allowed',
              }}
            >
              📥 Export My Data
            </button>
            <button
              onClick={async () => {
                if (!isConnected) return
                if (confirm('Are you sure you want to delete ALL your data? This cannot be undone.')) {
                  try {
                    await api.deleteAllData()
                    alert('All data has been deleted.')
                    window.location.reload()
                  } catch (err) {
                    console.error('Delete failed:', err)
                  }
                }
              }}
              disabled={!isConnected}
              style={{
                padding: '10px 16px',
                fontSize: 13,
                background: 'rgba(255, 100, 100, 0.1)',
                border: '1px solid rgba(255, 100, 100, 0.3)',
                borderRadius: 'var(--r-sm)',
                color: isConnected ? '#ff6464' : 'var(--muted)',
                cursor: isConnected ? 'pointer' : 'not-allowed',
              }}
            >
              🗑️ Delete All My Data
            </button>
          </div>
        </div>
      </CollapsibleSection>

      {/* Commands Reference */}
      <CollapsibleSection title="Quick Reference" description="Handy commands you can type in the chat. Use these to control Orion directly.">
        <div style={{ marginBottom: 12, fontSize: 13, color: 'var(--muted)' }}>Workspace</div>
        <CommandItem command="/workspace <path>" description="Set project workspace" />
        <CommandItem command="/workspace add <name> <path>" description="Add named workspace" />
        <CommandItem command="/workspace switch <name>" description="Switch to workspace" />
        <CommandItem command="/workspace list" description="List all workspaces" />

        <div style={{ marginTop: 16, marginBottom: 12, fontSize: 13, color: 'var(--muted)' }}>Context</div>
        <CommandItem command="/add <file>" description="Add file to context" />
        <CommandItem command="/drop <file>" description="Remove file from context" />
        <CommandItem command="/clear" description="Clear all context" />

        <div style={{ marginTop: 16, marginBottom: 12, fontSize: 13, color: 'var(--muted)' }}>Actions</div>
        <CommandItem command="/undo" description="Revert last change" />
        <CommandItem command="/diff" description="Show pending changes" />
        <CommandItem command="/commit [msg]" description="Commit changes to git" />

        <div style={{ marginTop: 16, marginBottom: 12, fontSize: 13, color: 'var(--muted)' }}>Tasks</div>
        <CommandItem command="/tasks" description="List background tasks" />
        <CommandItem command="/task <id>" description="Show task details" />
        <CommandItem command="/task cancel <id>" description="Cancel pending task" />

        <div style={{ marginTop: 16, marginBottom: 12, fontSize: 13, color: 'var(--muted)' }}>Modes</div>
        <CommandItem command="/mode safe" description="Safest mode - approval for everything" />
        <CommandItem command="/mode pro" description="Faster mode - auto-approve safe actions" />
        <CommandItem command="/mode project" description="Full mode - includes command execution" />

        <div style={{ marginTop: 16, marginBottom: 12, fontSize: 13, color: 'var(--muted)' }}>Settings</div>
        <CommandItem command="/settings api <provider> <key>" description="Set API key securely" />
        <CommandItem command="/settings show" description="Show current configuration" />

        <div style={{ marginTop: 16, marginBottom: 12, fontSize: 13, color: 'var(--muted)' }}>Autonomous Roles (ARA)</div>
        <CommandItem command="/setup" description="Run first-time ARA setup wizard" />
        <CommandItem command="/work <role> <goal>" description="Start autonomous background session" />
        <CommandItem command="/pause" description="Pause the running session" />
        <CommandItem command="/resume" description="Resume a paused session" />
        <CommandItem command="/cancel" description="Cancel the running session" />
        <CommandItem command="/review [session_id]" description="Review sandbox changes for promotion" />
        <CommandItem command="/sessions" description="List all ARA sessions" />
        <CommandItem command="/dashboard" description="Show morning dashboard" />
        <CommandItem command="/role list | show | create | delete" description="Manage ARA roles" />
        <CommandItem command="/rollback [session_id]" description="Rollback promoted changes" />
        <CommandItem command="/ara-settings" description="View/update ARA settings" />
        <CommandItem command="/auth-switch <method>" description="Switch auth method (pin/totp)" />
      </CollapsibleSection>

      {/* Save Button */}
      <div style={{ marginTop: 32, display: 'flex', gap: 12 }}>
        <Button variant="primary" onClick={handleSaveAllSettings}>Save Settings</Button>
        <Link href="/chat">
          <Button variant="secondary">Ask Orion</Button>
        </Link>
      </div>
    </div>
  )
}
