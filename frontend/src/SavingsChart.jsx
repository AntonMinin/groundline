import { useEffect, useState } from 'react'
import { api } from './api.js'
import { onEvent } from './events.js'

const SPENT = '#c0392b'
const SAVED = '#2563eb'
const WIDTH = 640
const HEIGHT = 220
const PAD = { top: 16, right: 72, bottom: 28, left: 56 }

function niceCeiling(value) {
  if (value <= 0) return 100
  const magnitude = 10 ** Math.floor(Math.log10(value))
  return [1, 2, 5, 10].map((step) => step * magnitude).find((candidate) => candidate >= value) ?? magnitude * 10
}

function path(points, x, y, key) {
  return points.map((point, index) => `${index ? 'L' : 'M'}${x(index)},${y(point[key])}`).join(' ')
}

export default function SavingsChart() {
  const [points, setPoints] = useState([])
  const [hover, setHover] = useState(null)

  useEffect(() => {
    api
      .history(200)
      .then((rows) => {
        let spent = 0
        let saved = 0
        const restored = [...rows].reverse().map((row) => {
          spent += row.tokens_used
          saved += row.tokens_saved
          return { spent, saved, node: row.cache_hit ? 'cache hit' : 'query' }
        })
        setPoints((live) => {
          const offset = restored[restored.length - 1] ?? { spent: 0, saved: 0 }
          return [...restored, ...live.map((p) => ({ ...p, spent: p.spent + offset.spent, saved: p.saved + offset.saved }))]
        })
      })
      .catch(() => {})
  }, [])

  useEffect(
    () =>
      onEvent((event) => {
        if (event.type !== 'node_finished') return
        const tokens = event.tokens || 0
        const saved = event.tokens_saved || 0
        if (!tokens && !saved) return
        setPoints((current) => {
          const last = current[current.length - 1] ?? { spent: 0, saved: 0 }
          return [...current, { spent: last.spent + tokens, saved: last.saved + saved, node: event.node }]
        })
      }),
    [],
  )

  if (points.length === 0) {
    return (
      <section className="card chart">
        <h2>Cumulative token cost</h2>
        <p className="muted">Ask a question to see tokens spent on the LLM against tokens saved by the cache.</p>
      </section>
    )
  }

  const totals = points[points.length - 1]
  const max = niceCeiling(Math.max(totals.spent, totals.saved, 1))
  const innerWidth = WIDTH - PAD.left - PAD.right
  const innerHeight = HEIGHT - PAD.top - PAD.bottom
  const x = (index) => (points.length === 1 ? PAD.left : PAD.left + (index / (points.length - 1)) * innerWidth)
  const y = (value) => PAD.top + innerHeight - (value / max) * innerHeight
  const ticks = [0, max / 2, max]
  const active = hover === null ? points.length - 1 : hover

  const pick = (event) => {
    const box = event.currentTarget.getBoundingClientRect()
    const ratio = (event.clientX - box.left) / box.width
    const position = ratio * WIDTH
    const step = points.length === 1 ? 1 : innerWidth / (points.length - 1)
    setHover(Math.max(0, Math.min(points.length - 1, Math.round((position - PAD.left) / step))))
  }

  return (
    <section className="card chart">
      <h2>Cumulative token cost</h2>
      <ul className="legend">
        <li><span className="key" style={{ background: SPENT }} />Spent on LLM</li>
        <li><span className="key" style={{ background: SAVED }} />Saved by cache</li>
      </ul>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%" role="img" aria-label="Cumulative tokens spent and saved">
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} stroke="#e5e5e2" strokeWidth="1" />
            <text x={PAD.left - 8} y={y(tick) + 4} textAnchor="end" className="tick">{Math.round(tick).toLocaleString()}</text>
          </g>
        ))}
        <path d={path(points, x, y, 'spent')} fill="none" stroke={SPENT} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <path d={path(points, x, y, 'saved')} fill="none" stroke={SAVED} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {hover !== null && (
          <line x1={x(active)} x2={x(active)} y1={PAD.top} y2={PAD.top + innerHeight} stroke="#b8b8b4" strokeWidth="1" />
        )}
        {[['spent', SPENT], ['saved', SAVED]].map(([key, color]) => (
          <circle key={key} cx={x(active)} cy={y(points[active][key])} r="4" fill={color} stroke="#fff" strokeWidth="2" />
        ))}
        <text x={x(points.length - 1) + 10} y={y(totals.spent) + 4} className="end-label">{totals.spent.toLocaleString()}</text>
        <text x={x(points.length - 1) + 10} y={y(totals.saved) + 4} className="end-label">{totals.saved.toLocaleString()}</text>
        {hover !== null && (
          <text x={PAD.left} y={HEIGHT - 8} className="tick">
            {points[active].node}: spent {points[active].spent.toLocaleString()}, saved {points[active].saved.toLocaleString()}
          </text>
        )}
        <rect
          x={PAD.left}
          y={PAD.top}
          width={innerWidth}
          height={innerHeight}
          fill="transparent"
          onMouseMove={pick}
          onMouseLeave={() => setHover(null)}
        />
      </svg>
      <details>
        <summary>Table view</summary>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Step</th><th>Node</th><th>Spent</th><th>Saved</th></tr></thead>
            <tbody>
              {points.slice(-20).map((point, index) => (
                <tr key={index}>
                  <td>{points.length - Math.min(points.length, 20) + index + 1}</td>
                  <td>{point.node}</td>
                  <td>{point.spent.toLocaleString()}</td>
                  <td>{point.saved.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  )
}
