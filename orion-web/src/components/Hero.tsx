import React from 'react'
import Link from 'next/link'
import BrandBlock from './BrandBlock'
import StatusRow from './StatusRow'
import Button from './Button'
import OrionCore from '@/visuals/OrionCore'

export default function Hero() {
  return (
    <section style={{ position: 'relative', minHeight: '100vh' }}>

      <div
        style={{
          maxWidth: 1120,
          margin: '0 auto',
          padding: '56px 20px',
          position: 'relative',
          zIndex: 2,
        }}
      >
        <BrandBlock />

        <div
          style={{
            marginTop: 72,
            display: 'grid',
            placeItems: 'center',
          }}
        >
          <OrionCore />
        </div>

        <div style={{ marginTop: 56, textAlign: 'center' }}>
          <div
            style={{
              fontSize: 28,
              color: 'var(--text)',
              opacity: 0.92,
            }}
          >
            I'm here to help you create — safely.
          </div>

          <div
            style={{
              marginTop: 18,
              display: 'flex',
              gap: 14,
              justifyContent: 'center',
              flexWrap: 'wrap',
            }}
          >
            <Link href="/chat">
              <Button variant="primary">Ask Orion</Button>
            </Link>
            <Link href="/ara">
              <Button variant="secondary">Autonomous Roles →</Button>
            </Link>
            <Link href="/aegis">
              <Button variant="secondary">AEGIS Governance →</Button>
            </Link>
            <Link href="/network">
              <Button variant="secondary">Network →</Button>
            </Link>
          </div>
        </div>

        <div style={{ marginTop: 56 }}>
          <StatusRow />
        </div>
      </div>
    </section>
  )
}
