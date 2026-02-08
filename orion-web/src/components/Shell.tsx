import React from 'react'

interface ShellProps {
  children: React.ReactNode
}

export default function Shell({ children }: ShellProps) {
  return (
    <div
      style={{
        minHeight: '100vh',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {children}
    </div>
  )
}
