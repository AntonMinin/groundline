import { useI18n } from './i18n.jsx'

export default function StatsBar({ stats }) {
  const { t, n } = useI18n()
  if (!stats) return null

  const { cache_hit_rate, cache_hits, total_queries, usage, limits } = stats

  return (
    <section className="panel">
      <div className="panel-head"><h2 className="kicker">{t('stats.title')}</h2></div>
      <div className="stats-row">
        <div className="stat">
          <span className="stat-value num">{(cache_hit_rate * 100).toFixed(1)}%</span>
          <span className="stat-label">{t('stats.hitRate', { hits: cache_hits, total: total_queries })}</span>
        </div>
        <div className="stat">
          <span className="stat-value num">{n(usage.queries_last_24h)}/{n(limits.queries_per_day)}</span>
          <span className="stat-label">{t('stats.queries')}</span>
        </div>
        <div className="stat">
          <span className="stat-value num">{n(usage.documents)}/{n(limits.max_documents)}</span>
          <span className="stat-label">{t('stats.documents')}</span>
        </div>
      </div>
    </section>
  )
}
