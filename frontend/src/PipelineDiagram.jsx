import { useEffect, useRef, useState } from 'react'
import { onEvent } from './events.js'

const LLM = '#c0392b'
const CACHE = '#2563eb'
const IDLE = '#8a8a86'
const FADE_MS = 2000

const NODES = [
  { id: 'check_cache', label: 'check cache', llm: false },
  { id: 'rewrite_query', label: 'rewrite', llm: true },
  { id: 'retrieve', label: 'retrieve', llm: false },
  { id: 'rerank', label: 'rerank', llm: false },
  { id: 'check_sufficiency', label: 'sufficiency', llm: true },
  { id: 'generate_answer', label: 'generate', llm: true },
]

const BOX = { width: 132, height: 48, gap: 28 }
const WIDTH = NODES.length * BOX.width + (NODES.length - 1) * BOX.gap
const HEIGHT = 96

export default function PipelineDiagram() {
  const [active, setActive] = useState({})
  const timers = useRef({})

  useEffect(() => {
    const stop = onEvent((event) => {
      if (event.type !== 'node_started' && event.type !== 'node_finished') return
      const index = NODES.findIndex((node) => node.id === event.node)
      if (index === -1) return
      clearTimeout(timers.current[event.node])
      if (event.type === 'node_started') {
        setActive((current) => ({ ...current, [event.node]: { state: 'running', cacheHit: false } }))
      } else {
        setActive((current) => ({ ...current, [event.node]: { state: 'done', cacheHit: Boolean(event.cache_hit) } }))
        timers.current[event.node] = setTimeout(
          () => setActive((current) => ({ ...current, [event.node]: null })),
          FADE_MS,
        )
      }
    })
    const pending = timers.current
    return () => {
      stop()
      Object.values(pending).forEach(clearTimeout)
    }
  }, [])

  const colorOf = (node) => {
    const state = active[node.id]
    if (!state) return IDLE
    if (state.cacheHit) return CACHE
    return node.llm ? LLM : IDLE
  }

  return (
    <section className="card diagram">
      <h2>Pipeline</h2>
      <ul className="legend">
        <li><span className="key" style={{ background: LLM }} />LLM call</li>
        <li><span className="key" style={{ background: CACHE }} />cache hit</li>
      </ul>
      <div className="diagram-wrap">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width={WIDTH} height={HEIGHT} role="img" aria-label="Query pipeline">
          {NODES.map((node, index) => {
            const x = index * (BOX.width + BOX.gap)
            const state = active[node.id]
            const color = colorOf(node)
            return (
              <g key={node.id}>
                {index > 0 && (
                  <g>
                    <line
                      x1={x - BOX.gap}
                      x2={x}
                      y1={BOX.height / 2 + 16}
                      y2={BOX.height / 2 + 16}
                      stroke={state ? color : '#d8d8d4'}
                      strokeWidth="2"
                    />
                    {state?.state === 'running' && (
                      <circle r="4" fill={color}>
                        <animate attributeName="cx" from={x - BOX.gap} to={x} dur="0.9s" repeatCount="indefinite" />
                        <animate attributeName="cy" from={BOX.height / 2 + 16} to={BOX.height / 2 + 16} dur="0.9s" repeatCount="indefinite" />
                      </circle>
                    )}
                  </g>
                )}
                <rect
                  x={x}
                  y={16}
                  width={BOX.width}
                  height={BOX.height}
                  rx="8"
                  fill={state ? `${color}14` : '#fff'}
                  stroke={state ? color : '#d8d8d4'}
                  strokeWidth={state ? 2 : 1}
                  className="node-box"
                />
                <text x={x + BOX.width / 2} y={BOX.height / 2 + 21} textAnchor="middle" className="node-label">
                  {node.label}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </section>
  )
}
