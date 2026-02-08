'use client'

import React from 'react'

export default function OrionCore() {
  return (
    <div
      style={{
        position: 'relative',
        width: 300,
        height: 300,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {/* Outermost glow */}
      <div
        style={{
          position: 'absolute',
          width: 300,
          height: 300,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(159,214,255,0.08) 0%, transparent 70%)',
          animation: 'pulse 9s ease-in-out infinite',
        }}
      />
      {/* Large outer glow */}
      <div
        style={{
          position: 'absolute',
          width: 220,
          height: 220,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(159,214,255,0.12) 0%, transparent 70%)',
          animation: 'pulse 9s ease-in-out infinite',
          animationDelay: '-2s',
        }}
      />
      {/* Medium glow ring */}
      <div
        style={{
          position: 'absolute',
          width: 150,
          height: 150,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(159,214,255,0.2) 0%, transparent 70%)',
          animation: 'pulse 9s ease-in-out infinite',
          animationDelay: '-4s',
        }}
      />
      {/* Inner glow */}
      <div
        style={{
          position: 'absolute',
          width: 100,
          height: 100,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(180,220,255,0.35) 0%, transparent 70%)',
          animation: 'pulse 9s ease-in-out infinite',
          animationDelay: '-6s',
        }}
      />
      {/* Bright core */}
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: '50%',
          background: 'radial-gradient(circle, #ffffff 0%, rgba(200,230,255,0.9) 30%, rgba(159,214,255,0.6) 60%, transparent 100%)',
          boxShadow: `
            0 0 20px rgba(255,255,255,0.8),
            0 0 40px rgba(200,230,255,0.6),
            0 0 80px rgba(159,214,255,0.5),
            0 0 120px rgba(159,214,255,0.3),
            0 0 200px rgba(159,214,255,0.2)
          `,
        }}
      />
      {/* Cross flare effect */}
      <div
        style={{
          position: 'absolute',
          width: 4,
          height: 120,
          background: 'linear-gradient(to bottom, transparent, rgba(255,255,255,0.3), transparent)',
          opacity: 0.6,
        }}
      />
      <div
        style={{
          position: 'absolute',
          width: 120,
          height: 4,
          background: 'linear-gradient(to right, transparent, rgba(255,255,255,0.3), transparent)',
          opacity: 0.6,
        }}
      />
      <style jsx>{`
        @keyframes pulse {
          0%, 100% {
            transform: scale(1);
            opacity: 0.7;
          }
          50% {
            transform: scale(1.15);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  )
}
