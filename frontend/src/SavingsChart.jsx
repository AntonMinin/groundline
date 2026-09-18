import { useI18n } from './i18n.jsx'

export default function SavingsChart({ stats }) {
  const { t, n } = useI18n()
  if (!stats) return null

  const saved = stats.tokens_saved
  const spent = stats.tokens_used
  const total = saved + spent
  const share = Math.round((stats.cache_hit_rate || 0) * 100)

  return (
    <section className="panel">
      <div className="panel-head"><h2 className="kicker">{t('savings.title')}</h2></div>
      {total === 0 ? (
        <p className="muted">{t('savings.empty')}</p>
      ) : (
        <figure className="savings-figure">
          <div className="savings-share">
            <strong className="num">{share}%</strong>
            <span className="muted">{t('savings.share')}</span>
          </div>
          <div
            className="savings-bar"
            role="img"
            aria-label={`${t('savings.saved')} ${n(saved)}, ${t('savings.spent')} ${n(spent)}`}
          >
            <span className="saved" style={{ flex: saved || 0.001 }} />
            <span className="spent" style={{ flex: spent || 0.001 }} />
          </div>
          <ul className="savings-legend">
            <li><span className="key key-saved" aria-hidden="true" />{t('savings.saved')} <span className="num">{n(saved)}</span></li>
            <li><span className="key key-spent" aria-hidden="true" />{t('savings.spent')} <span className="num">{n(spent)}</span></li>
          </ul>
        </figure>
      )}
    </section>
  )
}
