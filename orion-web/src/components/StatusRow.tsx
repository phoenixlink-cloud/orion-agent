import React from 'react'

interface StatusItemProps {
  label: string
  active?: boolean
}

function StatusItem({ label, active = true }: StatusItemProps) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        color: 'var(--muted)',
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: 999,
          background: active ? 'var(--glow)' : 'var(--muted)',
          boxShadow: active ? '0 0 10px rgba(159, 214, 255, 0.35)' : 'none',
        }}
      />
      <span style={{ fontSize: 14 }}>{label}</span>
    </div>
  )
}

export default function StatusRow() {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        gap: 28,
        flexWrap: 'wrap',
      }}
    >
      <StatusItem label="Orion online" />
      <StatusItem label="Aegis enforcing safeguards" />
      <StatusItem label="No intervention required" />
    </div>
  )
}
