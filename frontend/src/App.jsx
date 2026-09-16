import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import { connectEvents, disconnectEvents } from './events.js'
import Login from './Login.jsx'
import Documents from './Documents.jsx'
import Chat from './Chat.jsx'
import StatsBar from './StatsBar.jsx'
import SavingsChart from './SavingsChart.jsx'
import PipelineDiagram from './PipelineDiagram.jsx'

export default function App() {
  const [user, setUser] = useState(undefined)
  const [tab, setTab] = useState('chat')
  const [stats, setStats] = useState(null)
  const [resetKey, setResetKey] = useState(0)

  const refreshStats = useCallback(() => {
    api.stats().then(setStats).catch(() => {})
  }, [])

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

  if (user === undefined) return <main className="center">Loading…</main>
  if (user === null) return <Login onLogin={setUser} />

  return (
    <main>
      <header>
        <strong>Groundline</strong>
        <nav>
          <button className={tab === 'chat' ? 'active' : ''} onClick={() => setTab('chat')}>Chat</button>
          <button className={tab === 'documents' ? 'active' : ''} onClick={() => setTab('documents')}>Documents</button>
        </nav>
        <span className="spacer" />
        <span className="muted">{user.email}</span>
        <button onClick={logout}>Log out</button>
      </header>
      <StatsBar stats={stats} />
      <div className="visuals">
        <SavingsChart key={`chart-${resetKey}`} />
        <PipelineDiagram key={`diagram-${resetKey}`} />
      </div>
      <div hidden={tab !== 'chat'}>
        <Chat key={resetKey} onAnswered={refreshStats} />
      </div>
      <div hidden={tab !== 'documents'}>
        <Documents
          onChanged={refreshStats}
          onAccountDeleted={() => setUser(null)}
          onReset={() => setResetKey((key) => key + 1)}
        />
      </div>
    </main>
  )
}
