import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { connectEvents, disconnectEvents } from './events.js'
import { useI18n } from './i18n.jsx'
import Login from './Login.jsx'
import Documents from './Documents.jsx'
import Chat from './Chat.jsx'
import SavingsChart from './SavingsChart.jsx'
import PipelineDiagram from './PipelineDiagram.jsx'
import ServiceLimitsBar from './ServiceLimitsBar.jsx'
import LanguageDialog from './LanguageDialog.jsx'
import AcceptTerms from './AcceptTerms.jsx'
import { BOOT_STEPS, boot, forgetSession, rememberSession } from './session.js'

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 64 64" aria-hidden="true">
      <path className="sheet" d="M14 5h24l12 12v42H14z" />
      <line className="line" x1="23" y1="28" x2="41" y2="28" />
      <line className="line" x1="23" y1="38" x2="41" y2="38" />
      <line className="line line-accent" x1="23" y1="48" x2="37" y2="48" />
    </svg>
  )
}

function Splash({ loaded }) {
  const { t } = useI18n()
  return (
    <main className="center">
      <div className="splash" role="status">
        <p className="brand">
          <BrandMark />
          Groundline
          <span className="dot-pulse" aria-hidden="true" />
        </p>
        <ul className="boot">
          {BOOT_STEPS.map((key) => (
            <li key={key} data-done={loaded[key] === true}>
              <span>{t(`boot.${key}`)}</span>
              <span className="boot-mark" aria-hidden="true" />
              <span className="visually-hidden">{loaded[key] ? t('boot.done') : t('boot.loading')}</span>
            </li>
          ))}
        </ul>
      </div>
    </main>
  )
}

export default function App() {
  const [user, setUser] = useState(undefined)
  const [boot, setBoot] = useState(null)
  const [loaded, setLoaded] = useState({})
  const [bootKey, setBootKey] = useState(0)
  const [tab, setTab] = useState('chat')
  const [stats, setStats] = useState(null)
  const [resetKey, setResetKey] = useState(0)
  const [languageOpen, setLanguageOpen] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [serviceLimits, setServiceLimits] = useState(null)
  const { t, locale } = useI18n()

  const refreshStats = useCallback(() => {
    api.stats().then(setStats).catch(() => {})
  }, [])

  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])

  useEffect(() => {
    let live = true
    const onLoaded = (step) => setLoaded((current) => ({ ...current, [step]: true }))
    boot(api, { onLoaded }).then((result) => {
      if (!live) return
      if (!result || result.unauthorized || !result.data.me) {
        setUser(null)
        return
      }
      setStats(result.data.stats)
      setServiceLimits(result.data.limits)
      setUser(result.data.me)
      setBoot(result.data)
    })
    return () => {
      live = false
    }
  }, [bootKey])

  useEffect(() => {
    if (!user) return undefined
    connectEvents()
    return disconnectEvents
  }, [user])

  const reboot = (account) => {
    setUser(account)
    setBoot(null)
    setLoaded({})
    setBootKey((key) => key + 1)
  }

  const signIn = (account) => {
    rememberSession()
    setUser(account)
  }

  const signOut = () => {
    forgetSession()
    setUser(null)
  }

  const logout = async () => {
    if (!window.confirm(t('nav.confirmLogout'))) return
    setLeaving(true)
    await api.logout().catch(() => {})
    signOut()
  }

  if (user === undefined) return <Splash loaded={loaded} />
  if (user === null) return <Login onLogin={signIn} onLanguage={() => setLanguageOpen(true)} dialogOpen={languageOpen} onDialogClose={() => setLanguageOpen(false)} />
  if (user.terms_required) return <AcceptTerms email={user.email} onAccepted={reboot} onLogout={logout} />
  if (!boot) return <Splash loaded={loaded} />

  return (
    <div className="app">
      <header className="app-header">
        <a className="brand" href="#top"><BrandMark />Groundline</a>
        <nav className="app-tabs" aria-label="Groundline">
          <a
            href="#chat"
            aria-current={tab === 'chat' ? 'page' : undefined}
            onClick={(event) => { event.preventDefault(); setTab('chat') }}
          >
            {t('nav.chat')}
          </a>
          <a
            href="#documents"
            aria-current={tab === 'documents' ? 'page' : undefined}
            onClick={(event) => { event.preventDefault(); setTab('documents') }}
          >
            {t('nav.documents')}
          </a>
        </nav>
        <div className="app-user">
          <span>{user.email}</span>
          <button className="btn-quiet" type="button" onClick={() => setLanguageOpen(true)}>
            {t('nav.language')}: {locale.toUpperCase()}
          </button>
          <button className="btn-quiet" type="button" onClick={logout} disabled={leaving}>
            {leaving && <span className="dot-pulse" aria-hidden="true" />}
            {t('nav.logout')}
          </button>
        </div>
      </header>

      <main className="app-main chat-layout" hidden={tab !== 'chat'}>
        <Chat key={resetKey} initial={boot.history} onAnswered={refreshStats} />
        <aside className="telemetry" aria-label="Telemetry">
          <PipelineDiagram key={`pipeline-${resetKey}`} />
          <SavingsChart stats={stats} />
        </aside>
      </main>

      <Documents
        hidden={tab !== 'documents'}
        initial={boot.documents}
        stats={stats}
        onChanged={refreshStats}
        onAccountDeleted={signOut}
        onReset={() => {
          setBoot((current) => ({ ...current, history: [] }))
          setResetKey((key) => key + 1)
        }}
      />

      <ServiceLimitsBar initial={serviceLimits} />
      <LanguageDialog open={languageOpen} onClose={() => setLanguageOpen(false)} />
    </div>
  )
}
