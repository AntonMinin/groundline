import { useEffect, useState } from 'react'
import { api } from './api.js'
import { onEvent } from './events.js'
import { useI18n } from './i18n.jsx'

const ACTIVE = ['queued', 'processing']

export default function Documents({ hidden, stats, onChanged, onAccountDeleted, onReset }) {
  const [documents, setDocuments] = useState(null)
  const [jobs, setJobs] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(null)
  const [dragging, setDragging] = useState(false)
  const { t, n, locale } = useI18n()

  const maxDocuments = stats?.limits?.max_documents ?? 0
  const uploadMb = stats?.limits?.max_upload_mb ?? 0
  const list = documents ?? []
  const full = maxDocuments > 0 && list.length >= maxDocuments

  const load = () => api.documents().then(setDocuments).catch((err) => setError(err.message))

  useEffect(() => {
    load()
  }, [])

  useEffect(
    () =>
      onEvent((event) => {
        if (event.type === 'connected') {
          setJobs([])
          load()
          onChanged()
          return
        }
        if (event.type !== 'ingest') return
        setJobs((current) => [
          { id: event.job_id, filename: event.filename, status: event.status, error: event.error },
          ...current.filter((job) => job.id !== event.job_id),
        ])
        if (event.status === 'done') {
          load()
          onChanged()
        }
      }),
    [],
  )

  const send = async (files) => {
    if (busy || full || files.length === 0) return
    setBusy('upload')
    setError('')
    for (const file of files) {
      try {
        const job = await api.upload(file)
        setJobs((current) => [
          { id: job.id, filename: job.filename, status: job.status, error: null },
          ...current.filter((item) => item.id !== job.id),
        ])
      } catch (err) {
        setError(`${file.name}: ${err.message}`)
      }
    }
    setBusy(null)
  }

  const upload = async (event) => {
    const files = [...event.target.files]
    event.target.value = ''
    await send(files)
  }

  const drop = async (event) => {
    event.preventDefault()
    setDragging(false)
    await send([...event.dataTransfer.files])
  }

  const remove = async (id) => {
    if (busy) return
    setBusy(id)
    setError('')
    try {
      await api.deleteDocument(id)
      await load()
      onChanged()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(null)
    }
  }

  const resetDemo = async () => {
    if (!window.confirm(t('docs.confirmReset'))) return
    setBusy('reset')
    setError('')
    try {
      await api.deleteAllDocuments()
      await api.clearCache()
      await api.clearHistory()
      setJobs([])
      onReset()
    } catch (err) {
      setError(err.message)
    } finally {
      await load()
      onChanged()
      setBusy(null)
    }
  }

  const deleteAccount = async () => {
    if (!window.confirm(t('docs.confirmDelete'))) return
    setBusy('account')
    setError('')
    try {
      await api.deleteAccount()
      onAccountDeleted()
    } catch (err) {
      setError(err.message)
      setBusy(null)
    }
  }

  const chunks = list.reduce((sum, document) => sum + document.chunk_count, 0)
  const size = (bytes) => (bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`)
  const jobLabel = (job) => (job.status === 'error' ? t('job.error', { error: job.error ?? '' }) : t(`job.${job.status}`))
  const dot = <span className="dot-pulse" aria-hidden="true" />

  return (
    <main className="app-main docs" hidden={hidden}>
      <div className="docs-head">
        <h1>{t('docs.title')}</h1>
        {documents !== null && (
          <p className="muted">
            {t('docs.summary', { documents: n(list.length), limit: n(maxDocuments), chunks: n(chunks) })}
          </p>
        )}
      </div>

      <label
        className="dropzone"
        htmlFor="upload"
        data-dragging={dragging}
        data-busy={busy === 'upload'}
        data-full={full}
        aria-busy={busy === 'upload'}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
      >
        <strong>{t('docs.dropTitle')}</strong>
        {busy === 'upload' ? (
          <p className="working" role="status">{dot}{t('docs.uploading')}</p>
        ) : full ? (
          <p>{t('docs.full')}</p>
        ) : (
          <p>{t('docs.dropHint', { size: uploadMb })}</p>
        )}
        <input
          id="upload"
          type="file"
          accept=".pdf,.txt,.md"
          multiple={maxDocuments > 1}
          disabled={busy !== null || full}
          onChange={upload}
        />
      </label>

      {error && <p className="error" role="alert">{error}</p>}

      {jobs.length > 0 && (
        <section aria-labelledby="jobs-h">
          <h2 className="kicker" id="jobs-h">{t('docs.indexing')}</h2>
          <ul className="jobs">
            {jobs.map((job) => (
              <li className="job" key={job.id} data-status={job.status}>
                <span className="job-name">{job.filename}</span>
                <span className="job-status">{jobLabel(job)}</span>
                {ACTIVE.includes(job.status) && (
                  <span
                    className="job-progress"
                    aria-hidden="true"
                    data-indeterminate={job.status === 'processing'}
                  >
                    <i style={job.status === 'processing' ? undefined : { width: '8%' }} />
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="docs-h">
        <h2 className="kicker" id="docs-h">{t('docs.uploaded')}</h2>
        {documents === null ? null : list.length === 0 ? (
          <p className="muted">{t('docs.empty')}</p>
        ) : (
          <table className="doc-table">
            <thead>
              <tr>
                <th scope="col">{t('docs.file')}</th>
                <th scope="col">{t('docs.status')}</th>
                <th scope="col">{t('docs.chunks')}</th>
                <th scope="col">{t('docs.size')}</th>
                <th scope="col">{t('docs.uploadedAt')}</th>
                <th scope="col"><span className="visually-hidden">{t('docs.actions')}</span></th>
              </tr>
            </thead>
            <tbody>
              {list.map((doc) => (
                <tr key={doc.id}>
                  <td className="col-file" data-label={t('docs.file')}>{doc.filename}</td>
                  <td data-label={t('docs.status')}><span className="tag tag-accent">{t('docs.indexed')}</span></td>
                  <td className="num" data-label={t('docs.chunks')}>{n(doc.chunk_count)}</td>
                  <td className="num" data-label={t('docs.size')}>{size(doc.size_bytes)}</td>
                  <td className="num" data-label={t('docs.uploadedAt')}>
                    {new Date(doc.created_at).toLocaleString(locale, {
                      day: 'numeric',
                      month: 'short',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </td>
                  <td className="col-actions">
                    <button className="btn-quiet" type="button" onClick={() => remove(doc.id)} disabled={busy !== null}>
                      <span className="dot-pulse" aria-hidden="true" data-idle={busy !== doc.id} />
                      {t('docs.delete')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <div className="docs-danger">
        <button className="btn btn-secondary" type="button" onClick={resetDemo} disabled={busy !== null}>
          {busy === 'reset' && dot}
          {t('docs.reset')}
        </button>
        <button className="btn btn-secondary btn-danger" type="button" onClick={deleteAccount} disabled={busy !== null}>
          {busy === 'account' && dot}
          {t('docs.deleteAccount')}
        </button>
      </div>
    </main>
  )
}
