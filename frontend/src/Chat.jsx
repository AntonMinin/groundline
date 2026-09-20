import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { onEvent } from './events.js'
import { useI18n } from './i18n.jsx'

function Sources({ sources }) {
  const { t } = useI18n()
  if (!sources?.length) return null
  return (
    <details className="sources">
      <summary>{t('chat.sources', { count: sources.length })}</summary>
      <ol>
        {sources.map((source, index) => (
          <li className="source" key={index}>
            <span className="source-file">{source.filename}</span>
            <span className="source-loc">
              {t('chat.chunk', { index: source.chunk_index })}
              {source.page ? ` · ${t('chat.page', { page: source.page })}` : ''}
            </span>
            {source.content && (
              <p className="source-quote">
                «{source.content.slice(0, 300)}{source.content.length > 300 ? '…' : ''}»
              </p>
            )}
          </li>
        ))}
      </ol>
    </details>
  )
}

function Meta({ message }) {
  const { t, n } = useI18n()
  if (message.pending) return null
  return (
    <p className="msg-meta">
      <span className={message.cacheHit ? 'tag tag-accent' : 'tag'}>
        {message.cacheHit
          ? t('chat.cacheHit', { similarity: (message.similarity ?? 0).toFixed(4) })
          : t('chat.cacheMiss')}
      </span>
      {message.durationMs !== undefined && <span className="num">{message.durationMs >= 1000 ? `${(message.durationMs / 1000).toFixed(2)} s` : `${message.durationMs} ms`}</span>}
      <span className="num">
        {message.cacheHit
          ? t('chat.saved', { tokens: n(message.tokensSaved ?? 0) })
          : t('chat.tokens', { tokens: n(message.tokensUsed ?? 0) })}
      </span>
    </p>
  )
}

function toMessage(row) {
  return {
    question: row.question,
    answer: row.answer,
    sources: row.sources,
    cacheHit: row.cache_hit,
    tokensUsed: row.tokens_used,
    tokensSaved: row.tokens_saved,
    similarity: row.node_metrics?.find((metric) => metric.node === 'check_cache')?.similarity,
    durationMs: row.node_metrics?.reduce((sum, metric) => sum + (metric.duration_ms ?? 0), 0),
  }
}

export default function Chat({ initial, onAnswered }) {
  const [messages, setMessages] = useState(() => [...(initial ?? [])].reverse().map(toMessage))
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [step, setStep] = useState(null)
  const started = useRef(0)
  const bottom = useRef(null)
  const { t } = useI18n()

  useEffect(
    () =>
      onEvent((event) => {
        if (event.type === 'node_started') setStep(event.node)
        if (event.type === 'node_finished' && event.node === 'record') setStep(null)
      }),
    [],
  )

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const update = (patch) =>
    setMessages((current) => [
      ...current.slice(0, -1),
      { ...current[current.length - 1], ...patch(current[current.length - 1]) },
    ])

  const ask = async (event) => {
    event.preventDefault()
    const text = question.trim()
    if (!text) return
    setQuestion('')
    setBusy(true)
    started.current = performance.now()
    setMessages((current) => [...current, { question: text, answer: '', sources: [], pending: true }])
    try {
      for await (const evt of api.query(text)) {
        if (evt.type === 'token') update((m) => ({ answer: m.answer + evt.text }))
        if (evt.type === 'done')
          update(() => ({
            sources: evt.sources,
            cacheHit: evt.cache_hit,
            similarity: evt.cache_similarity,
            tokensUsed: evt.tokens_used,
            tokensSaved: evt.tokens_saved,
            durationMs: Math.round(performance.now() - started.current),
            pending: false,
          }))
        if (evt.type === 'error') update(() => ({ error: `${evt.status}: ${evt.detail}`, pending: false }))
      }
    } catch (err) {
      update(() => ({ error: err.status ? `${err.status}: ${err.message}` : err.message, pending: false }))
    } finally {
      setBusy(false)
      onAnswered()
    }
  }

  return (
    <div className="thread-col">
      <ol className="thread">
        {messages.length === 0 && <p className="muted">{t('chat.empty')}</p>}
        {messages.map((message, index) => (
          <li className="msg" key={index}>
            <p className="msg-question">{message.question}</p>
            <div className="msg-answer">
              {message.pending && (
                <p className="msg-working" role="status">
                  <span className="dot-pulse" aria-hidden="true" />
                  {step ? t(`step.${step}`) : '…'}
                </p>
              )}
              {message.answer && <p>{message.answer}</p>}
              {message.error && <p className="error" role="alert">{message.error}</p>}
              <Meta message={message} />
              <Sources sources={message.sources} />
            </div>
          </li>
        ))}
        <li ref={bottom} />
      </ol>

      <form className="composer" onSubmit={ask}>
        <label className="visually-hidden" htmlFor="ask">{t('chat.placeholder')}</label>
        <input
          className="input"
          id="ask"
          type="text"
          maxLength={2000}
          autoComplete="off"
          placeholder={t('chat.placeholder')}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy && <span className="dot-pulse" aria-hidden="true" />}
          {busy ? t('chat.asking') : t('chat.ask')}
        </button>
      </form>
    </div>
  )
}
