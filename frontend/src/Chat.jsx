import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { onEvent } from './events.js'

const STEP_LABELS = {
  check_cache: 'checking the answer cache…',
  rewrite_query: 'rewriting the question…',
  retrieve: 'searching documents…',
  rerank: 'ranking the best fragments…',
  check_sufficiency: 'checking whether the context is enough…',
  generate_answer: 'writing the answer…',
  record: 'saving…',
}

function Sources({ sources }) {
  if (!sources?.length) return null
  return (
    <details className="sources">
      <summary>Sources ({sources.length})</summary>
      <ol>
        {sources.map((source, index) => (
          <li key={index}>
            <strong>{source.filename}</strong>
            <span className="muted"> · chunk {source.chunk_index}{source.page ? ` · page ${source.page}` : ''}</span>
            {source.content && <p>{source.content.slice(0, 300)}{source.content.length > 300 ? '…' : ''}</p>}
          </li>
        ))}
      </ol>
    </details>
  )
}

export default function Chat({ onAnswered }) {
  const [messages, setMessages] = useState([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [step, setStep] = useState(null)
  const bottom = useRef(null)

  useEffect(
    () =>
      onEvent((event) => {
        if (event.type === 'node_started') setStep(event.node)
        if (event.type === 'node_finished' && event.node === 'record') setStep(null)
      }),
    [],
  )

  useEffect(() => {
    api
      .history()
      .then((rows) =>
        setMessages(rows.reverse().map((row) => ({ question: row.question, answer: row.answer, sources: row.sources, cacheHit: row.cache_hit }))),
      )
      .catch(() => {})
  }, [])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const update = (patch) =>
    setMessages((current) => [...current.slice(0, -1), { ...current[current.length - 1], ...patch(current[current.length - 1]) }])

  const ask = async (event) => {
    event.preventDefault()
    const text = question.trim()
    if (!text) return
    setQuestion('')
    setBusy(true)
    setMessages((current) => [...current, { question: text, answer: '', sources: [], pending: true }])
    try {
      for await (const evt of api.query(text)) {
        if (evt.type === 'token') update((m) => ({ answer: m.answer + evt.text }))
        if (evt.type === 'done') update(() => ({ sources: evt.sources, cacheHit: evt.cache_hit, tokensSaved: evt.tokens_saved, pending: false }))
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
    <section className="chat">
      <div className="messages">
        {messages.length === 0 && <p className="muted">Ask a question about your documents.</p>}
        {messages.map((message, index) => (
          <article key={index}>
            <p className="question">{message.question}</p>
            <div className="answer">
              {message.pending && (
                <p className="working">
                  <span className="spinner" aria-hidden="true" />
                  <span className="muted">{STEP_LABELS[step] ?? 'working…'}</span>
                </p>
              )}
              {message.answer}
              {message.cacheHit && <span className="badge">cache hit{message.tokensSaved ? ` · ${message.tokensSaved} tokens saved` : ''}</span>}
            </div>
            {message.error && <p className="error" role="alert">{message.error}</p>}
            <Sources sources={message.sources} />
          </article>
        ))}
        <div ref={bottom} />
      </div>
      <form className="ask" onSubmit={ask}>
        <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about your documents…" maxLength={2000} />
        <button type="submit" disabled={busy}>{busy ? 'Asking…' : 'Ask'}</button>
      </form>
    </section>
  )
}
