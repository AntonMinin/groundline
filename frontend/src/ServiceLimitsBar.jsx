import { useEffect, useState } from 'react'
import { onEvent } from './events.js'
import { useI18n } from './i18n.jsx'
import { isDegraded, shareLeft, stateOf, worstOf } from './telemetry.js'

export default function ServiceLimitsBar({ initial }) {
  const [services, setServices] = useState(initial?.services ?? [])
  const [degraded, setDegraded] = useState(Boolean(initial?.degraded))
  const [checkedAt, setCheckedAt] = useState(initial?.checked_at ?? null)
  const { t, n, locale } = useI18n()

  useEffect(
    () =>
      onEvent((event) => {
        if (event.type !== 'limits') return
        setServices(event.services)
        setDegraded(Boolean(event.degraded))
        setCheckedAt(event.timestamp)
      }),
    [],
  )

  if (services.length === 0) return null

  const worst = worstOf(services)
  const status = degraded ? 'warn' : stateOf(worst ? worst.share : null)
  const time = (value) =>
    value ? new Date(value).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

  const amount = (service) => {
    if (isDegraded(service)) return t('limits.unknown')
    if (service.used === null || service.used === undefined) return t('limits.dashboard')
    if (service.unit === 'usd') return `$${service.used.toFixed(2)} / $${service.limit.toFixed(2)}`
    if (!service.limit) return n(Math.round(service.used))
    return `${n(Math.round(service.used))} / ${n(service.limit)}`
  }

  return (
    <details className="limits">
      <summary>
        <span className="limits-status">
          <span className="led" data-state={status === 'ok' ? 'ok' : status} aria-hidden="true" />
          {degraded ? t('limits.degraded') : t(`limits.${status === 'manual' ? 'ok' : status}`)}
        </span>
        {!degraded && worst && (
          <span className="limits-peak">
            {t('limits.peak', {
              service: worst.service.service,
              title: worst.service.title.toLowerCase(),
              value: amount(worst.service),
            })}
          </span>
        )}
        {!degraded && worst && (
          <span className="limits-reset">{t('limits.reset', { time: time(worst.service.resets_at) })}</span>
        )}
        <span className="limits-more">{t('limits.more')}</span>
      </summary>

      <div className="limits-grid">
        {services.map((service) => {
          const share = shareLeft(service)
          return (
            <div className="quota" key={service.key} data-state={stateOf(share)}>
              <span className="quota-name">
                <b>{service.service}</b>
                <span>
                  {service.title.toLowerCase()} {service.period === 'day' ? t('limits.perDay') : t('limits.perMonth')}
                </span>
                <span className="quota-src">
                  {service.used === null || service.used === undefined
                    ? ''
                    : service.provider_reported
                      ? t('limits.provider')
                      : t('limits.local')}
                </span>
                {service.limit_outdated && (
                  <span className="quota-src quota-flag">
                    {t('limits.outdated', { found: n(service.limit_found_on_page ?? 0) })}
                  </span>
                )}
              </span>
              <span className="quota-value">{amount(service)}</span>
              <span className="quota-meter" aria-hidden="true">
                <i style={{ width: share === null ? 0 : `${Math.round((1 - share) * 100)}%` }} />
              </span>
            </div>
          )
        })}
      </div>
      <p className="limits-foot">
        {degraded ? t('limits.degradedFoot') : t('limits.checked', { time: time(checkedAt) })}
      </p>
    </details>
  )
}
