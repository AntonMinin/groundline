import { useState } from 'react'
import { api } from './api.js'
import { useI18n } from './i18n.jsx'

const SITE_URL = (import.meta.env.VITE_SITE_URL || 'https://groundline.antonmb.com').replace(/\/$/, '')

export default function AcceptTerms({ email, onAccepted, onLogout }) {
  const [accepted, setAccepted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const { t, locale } = useI18n()

  const href = (page) => `${SITE_URL}${locale === 'ru' ? '/ru' : ''}/${page}`

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      onAccepted(await api.acceptTerms())
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <main className="center">
      <form className="card" onSubmit={submit}>
        <h1>{t('terms.title')}</h1>
        <p className="muted">{t('terms.lede')}</p>
        <p className="muted">{email}</p>
        <label className="consent">
          <input type="checkbox" required checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />
          <span>
            {t('login.agree')}{' '}
            <a href={href('terms')} target="_blank" rel="noopener">{t('login.terms')}</a>{' '}
            {t('login.and')}{' '}
            <a href={href('privacy')} target="_blank" rel="noopener">{t('login.privacy')}</a>
          </span>
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button className="btn btn-primary" type="submit" disabled={busy}>
          {busy && <span className="dot-pulse" aria-hidden="true" />}
          {t('terms.accept')}
        </button>
        <button type="button" className="link" disabled={busy} onClick={onLogout}>
          {t('nav.logout')}
        </button>
      </form>
    </main>
  )
}
