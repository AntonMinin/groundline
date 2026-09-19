export const SITE = {
  name: 'Groundline',
  appUrl: process.env.PUBLIC_APP_URL || 'https://app.groundline.antonmb.com',
  repoUrl: process.env.PUBLIC_REPO_URL || 'https://github.com/AntonMinin/groundline',
  docsUrl: (process.env.PUBLIC_REPO_URL || 'https://github.com/AntonMinin/groundline') + '/tree/main/docs',
  author: 'Anton Minin Baranovskii',
  locales: ['en', 'ru'],
  defaultLocale: 'en',
}

export const MEASURED = {
  date: '2026-09-18',
  corpus: 'Northwind Robotics employee handbook, 1 document',
  cacheHitMs: 439,
  fullPipelineMs: 2620,
  tokensSavedPerHit: 849,
  hitSimilarity: 0.9916,
  threshold: 0.95,
  indexingMs: 2300,
  steps: 7,
  llmCallsOnMiss: 3,
  llmCallsOnHit: 0,
}

const STEPS = [
  ['check_cache', false],
  ['rewrite_query', true],
  ['retrieve', false],
  ['rerank', false],
  ['check_sufficiency', true],
  ['generate_answer', true],
  ['record', false],
]

export const CONTENT = {
  en: {
    lang: 'en',
    dir: '/',
    title: 'Groundline - answers from your documents, with a semantic cache',
    description:
      'Groundline answers questions about your own documents and caches answers by meaning, not by query string: a reworded question costs no LLM tokens.',
    nav: { how: 'How it works', auth: 'Why sign in', numbers: 'Numbers', faq: 'FAQ', repo: 'GitHub', demo: 'Open the demo' },
    otherLocale: { code: 'ru', label: 'Русский', href: '/ru' },
    hero: {
      kicker: 'RAG for your documents',
      title: 'Answers from your documents, and never pays twice for the same question',
      lede: 'Groundline indexes the files you upload and answers with the fragments it used. Answers are cached by the meaning of the question rather than its text, so "what is our SLA?" and "how fast must we respond under the contract?" share one cache entry - and the second one never reaches the language model.',
      facts: [
        [`${MEASURED.cacheHitMs} ms`, 'to answer from cache instead of ~2.6 s through the full pipeline'],
        [`${MEASURED.tokensSavedPerHit}`, 'tokens saved by a single cache hit, measured, not projected'],
        [`${MEASURED.steps}`, 'pipeline steps, each shown with its own time and token cost'],
      ],
    },
    how: {
      kicker: 'How it works',
      title: 'One question, seven steps, all of them visible',
      lede: 'A question is embedded and compared with earlier questions first; only a miss runs the rest. The interface shows which step is running, what the previous one took and how many tokens it spent.',
      steps: [
        'The question becomes a vector and is compared with questions already answered. Above the similarity threshold, the stored answer is returned immediately.',
        'The wording is rewritten into a precise search query: abbreviations expanded, vague terms resolved.',
        'Hybrid search over your chunks: vector search for paraphrases, full-text search for exact terms, merged by reciprocal rank fusion.',
        'A cross-encoder re-reads the candidates and keeps the five that actually answer the question.',
        'The model judges whether those fragments are enough. If not, the question is reformulated and searched again, at most twice.',
        'The answer is streamed from those fragments only, citing the file and chunk each claim came from.',
        'Answer, sources and per-step metrics go to the history, and to the cache for the next matching question.',
      ],
      llmNote: 'Steps marked LLM cost tokens. A cache hit runs none of them.',
    },
    auth: {
      kicker: 'Why sign in',
      title: 'The email step is part of the product, not paperwork',
      lede: 'The demo runs on free tiers of external services. Identifying the person is how that budget is shared fairly and how one person’s documents stay out of another’s answers.',
      items: [
        ['Personal quotas', 'Queries and documents are counted per account, not per service. One busy visitor cannot burn the day’s language-model budget for everyone else.'],
        ['Data isolation', 'Documents, history and cached answers belong to an account. Search only ever runs over your chunks, and the cache never returns someone else’s answer - enforced by Postgres row-level security, not only by application code.'],
        ['A code instead of a password', 'A six-digit code by email: no password to leak, no OAuth app, no extra personal data stored.'],
        ['Deletion in one step', 'The Documents screen deletes the account with every document, answer and cache entry. No support ticket.'],
      ],
    },
    numbers: {
      kicker: 'Cache numbers',
      title: 'What the semantic cache actually saved',
      lede: `Measured on ${MEASURED.date} against the demo corpus (${MEASURED.corpus}). These are readings from one run, not a benchmark - the same figures appear in the interface while you use it.`,
      rows: [
        ['Answer from cache', `${MEASURED.cacheHitMs} ms`, 'one embedding and one indexed lookup'],
        ['Answer through the full pipeline', `${(MEASURED.fullPipelineMs / 1000).toFixed(1)} s`, `${MEASURED.llmCallsOnMiss} language-model calls`],
        ['Tokens saved per hit', `${MEASURED.tokensSavedPerHit}`, `${MEASURED.llmCallsOnHit} language-model calls`],
        ['Similarity that produced the hit', `${MEASURED.hitSimilarity}`, `threshold ${MEASURED.threshold}`],
        ['Indexing the document', `${(MEASURED.indexingMs / 1000).toFixed(1)} s`, 'extraction, chunking and embeddings'],
      ],
      caption: 'Question asked twice, the second time reworded: "What is the vacation policy?" and "Whats the vacation policy?"',
    },
    limits: {
      kicker: 'Limits',
      title: 'What Groundline does not do',
      items: [
        ['Not a corporate search engine', 'The demo is sized for dozens of documents per account, not a company-wide archive.'],
        ['Answers only from what you uploaded', 'When the documents do not contain the answer, the sufficiency step stops the model from inventing one.'],
        ['PDF, TXT and MD only', 'Scans without a text layer, spreadsheets and slide decks are not parsed.'],
        ['Free provider tiers', 'When the daily quota of a provider runs out, requests are refused until it resets. The bar at the bottom of the app shows how much is left.'],
      ],
    },
    faq: {
      kicker: 'FAQ',
      title: 'Short answers',
      items: [
        [
          'How is a semantic cache different from a normal one?',
          'A normal cache compares the request string. A semantic cache compares embeddings, so a reworded question finds the same answer. The similarity threshold is configurable; below it the question runs the full pipeline.',
        ],
        [
          'Who can see my documents?',
          'Documents and chunks belong to your account and never enter anyone else’s search. Postgres row-level security enforces that at the database level. Text is sent to external models for embeddings and answer generation - the security notes in the repository list every service and what reaches it.',
        ],
        [
          'How many questions can I ask per day?',
          'The demo allows 50 questions a day and one document of up to 0.3 MB per account, with at least 15 seconds between questions. Cache hits are free and do not count. Your current usage is visible in the app.',
        ],
        [
          'Can I run it myself?',
          'Yes. The repository has a docker compose setup and documents every environment variable. Model and embedding providers are swapped by configuration, including fully local models.',
        ],
        [
          'What happens on a cache hit?',
          'Steps two to six never run. The answer and its sources come from the cache entry, and the interface marks check_cache as a hit with the similarity and the tokens saved.',
        ],
      ],
    },
    screenshots: {
      chat: 'The chat screen: a streamed answer with its sources, and the pipeline panel showing each step with its time and token cost.',
      documents: 'The documents screen: the upload area, the indexing queue and the list of indexed files.',
      limits: 'The service limits bar expanded: every external quota with how much is left and where the number came from.',
    },
    footer: { tagline: 'RAG for your documents', demo: 'Demo', repo: 'GitHub', docs: 'Documentation', privacy: 'Privacy', terms: 'Terms' },
  },

  ru: {
    lang: 'ru',
    dir: '/ru',
    title: 'Groundline - ответы по вашим документам с семантическим кэшем',
    description:
      'Groundline отвечает на вопросы по вашим документам и кэширует ответы по смыслу, а не по строке запроса: перефразированный вопрос не тратит токены LLM.',
    nav: { how: 'Как работает', auth: 'Зачем вход', numbers: 'Цифры', faq: 'FAQ', repo: 'GitHub', demo: 'Открыть демо' },
    otherLocale: { code: 'en', label: 'English', href: '/' },
    hero: {
      kicker: 'RAG по вашим документам',
      title: 'Отвечает по вашим документам и не платит дважды за один вопрос',
      lede: 'Groundline индексирует загруженные файлы и отвечает со ссылками на фрагменты, из которых собран ответ. Ответы кэшируются по смыслу вопроса, а не по его тексту: «какой у нас SLA?» и «сколько времени на реакцию по договору?» попадают в одну запись кэша, и второй запрос не идёт в языковую модель.',
      facts: [
        [`${MEASURED.cacheHitMs} мс`, 'ответ из кэша вместо ~2.6 с через полный пайплайн'],
        [`${MEASURED.tokensSavedPerHit}`, 'токенов сэкономило одно попадание в кэш - замер, не обещание'],
        [`${MEASURED.steps}`, 'шагов пайплайна, у каждого видно время и токены'],
      ],
    },
    how: {
      kicker: 'Как это работает',
      title: 'Один вопрос, семь шагов, и все они видны',
      lede: 'Вопрос сначала превращается в вектор и сравнивается с прошлыми вопросами; остальное выполняется только при промахе. В интерфейсе видно, какой шаг идёт сейчас, сколько занял предыдущий и сколько токенов потратил.',
      steps: [
        'Вопрос становится вектором и сравнивается с теми, на которые уже отвечали. Выше порога схожести готовый ответ отдаётся сразу.',
        'Формулировка переписывается в точный поисковый запрос: аббревиатуры раскрываются, размытые слова уточняются.',
        'Гибридный поиск по вашим фрагментам: векторный ловит перефразировки, полнотекстовый - точные термины, результаты объединяются ранговой фузией.',
        'Кросс-энкодер перечитывает кандидатов и оставляет пять, в которых действительно есть ответ.',
        'Модель проверяет, хватает ли этих фрагментов. Если нет - вопрос переформулируется и поиск повторяется, максимум дважды.',
        'Ответ пишется стримом строго по этим фрагментам, с указанием файла и чанка для каждого утверждения.',
        'Ответ, источники и метрики шагов уходят в историю и в кэш - для следующего похожего вопроса.',
      ],
      llmNote: 'Шаги с пометкой LLM тратят токены. При попадании в кэш не выполняется ни один из них.',
    },
    auth: {
      kicker: 'Зачем вход',
      title: 'Вход по email - часть продукта, а не формальность',
      lede: 'Демо работает на бесплатных тарифах внешних сервисов. Идентификация пользователя - способ честно разделить этот бюджет и не смешивать чужие документы с вашими ответами.',
      items: [
        ['Персональные квоты', 'Запросы и документы считаются на аккаунт, а не на весь сервис. Один активный посетитель не выжигает дневной бюджет модели для остальных.'],
        ['Изоляция данных', 'Документы, история и кэш ответов привязаны к аккаунту. Поиск идёт только по вашим фрагментам, а кэш не отдаёт чужой ответ - это обеспечивает row-level security в Postgres, а не только код приложения.'],
        ['Код вместо пароля', 'Шесть цифр на почту: пароль негде утечь, OAuth-приложение не нужно, лишние персональные данные не хранятся.'],
        ['Удаление в один шаг', 'Кнопка на экране «Документы» удаляет аккаунт со всеми файлами, ответами и кэшем. Без переписки с поддержкой.'],
      ],
    },
    numbers: {
      kicker: 'Цифры кэша',
      title: 'Что реально сэкономил семантический кэш',
      lede: `Замер ${MEASURED.date} на демо-корпусе (${MEASURED.corpus}). Это показания одного прогона, а не бенчмарк - те же цифры видны в интерфейсе во время работы.`,
      rows: [
        ['Ответ из кэша', `${MEASURED.cacheHitMs} мс`, 'один эмбеддинг и один индексный поиск'],
        ['Ответ через полный пайплайн', `${(MEASURED.fullPipelineMs / 1000).toFixed(1)} с`, `${MEASURED.llmCallsOnMiss} обращения к языковой модели`],
        ['Сэкономлено за попадание', `${MEASURED.tokensSavedPerHit} токенов`, `${MEASURED.llmCallsOnHit} обращений к модели`],
        ['Схожесть, давшая попадание', `${MEASURED.hitSimilarity}`, `порог ${MEASURED.threshold}`],
        ['Индексация документа', `${(MEASURED.indexingMs / 1000).toFixed(1)} с`, 'извлечение текста, нарезка и эмбеддинги'],
      ],
      caption: 'Вопрос задан дважды, второй раз другими словами: «What is the vacation policy?» и «Whats the vacation policy?»',
    },
    limits: {
      kicker: 'Ограничения',
      title: 'Чего Groundline не делает',
      items: [
        ['Это не корпоративный поиск', 'Демо рассчитано на десятки документов на аккаунт, а не на архив компании.'],
        ['Отвечает только по загруженному', 'Если ответа в документах нет, шаг проверки достаточности не даёт модели его выдумать.'],
        ['Форматы PDF, TXT и MD', 'Сканы без текстового слоя, таблицы и презентации не разбираются.'],
        ['Бесплатные тарифы провайдеров', 'Когда дневная квота провайдера кончается, запросы отклоняются до сброса. Полоса внизу приложения показывает остаток.'],
      ],
    },
    faq: {
      kicker: 'FAQ',
      title: 'Короткие ответы',
      items: [
        [
          'Чем семантический кэш отличается от обычного?',
          'Обычный кэш сравнивает строку запроса. Семантический сравнивает эмбеддинги, поэтому перефразированный вопрос находит тот же ответ. Порог схожести настраивается; ниже порога вопрос идёт в полный пайплайн.',
        ],
        [
          'Кто видит мои документы?',
          'Документы и фрагменты привязаны к аккаунту и в чужой поиск не попадают - это обеспечивает row-level security на уровне базы. Тексты уходят во внешние модели для эмбеддингов и генерации ответа: в разделе security репозитория перечислено, какой сервис что получает.',
        ],
        [
          'Сколько вопросов в день можно задать?',
          'В демо - 50 вопросов в сутки и один документ до 0,3 МБ на аккаунт, между вопросами не меньше 15 секунд. Попадания в кэш бесплатны и в счёт не идут. Текущий расход виден в приложении.',
        ],
        [
          'Можно развернуть у себя?',
          'Да. В репозитории есть docker compose и описание всех переменных окружения. Провайдеры моделей и эмбеддингов меняются конфигурацией, вплоть до полностью локальных.',
        ],
        [
          'Что происходит при попадании в кэш?',
          'Шаги со второго по шестой не выполняются. Ответ и источники берутся из записи кэша, а в интерфейсе check_cache помечается как попадание - со схожестью и числом сэкономленных токенов.',
        ],
      ],
    },
    screenshots: {
      chat: 'Экран чата: ответ пишется стримом, под ним источники, справа панель пайплайна с временем и токенами каждого шага.',
      documents: 'Экран документов: зона загрузки, очередь индексации и список проиндексированных файлов.',
      limits: 'Раскрытая полоса лимитов: каждая внешняя квота с остатком и пометкой, откуда взята цифра.',
    },
    footer: { tagline: 'RAG по вашим документам', demo: 'Демо', repo: 'GitHub', docs: 'Документация', privacy: 'Конфиденциальность', terms: 'Условия' },
  },
}

export const PIPELINE_STEPS = STEPS
