import { useEffect, useState } from 'react'
import { api } from './api.js'
import { onEvent } from './events.js'
import { useI18n } from './i18n.jsx'

const ACTIVE = ['queued', 'processing']

export default function Documents({ hidden, stats, onChanged, onAccountDeleted, onReset }) {
  const [documents, setDocuments] = useState([])
  const [jobs, setJobs] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const { t, n, locale } = useI18n()

  const load = () => api.documents().then(setDocuments).catch((err) => setError(err.message))

  useEffect(() => {
    load()
  }, [])

  useEffect(
    () =>
      onEvent((event) => {
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
    setBusy(true)
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
    setBusy(false)
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
    await api.deleteDocument(id).catch((err) => setError(err.message))
    load()
    onChanged()
  }

  const resetDemo = async () => {
    if (!window.confirm(t('docs.confirmReset'))) return
    setBusy(true)
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
      setBusy(false)
      load()
      onChanged()
    }
  }

  const deleteAccount = async () => {
    if (!window.confirm(t('docs.confirmDelete'))) return
    await api.deleteAccount()
    onAccountDeleted()
  }

  const chunks = documents.reduce((sum, document) => sum + document.chunk_count, 0)
  const size = (bytes) => (bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`)
  const jobLabel = (job) => (job.status === 'error' ? t('job.error', { error: job.error ?? '' }) : t(`job.${job.status}`))

  return (
    <main className="app-main docs" hidden={hidden}>
      <div className="docs-head">
        <h1>{t('docs.title')}</h1>
        <p className="muted">
          {t('docs.summary', {
            documents: n(documents.length),
            limit: n(stats?.limits?.max_documents ?? 0),
            chunks: n(chunks),
          })}
        </p>
      </div>

      <label
        className="dropzone"
        htmlFor="upload"
        data-dragging={dragging}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
      >
        <strong>{t('docs.dropTitle')}</strong>
        <p>{t('docs.dropHint', { size: stats?.limits?.max_upload_mb ?? 20 })}</p>
        <input id="upload" type="file" accept=".pdf,.txt,.md" multiple disabled={busy} onChange={upload} />
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
        {documents.length === 0 ? (
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
              {documents.map((doc) => (
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
                    <button className="btn-quiet" type="button" onClick={() => remove(doc.id)}>
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
        <button className="btn btn-secondary" type="button" onClick={resetDemo} disabled={busy}>
          {t('docs.reset')}
        </button>
        <button className="btn btn-secondary btn-danger" type="button" onClick={deleteAccount}>
          {t('docs.deleteAccount')}
        </button>
      </div>
    </main>
  )
}
