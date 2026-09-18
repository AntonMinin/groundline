import { useEffect, useState } from 'react'
import { api } from './api.js'
import { onEvent } from './events.js'
import { useI18n } from './i18n.jsx'
import { formatDuration } from './telemetry.js'

const NODES = ['check_cache', 'rewrite_query', 'retrieve', 'rerank', 'check_sufficiency', 'generate_answer', 'record']

function fromMetrics(metrics) {
  const nodes = {}
  metrics.forEach((metric) => {
    nodes[metric.node] = {
      state: 'done',
      durationMs: metric.duration_ms,
      tokens: metric.tokens,
      tokensSaved: metric.tokens_saved,
      similarity: metric.similarity,
      cacheHit: Boolean(metric.cache_hit),
    }
  })
  return nodes
}

export default function PipelineDiagram() {
  const [run, setRun] = useState({ nodes: {}, cacheHit: false, threshold: null, started: false, restored: false })
  const { t, n } = useI18n()

  useEffect(() => {
    api
      .history(1)
      .then(([last]) => {
        if (!last?.node_metrics?.length) return
        setRun((current) =>
          current.started
            ? current
            : {
                nodes: fromMetrics(last.node_metrics),
                cacheHit: Boolean(last.cache_hit),
                threshold: null,
                started: true,
                restored: true,
              },
        )
      })
      .catch(() => {})
  }, [])

  useEffect(
    () =>
      onEvent((event) => {
        if (event.type === 'node_started') {
          setRun((current) => {
            const base = event.node === 'check_cache' ? { nodes: {}, cacheHit: false, threshold: current.threshold } : current
            return {
              ...base,
              started: true,
              restored: false,
              nodes: { ...base.nodes, [event.node]: { state: 'active' } },
            }
          })
        }
        if (event.type === 'node_finished') {
          setRun((current) => ({
            ...current,
            cacheHit: current.cacheHit || Boolean(event.cache_hit),
            nodes: {
              ...current.nodes,
              [event.node]: {
                state: 'done',
                durationMs: event.duration_ms,
                tokens: event.tokens,
                tokensSaved: event.tokens_saved,
                similarity: event.similarity,
                cacheHit: Boolean(event.cache_hit),
              },
            },
          }))
        }
        if (event.type === 'done' && event.cache_threshold) {
          setRun((current) => ({ ...current, threshold: event.cache_threshold }))
        }
      }),
    [],
  )

  const done = NODES.filter((node) => run.nodes[node]?.state === 'done')
  const totals = done.reduce(
    (sum, node) => ({
      ms: sum.ms + (run.nodes[node].durationMs ?? 0),
      tokens: sum.tokens + (run.nodes[node].tokens ?? 0),
    }),
    { ms: 0, tokens: 0 },
  )

  const trackState = (node) => {
    const state = run.nodes[node]?.state
    if (!state) return run.started ? 'pending' : 'idle'
    if (state === 'active') return 'active'
    return run.cacheHit ? 'cached' : 'done'
  }

  const noteFor = (node) => {
    if (node !== 'check_cache') return null
    const similarity = run.nodes.check_cache?.similarity
    if (similarity === null || similarity === undefined) return null
    const key = run.cacheHit ? 'pipeline.cacheHitNote' : 'pipeline.cacheNote'
    return t(key, { similarity: similarity.toFixed(4), threshold: run.threshold ? run.threshold.toFixed(2) : '0.95' })
  }

  return (
    <details className="pipeline" open>
      <summary>
        <span className="pipeline-summary-row">
          <span className="kicker">{t('pipeline.title')}</span>
          <span className="pipeline-toggle">{t('pipeline.steps')}</span>
        </span>
        <span className="pipeline-facts">
          {run.started ? (
            <>
              <b>{t('pipeline.stepsOf', { done: done.length, total: NODES.length })}</b>
              <b>{formatDuration(totals.ms)}</b>
              <b>{n(totals.tokens)}</b> tok
              {run.restored && <span className="muted"> · {t('pipeline.previous')}</span>}
            </>
          ) : (
            <span className="muted">{t('pipeline.idle')}</span>
          )}
        </span>
        <span className="pipeline-track" aria-hidden="true">
          {NODES.map((node) => (
            <span key={node} data-state={trackState(node)} />
          ))}
        </span>
      </summary>
      <ol className="pipeline-steps">
        {NODES.map((node) => {
          const state = run.nodes[node]
          const note = noteFor(node)
          return (
            <li className="step" key={node} data-state={state?.state ?? 'pending'}>
              <span className="step-name">{node}</span>
              <span className="step-time">
                {state?.state === 'active' ? '…' : formatDuration(state?.durationMs)}
              </span>
              <span className="step-tokens">{state?.tokens ? n(state.tokens) : '—'}</span>
              {note && <span className="step-note">{note}</span>}
            </li>
          )
        })}
      </ol>
    </details>
  )
}
