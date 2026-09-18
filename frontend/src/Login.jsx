import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { useI18n } from './i18n.jsx'
import LanguageDialog from './LanguageDialog.jsx'

const TURNSTILE_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

function loadTurnstile() {
  if (window.turnstile) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${TURNSTILE_SRC}"]`)
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', reject)
      return
    }
    const script = document.createElement('script')
    script.src = TURNSTILE_SRC
    script.async = true
    script.onload = () => resolve()
    script.onerror = reject
    document.head.appendChild(script)
  })
}

export default function Login({ onLogin, onLanguage, dialogOpen, onDialogClose }) {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [siteKey, setSiteKey] = useState('')
  const captcha = useRef(null)
  const widgetId = useRef(null)
  const token = useRef('')
  const { t, locale } = useI18n()

  useEffect(() => {
    api.config().then((config) => setSiteKey(config.turnstile_site_key || '')).catch(() => setSiteKey(''))
  }, [])

  useEffect(() => {
    if (!siteKey || !captcha.current || widgetId.current !== null) return
    loadTurnstile()
      .then(() => {
        widgetId.current = window.turnstile.render(captcha.current, {
          sitekey: siteKey,
          callback: (value) => { token.current = value },
          'expired-callback': () => { token.current = '' },
        })
      })
      .catch(() => setError(t('login.captcha')))
  }, [siteKey])

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
      try {
        await api.requestOtp(email, token.current)
        setCodeSent(true)
      } finally {
        token.current = ''
        if (widgetId.current !== null) window.turnstile.reset(widgetId.current)
      }
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
        <p className="muted">{t('login.tagline')}</p>
        <label>
          {t('login.email')}
          <input
            className="input"
            type="email"
            required
            value={email}
            disabled={codeSent}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        {codeSent && (
          <label>
            {t('login.code')}
            <input
              className="input"
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
        <div ref={captcha} hidden={!siteKey || codeSent} />
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy && <span className="dot-pulse" aria-hidden="true" />}
          {codeSent ? t('login.signin') : t('login.send')}
        </button>
        {codeSent && (
          <button type="button" className="link" disabled={busy} onClick={() => { setCodeSent(false); setCode('') }}>
            {t('login.another')}
          </button>
        )}
        <button type="button" className="link" onClick={onLanguage}>
          {t('nav.language')}: {locale.toUpperCase()}
        </button>
      </form>
      <LanguageDialog open={dialogOpen} onClose={onDialogClose} />
    </main>
  )
}
