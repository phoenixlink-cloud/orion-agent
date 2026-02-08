'use client'

import React from 'react'

const nodes = [
  { x: 20, y: 30 },
  { x: 80, y: 25 },
  { x: 15, y: 70 },
  { x: 85, y: 75 },
  { x: 35, y: 15 },
  { x: 65, y: 85 },
  { x: 10, y: 50 },
  { x: 90, y: 50 },
]

const lines = [
  [0, 2],
  [1, 3],
  [0, 4],
  [1, 4],
  [2, 5],
  [3, 5],
  [0, 6],
  [1, 7],
]

export default function Constellation() {
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 1,
        pointerEvents: 'none',
        opacity: 0.4,
      }}
    >
      <svg width="100%" height="100%">
        {lines.map(([a, b], i) => (
          <line
            key={i}
            x1={`${nodes[a].x}%`}
            y1={`${nodes[a].y}%`}
            x2={`${nodes[b].x}%`}
            y2={`${nodes[b].y}%`}
            stroke="var(--line)"
            strokeWidth="1"
          />
        ))}
        {nodes.map((node, i) => (
          <circle
            key={i}
            cx={`${node.x}%`}
            cy={`${node.y}%`}
            r="3"
            fill="var(--glow)"
            opacity="0.6"
          />
        ))}
      </svg>
    </div>
  )
}
