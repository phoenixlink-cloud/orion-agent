'use client'

import React from 'react'

export default function AegisGridBackdrop() {
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 0,
        overflow: 'hidden',
        pointerEvents: 'none',
      }}
    >
      <svg
        width="100%"
        height="100%"
        style={{ position: 'absolute', inset: 0 }}
      >
        <defs>
          <pattern
            id="grid"
            width="60"
            height="60"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 60 0 L 0 0 0 60"
              fill="none"
              stroke="var(--grid)"
              strokeWidth="1"
            />
          </pattern>
          <radialGradient id="gridFade" cx="50%" cy="45%" r="60%">
            <stop offset="0%" stopColor="white" stopOpacity="0.4" />
            <stop offset="100%" stopColor="white" stopOpacity="0" />
          </radialGradient>
          <mask id="gridMask">
            <rect width="100%" height="100%" fill="url(#gridFade)" />
          </mask>
        </defs>
        <rect
          width="100%"
          height="100%"
          fill="url(#grid)"
          mask="url(#gridMask)"
        />
        <ellipse
          cx="50%"
          cy="45%"
          rx="400"
          ry="300"
          fill="none"
          stroke="var(--line)"
          strokeWidth="1"
          opacity="0.3"
        />
        <ellipse
          cx="50%"
          cy="45%"
          rx="600"
          ry="450"
          fill="none"
          stroke="var(--line)"
          strokeWidth="1"
          opacity="0.15"
        />
      </svg>
    </div>
  )
}
