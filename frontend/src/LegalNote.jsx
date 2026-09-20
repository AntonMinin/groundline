import { useI18n } from './i18n.jsx'

const HOME = 'https://www.antonmb.com'

function Home() {
  return <a href={HOME} target="_blank" rel="noopener">antonmb.com</a>
}

export default function LegalNote({ className = 'legal-note' }) {
  const { t } = useI18n()
  return (
    <div className={className}>
      <p>© {new Date().getFullYear()} <Home /> · Groundline</p>
      <p>{t('legal.made')} <Home /></p>
      <p>{t('legal.rights')}</p>
    </div>
  )
}
