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
  threshold: 0.9,
  indexingMs: 2300,
  steps: 7,
  llmCallsOnMiss: 3,
  llmCallsOnHit: 0,
}

export const JEV_RESULTS = {
  measured: null,
  statusUrl: (process.env.PUBLIC_API_URL || 'https://api.groundline.antonmb.com') + '/eval/status',
  evaluationUrl:
    (process.env.PUBLIC_REPO_URL || 'https://github.com/AntonMinin/groundline') + '/blob/main/docs/evaluation.md',
  values: {
    faithfulness: [null, null],
    answer_correctness: [null, null],
    context_precision: [null, null],
    context_recall: [null, null],
    groq_calls: [null, null],
    groq_tokens: [null, null],
    done_median: [null, null],
    check_cache: [null, null],
    jev_sufficiency: [null, null],
    check_sufficiency: [null, null],
    generate_answer: [null, null],
    jev_cost: [null, null],
    cache_pairs: [null, null],
    wrong_hits: [null, null],
  },
}

const JEV_ROWS = [
  ['quality', ['faithfulness', 'answer_correctness', 'context_precision', 'context_recall']],
  ['groq', ['groq_calls', 'groq_tokens']],
  ['latency', ['done_median', 'check_cache', 'jev_sufficiency', 'check_sufficiency', 'generate_answer']],
  ['cache', ['cache_pairs', 'wrong_hits', 'jev_cost']],
]

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
    nav: { jev: 'Jev', how: 'How it works', auth: 'Why sign in', numbers: 'Numbers', faq: 'FAQ', repo: 'GitHub', demo: 'Open the demo' },
    otherLocale: { code: 'ru', label: 'Русский', href: '/ru' },
    jev: {
      kicker: 'Before and after Jev',
      title: 'Three checks moved from the language model to a decision model',
      lede: 'Jev is the first System One model from TypeSafe. It does not write text: it reads a state and typed questions and returns calibrated probabilities - yes or no, one option out of several, or a position on a scale. Groundline now asks it the yes-or-no questions a RAG pipeline used to put to its LLM.',
      why: [
        ['A decision, not a paragraph', 'Whether the fragments are enough is one bit. Asking a chat model for it costs a full prompt with every fragment and returns text that still has to be parsed.'],
        ['Calibrated, so a threshold means something', 'Jev returns a probability. The pipeline acts on a threshold chosen from measurements and hands only the uncertain cases to the LLM.'],
        ['Fails open', 'When Jev is slow, unavailable or out of budget, the pipeline takes its old path. No answer depends on Jev being up.'],
      ],
      checksTitle: 'Who makes each decision',
      before: 'Before',
      after: 'With Jev',
      checks: [
        ['Is the context enough to answer?', 'The LLM on every attempt, reading the question and all five fragments', 'Jev first; the LLM only when Jev is not sure, and it still writes the hint for the next search'],
        ['Is this the question already in the cache?', 'Embedding similarity alone: 0.90 or more is a hit', 'Jev confirms matches between 0.85 and 0.97: a paraphrase can hit below 0.90, a look-alike that asks something else misses'],
        ['Do the sources back the answer?', 'Not checked: any answer with sufficient context went to the cache', 'Jev grades the answer after it is shown; only supported answers are cached, and the chat shows the verdict'],
      ],
      resultsTitle: 'Measured on the GitLab Handbook corpus',
      resultsLede: 'Same questions in the same order, cache cleared before each run, every answer judged three times by the same judge. Quality is the mean of the three judge runs ± their spread.',
      groups: { quality: 'Answer quality (ragas)', groq: 'Groq per question', latency: 'Latency, median ms', cache: 'Cache and cost' },
      rows: {
        faithfulness: 'Faithfulness',
        answer_correctness: 'Answer correctness',
        context_precision: 'Context precision',
        context_recall: 'Context recall',
        groq_calls: 'LLM calls',
        groq_tokens: 'LLM tokens',
        done_median: 'Time to the full answer',
        check_cache: 'check_cache',
        jev_sufficiency: 'jev_sufficiency',
        check_sufficiency: 'check_sufficiency',
        generate_answer: 'generate_answer',
        cache_pairs: 'Cache pairs decided correctly',
        wrong_hits: 'Wrong cache hits',
        jev_cost: 'Jev cost per 100 questions, USD',
      },
      pending: 'pending',
      preliminary: 'Preliminary data, updating as the runs continue: {baseline} of {total} questions without Jev, {jev} of {total} with Jev. Last update: {date}.',
      userTitle: 'What changes for the person asking',
      user: [
        ['A grounding badge', 'Under every answer: supported, partly supported, not supported or contradicted - the same verdict that decides whether the answer is cached.'],
        ['An honest "not in the documents"', 'When the fragments do not cover the question, the answer still says so instead of guessing: Jev skips the LLM check only when it is confident the context is enough.', true],
        ['Fewer wrong cache hits', 'A question that reads like an earlier one but asks something else no longer receives the earlier answer.'],
      ],
      methodTitle: 'How it was measured',
      method: [
        ['Corpus', '8 pages of the GitLab Handbook on time off, leave, benefits, expenses and travel, pinned to commit f243917f, CC BY-SA 4.0 - 70 chunks.'],
        ['Dataset', '29 questions: answered by one chunk, answered across documents, unanswerable, distractors, 5 in Russian. Plus 20 cache pairs: paraphrases and look-alikes.'],
        ['Judge', 'ragas with gpt-oss-20b through OpenRouter on one pinned upstream, max_tokens 4096, three judgements per answer.'],
        ['Limits', 'One corpus and 29 questions on free-tier Groq. Differences smaller than the judge spread are noise. Jev is strongest in English.'],
      ],
      docsLink: 'Full method and per-question results',
    },
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
        ['Not a corporate search engine', 'The demo gives each account one document of up to 0.3 MB, not a company-wide archive.'],
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
    footer: {
      tagline: 'RAG for your documents',
      demo: 'Demo', repo: 'GitHub', docs: 'Documentation', privacy: 'Privacy', terms: 'Terms',
      made: 'Made with ❤️ by',
      rights:
        'All rights reserved. Automated data collection, content extraction and unauthorised redistribution are strictly prohibited.',
    },
  },

  ru: {
    lang: 'ru',
    dir: '/ru',
    title: 'Groundline - ответы по вашим документам с семантическим кэшем',
    description:
      'Groundline отвечает на вопросы по вашим документам и кэширует ответы по смыслу, а не по строке запроса: перефразированный вопрос не тратит токены LLM.',
    nav: { jev: 'Jev', how: 'Как работает', auth: 'Зачем вход', numbers: 'Цифры', faq: 'FAQ', repo: 'GitHub', demo: 'Открыть демо' },
    otherLocale: { code: 'en', label: 'English', href: '/' },
    jev: {
      kicker: 'До Jev и после Jev',
      title: 'Три проверки перешли от языковой модели к модели для решений',
      lede: 'Jev - первая модель System One от TypeSafe. Она не пишет текст: получает состояние и типизированные вопросы и возвращает калиброванные вероятности - да или нет, один вариант из нескольких или позицию на шкале. Groundline теперь задаёт ей те вопросы «да или нет», которые RAG-пайплайн раньше задавал своей LLM.',
      why: [
        ['Решение, а не абзац', 'Хватает ли фрагментов - это один бит. Спросить об этом чат-модель - значит отправить полный промпт со всеми фрагментами и потом разбирать текст ответа.'],
        ['Калибровка, поэтому у порога есть смысл', 'Jev возвращает вероятность. Пайплайн действует по порогу, подобранному на замерах, и отдаёт LLM только неуверенные случаи.'],
        ['Отказ не ломает запрос', 'Если Jev медленный, недоступен или кончился бюджет, пайплайн идёт старым путём. Ни один ответ не зависит от того, работает ли Jev.'],
      ],
      checksTitle: 'Кто принимает каждое решение',
      before: 'До',
      after: 'С Jev',
      checks: [
        ['Хватает ли контекста для ответа?', 'LLM на каждой попытке: вопрос и все пять фрагментов', 'Сначала Jev; LLM - только если Jev не уверен, и она по-прежнему пишет подсказку для следующего поиска'],
        ['Это тот же вопрос, что уже есть в кэше?', 'Только сходство эмбеддингов: от 0.90 - попадание', 'Jev подтверждает совпадения от 0.85 до 0.97: перефраз может попасть ниже 0.90, похожий по словам вопрос с другим смыслом - нет'],
        ['Подтверждают ли источники ответ?', 'Не проверялось: в кэш шёл любой ответ при достаточном контексте', 'Jev оценивает ответ после показа; в кэш идут только подтверждённые, а в чате виден вердикт'],
      ],
      resultsTitle: 'Замер на корпусе GitLab Handbook',
      resultsLede: 'Одни и те же вопросы в одном порядке, кэш очищен перед каждым прогоном, каждый ответ оценён одним судьёй трижды. Качество - среднее трёх оценок ± их разброс.',
      groups: { quality: 'Качество ответа (ragas)', groq: 'Groq на вопрос', latency: 'Задержка, медиана, мс', cache: 'Кэш и стоимость' },
      rows: {
        faithfulness: 'Faithfulness',
        answer_correctness: 'Answer correctness',
        context_precision: 'Context precision',
        context_recall: 'Context recall',
        groq_calls: 'Вызовы LLM',
        groq_tokens: 'Токены LLM',
        done_median: 'Время до полного ответа',
        check_cache: 'check_cache',
        jev_sufficiency: 'jev_sufficiency',
        check_sufficiency: 'check_sufficiency',
        generate_answer: 'generate_answer',
        cache_pairs: 'Пары для кэша решены верно',
        wrong_hits: 'Ложные попадания в кэш',
        jev_cost: 'Стоимость Jev на 100 вопросов, USD',
      },
      pending: 'ждёт прогона',
      preliminary: 'Предварительные данные, обновляются по ходу прогонов: {baseline} из {total} вопросов без Jev, {jev} из {total} с Jev. Последнее обновление: {date}.',
      userTitle: 'Что меняется для того, кто спрашивает',
      user: [
        ['Бейдж обоснованности', 'Под каждым ответом: подтверждено, подтверждено частично, не подтверждено или противоречит - тот же вердикт решает, попадёт ли ответ в кэш.'],
        ['Честное «в документах этого нет»', 'Если фрагменты не покрывают вопрос, ответ так и говорит, а не угадывает: Jev пропускает проверку LLM, только когда уверен, что контекста достаточно.', true],
        ['Меньше ложных попаданий в кэш', 'Вопрос, похожий по словам на прошлый, но о другом, больше не получает чужой ответ.'],
      ],
      methodTitle: 'Как измеряли',
      method: [
        ['Корпус', '8 страниц GitLab Handbook об отпусках, leave, льготах, расходах и командировках, зафиксированы на коммите f243917f, CC BY-SA 4.0 - 70 чанков.'],
        ['Датасет', '29 вопросов: ответ в одном чанке, ответ из нескольких документов, неотвечаемые, дистракторы, 5 на русском. Плюс 20 пар для кэша: перефразы и похожие по словам вопросы.'],
        ['Судья', 'ragas с gpt-oss-20b через OpenRouter на одном закреплённом апстриме, max_tokens 4096, три оценки на ответ.'],
        ['Ограничения', 'Один корпус и 29 вопросов на бесплатном тарифе Groq. Разница меньше разброса судьи - это шум. Сильнее всего Jev на английском.'],
      ],
      docsLink: 'Полная методика и результаты по вопросам',
    },
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
        ['Это не корпоративный поиск', 'В демо на аккаунт даётся один документ до 0,3 МБ, а не архив компании.'],
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
    footer: {
      tagline: 'RAG по вашим документам',
      demo: 'Демо', repo: 'GitHub', docs: 'Документация', privacy: 'Конфиденциальность', terms: 'Условия',
      made: 'Сделано с ❤️',
      rights:
        'Все права защищены. Автоматический сбор данных, извлечение содержимого и несанкционированное распространение строго запрещены.',
    },
  },
}

export const PIPELINE_STEPS = STEPS
export const JEV_TABLE = JEV_ROWS
