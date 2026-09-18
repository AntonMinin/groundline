import { useEffect, useRef } from 'react'
import { LOCALES, useI18n } from './i18n.jsx'

export default function LanguageDialog({ open, onClose }) {
  const dialog = useRef(null)
  const { locale, setLocale, t } = useI18n()

  useEffect(() => {
    const node = dialog.current
    if (!node) return
    if (open && !node.open) node.showModal()
    if (!open && node.open) node.close()
  }, [open])

  const choose = (next) => {
    setLocale(next)
    onClose()
  }

  return (
    <dialog className="lang-dialog" ref={dialog} onClose={onClose}>
      <form method="dialog">
        <h2>{t('lang.title')}</h2>
        {Object.entries(LOCALES).map(([code, name]) => (
          <button
            key={code}
            type="button"
            className="lang-option"
            aria-current={code === locale}
            onClick={() => choose(code)}
          >
            <span>{name}</span>
            <span className="quota-src">{code.toUpperCase()}</span>
          </button>
        ))}
        <button className="btn btn-secondary" type="button" onClick={onClose}>{t('lang.close')}</button>
      </form>
    </dialog>
  )
}
