import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'

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
  const bottom = useRef(null)

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
              {message.pending && !message.answer && <span className="muted">Searching documents…</span>}
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
        <button type="submit" disabled={busy}>Ask</button>
      </form>
    </section>
  )
}
