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

  const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

  const loadOAuthStatus = () => {
    fetch(`${API_BASE}/api/oauth/status`)
      .then(r => r.ok ? r.json() : null)
      .then(s => { if (s) setOauthStatus(s) })
      .catch(() => {})
  }

  // Load all settings + model config + OAuth status on mount
  useEffect(() => {
    if (!isConnected) return
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
        loadOAuthStatus()
      }
    } catch (err) {
      console.error('OAuth login failed:', err)
    } finally {
      setOauthLoading(null)
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

      {/* LLM Provider Enable/Disable (v5.1.0) */}
      <CollapsibleSection title="AI Providers" description="Choose which AI services are available. Disable any you don't use to keep things simple.">
        <div style={{ padding: '12px 16px', background: 'rgba(34, 211, 238, 0.08)', borderRadius: 'var(--r-sm)', marginBottom: 16, border: '1px solid rgba(34, 211, 238, 0.2)' }}>
          <div style={{ fontSize: 13, color: 'var(--glow)' }}>
            Toggle providers on/off. Disabled providers won't appear in Builder/Reviewer dropdowns. All providers are enabled by default.
          </div>
        </div>
        {Object.entries(providers).map(([key, info]: [string, any]) => (
          <div key={key} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '10px 16px', background: 'rgba(0,0,0,0.15)', borderRadius: 'var(--r-sm)',
            marginBottom: 6, border: `1px solid ${info.enabled !== false ? 'rgba(34,211,238,0.15)' : 'var(--line)'}`,
            opacity: info.enabled !== false ? 1 : 0.5,
          }}>
            <div>
              <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{info.name || key}</span>
              <span style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 8 }}>
                {(info.models || []).length} models · {info.cost || '?'}
              </span>
            </div>
            <button
              onClick={() => handleToggleProvider(key, info.enabled === false)}
              style={{
                padding: '4px 14px', fontSize: 12, fontWeight: 600, borderRadius: 'var(--r-sm)', cursor: 'pointer',
                background: info.enabled !== false ? 'rgba(34,211,238,0.15)' : 'rgba(255,255,255,0.05)',
                color: info.enabled !== false ? 'var(--glow)' : 'var(--muted)',
                border: info.enabled !== false ? '1px solid rgba(34,211,238,0.3)' : '1px solid var(--line)',
              }}
            >
              {info.enabled !== false ? 'Enabled' : 'Disabled'}
            </button>
          </div>
        ))}
      </CollapsibleSection>

      {/* OAuth Authentication (v2.4.0) */}
      <CollapsibleSection title="Connected Accounts" description="Link your Google, GitHub, GitLab, or Microsoft accounts to unlock extra features and free AI access.">
        <div style={{ padding: '12px 16px', background: 'rgba(34, 211, 238, 0.08)', borderRadius: 'var(--r-sm)', marginBottom: 16, border: '1px solid rgba(34, 211, 238, 0.2)' }}>
          <div style={{ fontSize: 13, color: 'var(--glow)' }}>
            OAuth lets you use existing accounts instead of raw API keys. Google Gemini free tier = 1500 req/day at no cost.
          </div>
        </div>

        {Object.entries(oauthStatus).map(([name, status]: [string, any]) => (
          <div key={name} style={{
            padding: '16px',
            background: 'rgba(0,0,0,0.2)',
            borderRadius: 'var(--r-md)',
            marginBottom: 12,
            border: status.authenticated ? '1px solid rgba(34, 211, 238, 0.3)' : '1px solid var(--line)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <div>
                <span style={{ fontSize: 14, fontWeight: 600, color: status.authenticated ? 'var(--glow)' : 'var(--text)' }}>
                  {status.name || name.charAt(0).toUpperCase() + name.slice(1)}
                </span>
                <span style={{ fontSize: 12, color: 'var(--muted)', marginLeft: 8 }}>
                  {status.authenticated ? 'Authenticated' : status.configured ? 'Configured' : 'Not configured'}
                </span>
                {status.free_tier && (
                  <span style={{ fontSize: 11, color: '#64c864', marginLeft: 8 }}>
                    {status.free_tier}
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                {status.configured && !status.authenticated && (
                  <button
                    onClick={() => handleOAuthLogin(name)}
                    disabled={oauthLoading === name}
                    style={{
                      padding: '6px 14px', fontSize: 12, fontWeight: 600,
                      background: 'var(--glow)', color: '#000', border: 'none',
                      borderRadius: 'var(--r-sm)', cursor: 'pointer',
                      opacity: oauthLoading === name ? 0.5 : 1,
                    }}
                  >
                    {oauthLoading === name ? 'Waiting...' : 'Login'}
                  </button>
                )}
                {status.authenticated && (
                  <button
                    onClick={() => handleOAuthRevoke(name)}
                    style={{
                      padding: '6px 14px', fontSize: 12, fontWeight: 500,
                      background: 'transparent', color: '#ff6b6b', border: '1px solid #ff6b6b',
                      borderRadius: 'var(--r-sm)', cursor: 'pointer',
                    }}
                  >
                    Revoke
                  </button>
                )}
              </div>
            </div>

            {status.description && (
              <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 6 }}>
                {status.description}
              </div>
            )}

            {status.authenticated && status.expires_at && (
              <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                Expires: {new Date(status.expires_at).toLocaleString()}
                {status.scopes && <span> | Scopes: {status.scopes}</span>}
              </div>
            )}

            {!status.configured && (
              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 8 }}>
                  Enter your OAuth app credentials to enable login:
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <input
                    type="text"
                    placeholder="Client ID"
                    value={getOauthCred(name).clientId}
                    onChange={(e) => setOauthCred(name, 'clientId', e.target.value)}
                    style={{
                      flex: 1, minWidth: 180, padding: '8px 12px', fontSize: 13,
                      background: 'var(--tile)', border: '1px solid var(--line)',
                      borderRadius: 'var(--r-sm)', color: 'var(--text)',
                    }}
                  />
                  <input
                    type="password"
                    placeholder="Client Secret (optional)"
                    value={getOauthCred(name).clientSecret}
                    onChange={(e) => setOauthCred(name, 'clientSecret', e.target.value)}
                    style={{
                      flex: 1, minWidth: 180, padding: '8px 12px', fontSize: 13,
                      background: 'var(--tile)', border: '1px solid var(--line)',
                      borderRadius: 'var(--r-sm)', color: 'var(--text)',
                    }}
                  />
                  <button
                    onClick={() => handleOAuthConfigure(name)}
                    disabled={!getOauthCred(name).clientId}
                    style={{
                      padding: '8px 16px', fontSize: 12, fontWeight: 600,
                      background: getOauthCred(name).clientId ? 'var(--glow)' : 'var(--tile)',
                      color: getOauthCred(name).clientId ? '#000' : 'var(--muted)',
                      border: 'none', borderRadius: 'var(--r-sm)', cursor: 'pointer',
                    }}
                  >
                    Configure
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}

        {Object.keys(oauthStatus).length === 0 && (
          <div style={{ fontSize: 13, color: 'var(--muted)', textAlign: 'center', padding: 20 }}>
            No OAuth platforms available. Check your Orion installation.
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
