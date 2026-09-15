import { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'
import Login from './Login.jsx'
import Documents from './Documents.jsx'
import Chat from './Chat.jsx'
import StatsBar from './StatsBar.jsx'

export default function App() {
  const [user, setUser] = useState(undefined)
  const [tab, setTab] = useState('chat')
  const [stats, setStats] = useState(null)

  const refreshStats = useCallback(() => {
    api.stats().then(setStats).catch(() => {})
  }, [])

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null))
  }, [])

  useEffect(() => {
    if (user) refreshStats()
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
      {tab === 'chat' ? (
        <Chat onAnswered={refreshStats} />
      ) : (
        <Documents onChanged={refreshStats} onAccountDeleted={() => setUser(null)} />
      )}
    </main>
  )
}
