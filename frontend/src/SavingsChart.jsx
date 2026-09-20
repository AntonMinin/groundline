import { useI18n } from './i18n.jsx'

export default function SavingsChart({ stats, pending }) {
  const { t, n } = useI18n()
  if (!stats) return null

  const saved = stats.tokens_saved
  const spent = stats.tokens_used
  const total = saved + spent
  const share = Math.round((stats.cache_hit_rate || 0) * 100)

  return (
    <section className="panel" aria-busy={pending || undefined}>
      <div className="panel-head">
        <h2 className="kicker">
          {t('savings.title')}
          {pending && <span className="dot-pulse" aria-hidden="true" />}
        </h2>
      </div>
      {total === 0 ? (
        <p className="muted">{t('savings.empty')}</p>
      ) : (
        <figure className="savings-figure" data-pending={pending || undefined}>
          <div className="savings-share">
            <strong className="num">{share}%</strong>
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
