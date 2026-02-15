/**
 * ORION Web UI - API Client
 * 
 * Connects to the Orion API server for settings and configuration.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001'

export interface APIKeyStatus {
  provider: string
  configured: boolean
  description: string
}

export interface Settings {
  // Core Features
  enable_table_of_three: boolean
  enable_file_tools: boolean
  enable_passive_memory: boolean
  enable_intelligent_orion: boolean
  enable_streaming: boolean
  
  // Intelligent Orion
  quality_threshold: number
  max_refinement_iterations: number
  
  // Governance
  aegis_strict_mode: boolean
  default_mode: string
  valid_modes: string[]
  
  // Command Execution
  enable_command_execution: boolean
  command_timeout_seconds: number
  
  // Limits
  max_evidence_files: number
  max_file_size_bytes: number
  max_evidence_retry: number
  
  // Web Access
  web_cache_ttl: number
  enable_web_access: boolean
  allowed_domains: string
  
  // Image Generation
  image_provider: string
  sdxl_enabled: boolean
  sdxl_endpoint: string
  sdxl_timeout: number
  flux_enabled: boolean
  flux_endpoint: string
  flux_timeout: number
  dalle_enabled: boolean
  dalle_model: string
  dalle_timeout: number
  
  // Models
  use_local_models: boolean
  model_mode: string
  gpt_model: string
  claude_model: string
  ollama_base_url: string
  ollama_builder_model: string
  ollama_reviewer_model: string
  ollama_timeout: number
  
  // Paths
  data_dir: string
  ledger_file: string
  
  // Workspace
  workspace: string
}

export interface ModelMode {
  mode: string
  use_local_models: boolean
  description: string
}

export interface OllamaStatus {
  available: boolean
  endpoint: string
  error?: string
}

/**
 * Check if the API server is healthy
 */
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`)
    return res.ok
  } catch {
    return false
  }
}

/**
 * Get API key status for all providers
 */
export async function getAPIKeyStatus(): Promise<APIKeyStatus[]> {
  const res = await fetch(`${API_BASE}/api/keys/status`)
  if (!res.ok) throw new Error('Failed to get API key status')
  return res.json()
}

/**
 * Set an API key
 */
export async function setAPIKey(provider: string, key: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/keys/set`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, key })
  })
  if (!res.ok) {
    const error = await res.json()
    throw new Error(error.detail || 'Failed to set API key')
  }
}

/**
 * Remove an API key
 */
export async function removeAPIKey(provider: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/keys/${provider}`, {
    method: 'DELETE'
  })
  if (!res.ok) {
    const error = await res.json()
    throw new Error(error.detail || 'Failed to remove API key')
  }
}

/**
 * Get current model config (replaces legacy getModelMode)
 */
export async function getModelConfig(): Promise<object> {
  const res = await fetch(`${API_BASE}/api/models/config`)
  if (!res.ok) throw new Error('Failed to get model config')
  return res.json()
}

/**
 * Get all settings
 */
export async function getSettings(): Promise<Settings> {
  const res = await fetch(`${API_BASE}/api/settings`)
  if (!res.ok) throw new Error('Failed to get settings')
  return res.json()
}

/**
 * Update settings
 */
export async function updateSettings(settings: Partial<Settings>): Promise<void> {
  const res = await fetch(`${API_BASE}/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings)
  })
  if (!res.ok) {
    const error = await res.json()
    throw new Error(error.detail || 'Failed to update settings')
  }
}

/**
 * Set workspace path
 */
export async function setWorkspace(workspace: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/settings/workspace`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(workspace)
  })
  if (!res.ok) {
    const error = await res.json()
    throw new Error(error.detail || 'Failed to set workspace')
  }
}

/**
 * Get Ollama status via integration health
 */
export async function getOllamaStatus(): Promise<OllamaStatus> {
  try {
    const res = await fetch(`${API_BASE}/api/integrations/health`)
    if (!res.ok) return { available: false, endpoint: 'http://localhost:11434', error: 'Health check failed' }
    const data = await res.json()
    const ollamaCheck = data?.checks?.find?.((c: any) => c.name?.includes?.('ollama'))
    return {
      available: ollamaCheck?.healthy ?? false,
      endpoint: 'http://localhost:11434',
      error: ollamaCheck?.error,
    }
  } catch {
    return { available: false, endpoint: 'http://localhost:11434', error: 'Connection failed' }
  }
}

// =============================================================================
// GDPR COMPLIANCE
// =============================================================================

export interface GDPRConsents {
  consents: { [key: string]: boolean }
  policy_version: string
}

export interface AuditLogEntry {
  action: string
  data_type: string
  timestamp: string
  details: string | null
}

/**
 * Get GDPR consent statuses
 */
export async function getGDPRConsents(): Promise<GDPRConsents> {
  const res = await fetch(`${API_BASE}/api/gdpr/consents`)
  if (!res.ok) throw new Error('Failed to get GDPR consents')
  return res.json()
}

/**
 * Set GDPR consent
 */
export async function setGDPRConsent(consentType: string, granted: boolean): Promise<void> {
  const res = await fetch(`${API_BASE}/api/gdpr/consent/${consentType}?granted=${granted}`, {
    method: 'POST'
  })
  if (!res.ok) throw new Error('Failed to set GDPR consent')
}

/**
 * Export all user data (GDPR right to data portability)
 */
export async function exportAllData(): Promise<object> {
  const res = await fetch(`${API_BASE}/api/gdpr/export`)
  if (!res.ok) throw new Error('Failed to export data')
  return res.json()
}

/**
 * Delete all user data (GDPR right to erasure)
 */
export async function deleteAllData(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/gdpr/data`, {
    method: 'DELETE'
  })
  if (!res.ok) throw new Error('Failed to delete data')
}

/**
 * Get GDPR audit log
 */
export async function getAuditLog(limit: number = 100): Promise<{ audit_log: AuditLogEntry[] }> {
  const res = await fetch(`${API_BASE}/api/gdpr/audit?limit=${limit}`)
  if (!res.ok) throw new Error('Failed to get audit log')
  return res.json()
}

// =============================================================================
// ARA (Autonomous Role Architecture)
// =============================================================================

export interface ARAStatus {
  success: boolean
  message: string
  data: Record<string, any> | null
}

export interface ARARole {
  name: string
  scope: string
  auth_method: string
  source: string
}

export interface ARASession {
  session_id: string
  role: string
  goal: string
  status: string
}

export interface ARADashboard {
  success: boolean
  rendered: string
  data: {
    sections: { title: string; content: string; style: string }[]
    pending_count: number
  }
}

/**
 * Get ARA session status
 */
export async function getARAStatus(): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/status`)
  if (!res.ok) throw new Error('Failed to get ARA status')
  return res.json()
}

/**
 * Start an autonomous work session
 */
export async function startARAWork(roleName: string, goal: string, workspacePath?: string): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/work`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role_name: roleName, goal, workspace_path: workspacePath })
  })
  if (!res.ok) {
    const error = await res.json()
    throw new Error(error.detail || 'Failed to start work session')
  }
  return res.json()
}

/**
 * Pause the running ARA session
 */
export async function pauseARASession(): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/pause`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to pause session')
  return res.json()
}

/**
 * Resume a paused ARA session
 */
export async function resumeARASession(): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/resume`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to resume session')
  return res.json()
}

/**
 * Cancel the running ARA session
 */
export async function cancelARASession(): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/cancel`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to cancel session')
  return res.json()
}

/**
 * List all ARA sessions
 */
export async function getARASessions(): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/sessions`)
  if (!res.ok) throw new Error('Failed to get sessions')
  return res.json()
}

/**
 * List all ARA roles
 */
export async function getARARoles(): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/roles`)
  if (!res.ok) throw new Error('Failed to get roles')
  return res.json()
}

/**
 * Get ARA role details
 */
export async function getARARole(roleName: string): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/roles/${encodeURIComponent(roleName)}`)
  if (!res.ok) throw new Error('Failed to get role details')
  return res.json()
}

/**
 * Get ARA morning dashboard
 */
export async function getARADashboard(workspacePath?: string): Promise<ARADashboard> {
  const params = workspacePath ? `?workspace_path=${encodeURIComponent(workspacePath)}` : ''
  const res = await fetch(`${API_BASE}/api/ara/dashboard${params}`)
  if (!res.ok) throw new Error('Failed to get dashboard')
  return res.json()
}

/**
 * Get ARA setup status
 */
export async function getARASetup(): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/setup`)
  if (!res.ok) throw new Error('Failed to get setup status')
  return res.json()
}

/**
 * Get ARA-specific settings
 */
export async function getARASettings(): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/settings`)
  if (!res.ok) throw new Error('Failed to get ARA settings')
  return res.json()
}

/**
 * Update ARA-specific settings
 */
export async function updateARASettings(settings: Record<string, any>): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings })
  })
  if (!res.ok) throw new Error('Failed to update ARA settings')
  return res.json()
}

/**
 * Review sandbox changes for promotion
 */
export async function reviewARASession(sessionId?: string): Promise<ARAStatus> {
  const params = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
  const res = await fetch(`${API_BASE}/api/ara/review${params}`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to review session')
  return res.json()
}

/**
 * Create a new ARA role
 */
export async function createARARole(name: string, scope: string, authMethod: string, description: string): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/roles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, scope, auth_method: authMethod, description })
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to create role')
  }
  return res.json()
}

/**
 * Delete an ARA role
 */
export async function deleteARARole(roleName: string): Promise<ARAStatus> {
  const res = await fetch(`${API_BASE}/api/ara/roles/${encodeURIComponent(roleName)}`, {
    method: 'DELETE'
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to delete role')
  }
  return res.json()
}

/**
 * Get morning dashboard structured data
 */
export async function getARADashboardData(workspacePath?: string): Promise<ARADashboard> {
  const params = workspacePath ? `?workspace_path=${encodeURIComponent(workspacePath)}` : ''
  const res = await fetch(`${API_BASE}/api/ara/dashboard${params}`)
  if (!res.ok) throw new Error('Failed to get dashboard data')
  return res.json()
}

// =============================================================================
// RUNTIME INFO
// =============================================================================

export interface RuntimeInfo {
  api_port: number
  web_port: number
  api_url: string
  web_url: string
  pid?: number
}

/**
 * Get runtime information (dynamic ports)
 */
export async function getRuntimeInfo(): Promise<RuntimeInfo> {
  const res = await fetch(`${API_BASE}/api/runtime`)
  if (!res.ok) throw new Error('Failed to get runtime info')
  return res.json()
}
