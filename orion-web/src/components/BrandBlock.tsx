import React from 'react'

export default function BrandBlock() {
  return (
    <div>
      <div
        style={{
          fontSize: 'var(--h1-size)',
          fontWeight: 'var(--h1-weight)',
          letterSpacing: '0.12em',
          color: 'var(--text)',
        }}
      >
        ORION
      </div>
      <div
        style={{
          marginTop: 8,
          fontSize: 'var(--h2-size)',
          fontWeight: 'var(--h2-weight)',
          letterSpacing: '0.08em',
          color: 'var(--muted)',
        }}
      >
        Governed AI Assistant
      </div>
    </div>
  )
}
