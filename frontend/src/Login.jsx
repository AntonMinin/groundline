import { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { useI18n } from './i18n.jsx'
import LanguageDialog from './LanguageDialog.jsx'

const TURNSTILE_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
const SITE_URL = (import.meta.env.VITE_SITE_URL || 'https://groundline.antonmb.com').replace(/\/$/, '')

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
  const [accepted, setAccepted] = useState(false)
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
        await api.requestOtp(email, token.current, accepted)
        setCodeSent(true)
      } finally {
        token.current = ''
        if (widgetId.current !== null) window.turnstile.reset(widgetId.current)
      }
    })
  }

  const legalHref = (page) => `${SITE_URL}${locale === 'ru' ? '/ru' : ''}/${page}`

  const verifyCode = (event) => {
    event.preventDefault()
    run(async () => onLogin(await api.verifyOtp(email, code, accepted)))
  }

  return (
    <main className="center">
      <form className="card" onSubmit={codeSent ? verifyCode : requestCode}>
        <h1>Groundline</h1>
        <p className="muted">{t('login.tagline')}</p>
        <section className="why">
          <h2>{t('login.whyTitle')}</h2>
          <p className="why-lede">{t('login.whyLede')}</p>
          <p>{t('login.whyBody')}</p>
        </section>
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
        {!codeSent && (
          <label className="consent">
            <input type="checkbox" required checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />
            <span>
              {t('login.agree')}{' '}
              <a href={legalHref('terms')} target="_blank" rel="noopener">{t('login.terms')}</a>{' '}
              {t('login.and')}{' '}
              <a href={legalHref('privacy')} target="_blank" rel="noopener">{t('login.privacy')}</a>
            </span>
          </label>
        )}
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
