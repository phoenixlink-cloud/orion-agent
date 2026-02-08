import React from 'react'

type Variant = 'primary' | 'secondary'

interface ButtonProps {
  variant: Variant
  children: React.ReactNode
  onClick?: () => void
}

export default function Button({ variant, children, onClick }: ButtonProps) {
  const base: React.CSSProperties = {
    borderRadius: '999px',
    padding: '14px 22px',
    fontSize: 16,
    letterSpacing: 0.2,
    cursor: 'pointer',
    transition: 'all var(--slow) var(--ease)',
    border: '1px solid var(--line)',
    background: 'transparent',
    color: 'var(--text)',
  }

  const primary: React.CSSProperties = {
    background: 'var(--tile)',
    boxShadow: '0 0 30px rgba(159, 214, 255, 0.15)',
  }

  const secondary: React.CSSProperties = {
    background: 'var(--tile)',
  }

  return (
    <button
      style={{ ...base, ...(variant === 'primary' ? primary : secondary) }}
      onClick={onClick}
    >
      {children}
    </button>
  )
}
