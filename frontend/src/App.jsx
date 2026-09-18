import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { connectEvents, disconnectEvents } from './events.js'
import { useI18n } from './i18n.jsx'
import Login from './Login.jsx'
import Documents from './Documents.jsx'
import Chat from './Chat.jsx'
import StatsBar from './StatsBar.jsx'
import SavingsChart from './SavingsChart.jsx'
import PipelineDiagram from './PipelineDiagram.jsx'
import ServiceLimitsBar from './ServiceLimitsBar.jsx'
import LanguageDialog from './LanguageDialog.jsx'

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

export default function App() {
  const [user, setUser] = useState(undefined)
  const [tab, setTab] = useState('chat')
  const [stats, setStats] = useState(null)
  const [resetKey, setResetKey] = useState(0)
  const [languageOpen, setLanguageOpen] = useState(false)
  const { t, locale } = useI18n()

  const refreshStats = useCallback(() => {
    api.stats().then(setStats).catch(() => {})
  }, [])

  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null))
  }, [])

  useEffect(() => {
    if (!user) return undefined
    refreshStats()
    connectEvents()
    return disconnectEvents
  }, [user, refreshStats])

  const logout = async () => {
    await api.logout().catch(() => {})
    setUser(null)
  }

  if (user === undefined) return <main className="center"><p className="muted">…</p></main>
  if (user === null) return <Login onLogin={setUser} onLanguage={() => setLanguageOpen(true)} dialogOpen={languageOpen} onDialogClose={() => setLanguageOpen(false)} />

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
          <button className="btn-quiet" type="button" onClick={logout}>{t('nav.logout')}</button>
        </div>
      </header>

      <main className="app-main chat-layout" hidden={tab !== 'chat'}>
        <Chat key={resetKey} onAnswered={refreshStats} />
        <aside className="telemetry" aria-label="Telemetry">
          <PipelineDiagram key={`pipeline-${resetKey}`} />
          <SavingsChart stats={stats} />
          <StatsBar stats={stats} />
        </aside>
      </main>

      <Documents
        hidden={tab !== 'documents'}
        stats={stats}
        onChanged={refreshStats}
        onAccountDeleted={() => setUser(null)}
        onReset={() => setResetKey((key) => key + 1)}
      />

      <ServiceLimitsBar />
      <LanguageDialog open={languageOpen} onClose={() => setLanguageOpen(false)} />
    </div>
  )
}
