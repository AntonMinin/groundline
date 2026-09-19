import { createContext, useContext, useMemo, useState } from 'react'

export const LOCALES = { en: 'English', ru: 'Русский' }
const STORAGE_KEY = 'groundline.locale'
const DEFAULT = 'en'

const DICT = {
  en: {
    'nav.chat': 'Chat',
    'nav.documents': 'Documents',
    'nav.logout': 'Log out',
    'nav.confirmLogout': 'Log out of Groundline? Your documents and history stay.',
    'nav.language': 'Language',
    'lang.title': 'Interface language',
    'lang.close': 'Close',
    'login.tagline': 'Answers grounded in your documents.',
    'login.email': 'Email',
    'login.code': '6-digit code from email',
    'login.send': 'Send code',
    'login.signin': 'Sign in',
    'login.another': 'Use another email',
    'login.captcha': 'Could not load the captcha, reload the page',
    'chat.placeholder': 'Ask about your documents…',
    'chat.ask': 'Ask',
    'chat.asking': 'Asking…',
    'chat.empty': 'Ask a question about your documents.',
    'chat.sources': 'Sources ({count})',
    'chat.chunk': 'chunk {index}',
    'chat.page': 'page {page}',
    'chat.cacheHit': 'cache hit · similarity {similarity}',
    'chat.cacheMiss': 'cache miss',
    'chat.saved': '{tokens} tok saved',
    'chat.tokens': '{tokens} tok',
    'step.check_cache': 'check_cache — looking for a matching question…',
    'step.rewrite_query': 'rewrite_query — sharpening the search query…',
    'step.retrieve': 'retrieve — searching your documents…',
    'step.rerank': 'rerank — ranking the best fragments…',
    'step.check_sufficiency': 'check_sufficiency — is this enough to answer?…',
    'step.generate_answer': 'generate_answer — writing the answer…',
    'step.record': 'record — saving…',
    'pipeline.title': 'Pipeline',
    'pipeline.stepsOf': '{done}/{total} steps',
    'pipeline.idle': 'Ask a question to see per-step timings.',
    'pipeline.previous': 'Previous query',
    'pipeline.cacheNote': 'nearest cached question {similarity} — below the {threshold} threshold',
    'pipeline.cacheHitNote': 'nearest cached question {similarity} — cache hit',
    'savings.title': 'Token savings',
    'savings.saved': 'Saved',
    'savings.spent': 'Spent',
    'savings.empty': 'No questions yet.',
    'docs.title': 'Documents',
    'docs.summary': '{documents}/{limit} documents · {chunks} chunks',
    'docs.dropTitle': 'Drop files here',
    'docs.dropHint': 'or click to choose. PDF, TXT, MD up to {size} MB. Indexing starts right after upload.',
    'docs.full': 'Limit reached — delete the current document to upload another.',
    'docs.uploading': 'Uploading…',
    'docs.indexing': 'Indexing',
    'docs.uploaded': 'Uploaded',
    'docs.file': 'File',
    'docs.status': 'Status',
    'docs.chunks': 'Chunks',
    'docs.size': 'Size',
    'docs.uploadedAt': 'Uploaded',
    'docs.actions': 'Actions',
    'docs.delete': 'Delete',
    'docs.indexed': 'indexed',
    'docs.reset': 'Reset demo',
    'docs.deleteAccount': 'Delete account',
    'docs.confirmReset': 'Delete all documents, the answer cache and the query history? Your account stays.',
    'docs.confirmDelete': 'Delete your account, all documents and history? This cannot be undone.',
    'job.queued': 'queued',
    'job.processing': 'extracting text and building embeddings…',
    'job.done': 'indexed',
    'job.error': 'error: {error}',
    'limits.ok': 'Service limits are healthy',
    'limits.warn': 'A service limit is running low',
    'limits.error': 'A service limit is exhausted',
    'limits.peak': 'closest: {service} {title} {value}',
    'limits.reset': 'resets {time}',
    'limits.more': 'details',
    'limits.checked': 'Checked {time}. Quotas marked “dashboard” are not metered by the application.',
    'limits.dashboard': 'see dashboard',
    'limits.provider': 'from provider',
    'limits.local': 'counted locally',
    'limits.outdated': 'limit may be outdated: page says {found}',
    'limits.empty': 'No metered services.',
    'limits.unknown': 'unknown',
    'limits.degraded': 'Limit data unavailable, quotas are not being enforced',
    'limits.degradedFoot': 'The usage counters could not be read, so these numbers are unknown rather than zero. Limits are not enforced until the counters are readable again.',
    'limits.perDay': '/ day',
    'limits.perMonth': '/ month',
  },
  ru: {
    'nav.chat': 'Чат',
    'nav.documents': 'Документы',
    'nav.logout': 'Выйти',
    'nav.confirmLogout': 'Выйти из Groundline? Документы и история останутся.',
    'nav.language': 'Язык',
    'lang.title': 'Язык интерфейса',
    'lang.close': 'Закрыть',
    'login.tagline': 'Ответы строго по вашим документам.',
    'login.email': 'Email',
    'login.code': 'Код из письма, 6 цифр',
    'login.send': 'Выслать код',
    'login.signin': 'Войти',
    'login.another': 'Другой адрес',
    'login.captcha': 'Не удалось загрузить капчу, перезагрузите страницу',
    'chat.placeholder': 'Спросите о своих документах…',
    'chat.ask': 'Спросить',
    'chat.asking': 'Спрашиваю…',
    'chat.empty': 'Задайте вопрос по своим документам.',
    'chat.sources': 'Источники ({count})',
    'chat.chunk': 'chunk {index}',
    'chat.page': 'стр. {page}',
    'chat.cacheHit': 'cache hit · similarity {similarity}',
    'chat.cacheMiss': 'cache miss',
    'chat.saved': '{tokens} tok сэкономлено',
    'chat.tokens': '{tokens} tok',
    'step.check_cache': 'check_cache — ищет похожий вопрос…',
    'step.rewrite_query': 'rewrite_query — уточняет поисковый запрос…',
    'step.retrieve': 'retrieve — ищет по документам…',
    'step.rerank': 'rerank — отбирает лучшие фрагменты…',
    'step.check_sufficiency': 'check_sufficiency — проверяет, хватает ли материала…',
    'step.generate_answer': 'generate_answer — пишет ответ…',
    'step.record': 'record — сохраняет…',
    'pipeline.title': 'Pipeline',
    'pipeline.stepsOf': '{done}/{total} шагов',
    'pipeline.idle': 'Задайте вопрос — здесь появятся шаги с временем и токенами.',
    'pipeline.previous': 'Прошлый запрос',
    'pipeline.cacheNote': 'ближайший вопрос в кэше {similarity} — ниже порога {threshold}',
    'pipeline.cacheHitNote': 'ближайший вопрос в кэше {similarity} — попадание',
    'savings.title': 'Экономия токенов',
    'savings.saved': 'Сэкономлено',
    'savings.spent': 'Потрачено',
    'savings.empty': 'Запросов пока не было.',
    'docs.title': 'Документы',
    'docs.summary': '{documents}/{limit} документов · {chunks} чанков',
    'docs.dropTitle': 'Перетащите файлы сюда',
    'docs.dropHint': 'или нажмите, чтобы выбрать. PDF, TXT, MD до {size} МБ. Индексация начинается сразу после загрузки.',
    'docs.full': 'Лимит достигнут — удалите текущий документ, чтобы загрузить новый.',
    'docs.uploading': 'Загрузка…',
    'docs.indexing': 'Индексация',
    'docs.uploaded': 'Загружено',
    'docs.file': 'Файл',
    'docs.status': 'Статус',
    'docs.chunks': 'Чанки',
    'docs.size': 'Размер',
    'docs.uploadedAt': 'Загружен',
    'docs.actions': 'Действия',
    'docs.delete': 'Удалить',
    'docs.indexed': 'проиндексирован',
    'docs.reset': 'Сбросить демо',
    'docs.deleteAccount': 'Удалить аккаунт',
    'docs.confirmReset': 'Удалить все документы, кэш ответов и историю? Аккаунт останется.',
    'docs.confirmDelete': 'Удалить аккаунт со всеми документами и историей? Это необратимо.',
    'job.queued': 'в очереди',
    'job.processing': 'извлечение текста и эмбеддинги…',
    'job.done': 'проиндексирован',
    'job.error': 'ошибка: {error}',
    'limits.ok': 'Лимиты сервисов в норме',
    'limits.warn': 'Лимит сервиса на исходе',
    'limits.error': 'Лимит сервиса исчерпан',
    'limits.peak': 'ближайший: {service} {title} {value}',
    'limits.reset': 'сброс {time}',
    'limits.more': 'детали',
    'limits.checked': 'Проверено {time}. Квоты с пометкой «по дашборду» приложение не измеряет.',
    'limits.dashboard': 'по дашборду',
    'limits.provider': 'от провайдера',
    'limits.local': 'считаем сами',
    'limits.outdated': 'лимит мог устареть: на странице {found}',
    'limits.empty': 'Измеряемых сервисов нет.',
    'limits.unknown': 'неизвестно',
    'limits.degraded': 'Данные о лимитах недоступны, квоты не ограничивают',
    'limits.degradedFoot': 'Счётчики расхода не читаются, поэтому цифры неизвестны, а не равны нулю. Пока счётчики недоступны, лимиты не применяются.',
    'limits.perDay': '/ день',
    'limits.perMonth': '/ месяц',
  },
}

function stored() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved && DICT[saved] ? saved : DEFAULT
  } catch {
    return DEFAULT
  }
}

function fill(template, vars) {
  return Object.entries(vars).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, value), template)
}

const LocaleContext = createContext(null)

export function LocaleProvider({ children }) {
  const [locale, setLocale] = useState(stored)

  const value = useMemo(() => {
    const change = (next) => {
      setLocale(next)
      document.documentElement.lang = next
      try {
        localStorage.setItem(STORAGE_KEY, next)
      } catch {}
    }
    const t = (key, vars) => {
      const template = DICT[locale][key] ?? DICT[DEFAULT][key] ?? key
      return vars ? fill(template, vars) : template
    }
    return { locale, setLocale: change, t, n: (value) => Number(value).toLocaleString(locale) }
  }, [locale])

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}

export function useI18n() {
  const value = useContext(LocaleContext)
  if (!value) throw new Error('useI18n outside LocaleProvider')
  return value
}
