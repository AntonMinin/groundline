import { useEffect, useState } from 'react'
import { api } from './api.js'
import { onEvent } from './events.js'

export default function Documents({ onChanged, onAccountDeleted, onReset }) {
  const [documents, setDocuments] = useState([])
  const [jobs, setJobs] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

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

  const upload = async (event) => {
    const files = [...event.target.files]
    event.target.value = ''
    setBusy(true)
    setError('')
    for (const file of files) {
      try {
        await api.upload(file)
      } catch (err) {
        setError(`${file.name}: ${err.message}`)
      }
    }
    setBusy(false)
  }

  const remove = async (id) => {
    await api.deleteDocument(id).catch((err) => setError(err.message))
    load()
    onChanged()
  }

  const resetDemo = async () => {
    if (!window.confirm('Delete all documents, the answer cache and the query history? Your account stays.')) return
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
    if (!window.confirm('Delete your account, all documents and history? This cannot be undone.')) return
    await api.deleteAccount()
    onAccountDeleted()
  }

  return (
    <section>
      <label className="upload">
        {busy ? 'Uploading and indexing…' : 'Upload PDF, TXT or MD'}
        <input type="file" accept=".pdf,.txt,.md" multiple disabled={busy} onChange={upload} />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      {jobs.filter((job) => job.status !== 'done').length > 0 && (
        <ul className="jobs">
          {jobs
            .filter((job) => job.status !== 'done')
            .map((job) => (
              <li key={job.id}>
                <strong>{job.filename}</strong>
                <span className={job.status === 'error' ? 'error' : 'muted'}> {job.status}{job.error ? `: ${job.error}` : ''}</span>
              </li>
            ))}
        </ul>
      )}
      {documents.length === 0 ? (
        <p className="muted">No documents yet.</p>
      ) : (
        <div className="table-wrap">
        <table>
          <thead>
            <tr><th>File</th><th>Chunks</th><th>Size</th><th>Uploaded</th><th /></tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr key={doc.id}>
                <td>{doc.filename}</td>
                <td>{doc.chunk_count}</td>
                <td>{(doc.size_bytes / 1024).toFixed(0)} KB</td>
                <td>{new Date(doc.created_at).toLocaleString()}</td>
                <td><button onClick={() => remove(doc.id)}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
      <hr />
      <div className="actions">
        <button onClick={resetDemo} disabled={busy}>Reset demo</button>
        <button className="danger" onClick={deleteAccount}>Delete account</button>
      </div>
    </section>
  )
}
