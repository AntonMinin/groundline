import { useState } from 'react'
import { api } from './api.js'

export default function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const run = async (action) => {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const requestCode = (event) => {
    event.preventDefault()
    run(async () => {
      await api.requestOtp(email)
      setCodeSent(true)
    })
  }

  const verifyCode = (event) => {
    event.preventDefault()
    run(async () => onLogin(await api.verifyOtp(email, code)))
  }

  return (
    <main className="center">
      <form className="card" onSubmit={codeSent ? verifyCode : requestCode}>
        <h1>Groundline</h1>
        <p className="muted">Answers grounded in your documents.</p>
        <label>
          Email
          <input type="email" required value={email} disabled={codeSent} onChange={(e) => setEmail(e.target.value)} />
        </label>
        {codeSent && (
          <label>
            6-digit code from email
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="\d{6}"
              maxLength={6}
              required
              autoFocus
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
        )}
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" disabled={busy}>{codeSent ? 'Sign in' : 'Send code'}</button>
        {codeSent && (
          <button type="button" className="link" onClick={() => { setCodeSent(false); setCode('') }}>
            Use another email
          </button>
        )}
      </form>
    </main>
  )
}
