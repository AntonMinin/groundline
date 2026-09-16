import { useEffect, useState } from 'react'
import { onEvent } from './events.js'

const LLM = '#c0392b'
const CACHE = '#2563eb'
const IDLE = '#8a8a86'

const NODES = [
  { id: 'check_cache', label: 'check cache', llm: false },
  { id: 'rewrite_query', label: 'rewrite', llm: true },
  { id: 'retrieve', label: 'retrieve', llm: false },
  { id: 'rerank', label: 'rerank', llm: false },
  { id: 'check_sufficiency', label: 'sufficiency', llm: true },
  { id: 'generate_answer', label: 'generate', llm: true },
]

const BOX = { width: 132, height: 44, gap: 28, top: 18 }
const WIDTH = NODES.length * BOX.width + (NODES.length - 1) * BOX.gap
const HEIGHT = 108

function formatDuration(ms) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`
}

export default function PipelineDiagram() {
  const [run, setRun] = useState({ nodes: {}, cacheHit: false, similarity: null, started: false })

  useEffect(
    () =>
      onEvent((event) => {
        if (event.type === 'node_started') {
          setRun((current) => {
            const fresh = event.node === 'check_cache' ? { nodes: {}, cacheHit: false, similarity: null } : current
            return { ...fresh, started: true, nodes: { ...fresh.nodes, [event.node]: { state: 'running' } } }
          })
        }
        if (event.type === 'node_finished') {
          setRun((current) => ({
            ...current,
            cacheHit: current.cacheHit || Boolean(event.cache_hit),
            similarity: event.node === 'check_cache' ? event.similarity ?? null : current.similarity,
            nodes: {
              ...current.nodes,
              [event.node]: {
                state: 'done',
                durationMs: event.duration_ms,
                tokens: event.tokens,
                tokensSaved: event.tokens_saved,
                cacheHit: Boolean(event.cache_hit),
              },
            },
          }))
        }
      }),
    [],
  )

  const totals = Object.values(run.nodes).reduce(
    (sum, node) => ({
      ms: sum.ms + (node.durationMs ?? 0),
      tokens: sum.tokens + (node.tokens ?? 0),
      saved: sum.saved + (node.tokensSaved ?? 0),
    }),
    { ms: 0, tokens: 0, saved: 0 },
  )

  const colorOf = (node) => {
    const state = run.nodes[node.id]
    if (!state) return IDLE
    if (run.cacheHit) return CACHE
    return node.llm ? LLM : IDLE
  }

  return (
    <section className="card diagram">
      <h2>Pipeline</h2>
      <ul className="legend">
        <li><span className="key" style={{ background: LLM }} />LLM call</li>
        <li><span className="key" style={{ background: CACHE }} />cache hit</li>
      </ul>
      <p className="muted run-summary">
        {run.started
          ? `Last query: ${formatDuration(totals.ms)} · ${totals.tokens.toLocaleString()} tokens spent` +
            (run.cacheHit ? ` · ${totals.saved.toLocaleString()} saved by cache` : '') +
            (run.similarity !== null ? ` · nearest cached question ${run.similarity.toFixed(4)}` : '')
          : 'Ask a question to see per-step timings here.'}
      </p>
      <div className="diagram-wrap">
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width={WIDTH} height={HEIGHT} role="img" aria-label="Query pipeline">
          {NODES.map((node, index) => {
            const x = index * (BOX.width + BOX.gap)
            const state = run.nodes[node.id]
            const color = colorOf(node)
            const midY = BOX.top + BOX.height / 2
            return (
              <g key={node.id}>
                {index > 0 && (
                  <g>
                    <line
                      x1={x - BOX.gap}
                      x2={x}
                      y1={midY}
                      y2={midY}
                      stroke={state ? color : '#d8d8d4'}
                      strokeWidth="2"
                    />
                    {state?.state === 'running' && (
                      <circle r="4" cy={midY} fill={color}>
                        <animate attributeName="cx" from={x - BOX.gap} to={x} dur="0.9s" repeatCount="indefinite" />
                      </circle>
                    )}
                  </g>
                )}
                <rect
                  x={x}
                  y={BOX.top}
                  width={BOX.width}
                  height={BOX.height}
                  rx="8"
                  fill={state ? `${color}14` : '#fff'}
                  stroke={state ? color : '#d8d8d4'}
                  strokeWidth={state ? 2 : 1}
                />
                <text x={x + BOX.width / 2} y={BOX.top + 19} textAnchor="middle" className="node-label">
                  {node.label}
                </text>
                <text x={x + BOX.width / 2} y={BOX.top + 35} textAnchor="middle" className="node-metric">
                  {state?.state === 'running' && 'running…'}
                  {state?.state === 'done' &&
                    [
                      formatDuration(state.durationMs ?? 0),
                      state.tokens ? `${state.tokens.toLocaleString()} tok` : null,
                      state.tokensSaved ? `${state.tokensSaved.toLocaleString()} saved` : null,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                </text>
              </g>
            )
          })}
        </svg>
      </div>
    </section>
  )
}
