export const UPDATED = '2026-09-26'

export const LEGAL = {
  en: {
    privacy: {
      title: 'Privacy - Groundline',
      heading: 'What Groundline stores, where it goes, and how to delete it',
      description:
        'Plain-language privacy notice for the Groundline demo: what is collected (email, uploaded documents, questions), where it is stored and which external services receive it.',
      lede: 'Short version: Groundline keeps your email address, the documents you upload, and the questions and answers from your account. Document text is sent to external models to answer questions. Deleting your account removes all of it immediately.',
      sections: [
        {
          h: 'What is collected',
          list: [
            ['Your email address', 'the only account identifier. There is no password, no profile and no tracking of you across other sites.'],
            ['Documents you upload', 'stored as extracted text, split into fragments, each with a numeric representation of its meaning used for search.'],
            ['Your questions and answers', 'kept as history and as cache entries, so a repeated question can be answered without paying for it again.'],
            ['Technical records', 'timing and token counts per request, the IP address of login-code requests (to rate-limit abuse), and server logs.'],
          ],
        },
        {
          h: 'Where it is stored',
          body: 'In a single Postgres database hosted by Supabase in the EU. Every row is tied to an account, and the database itself enforces that one account cannot read another’s rows - not just the application code.',
        },
        {
          h: 'Which services receive what',
          table: [
            ['Render', 'Runs the backend, so every request passes through it: your questions, your uploads and your email address. Its logs keep the technical records above.'],
            ['Vercel', 'Serves the pages, so it sees the IP address and browser of every visit. No document text and no email address.'],
            ['Groq', 'Your question and the document fragments chosen to answer it. Used to write the answer.'],
            ['OpenRouter and TypeSafe', 'Your question, the document fragments chosen to answer it, the answer, and the earlier question a cached answer belongs to. OpenRouter passes them to TypeSafe’s Jev model, which checks whether the fragments are enough to answer, whether a cached question asks the same thing, and whether the sources back the answer. Jev returns probabilities, not text.'],
            ['DeepInfra', 'The text of your document fragments and of your questions. Used to turn text into the vectors that make search work.'],
            ['Pinecone', 'Your question and the candidate fragments. Used to rank which fragments actually answer it.'],
            ['LangFuse', 'A trace of each request: the question, the answer and the fragments used, for debugging and cost analysis.'],
            ['Resend', 'Your email address and the six-digit login code.'],
            ['Cloudflare Turnstile', 'A challenge token and your IP address, to keep bots from requesting login codes.'],
            ['Upstash', 'Counters only - how many login codes an IP requested, how many streams an account holds. No document text.'],
            ['Vercel Analytics and Speed Insights', 'Page views and page-load timings, aggregated. Cookieless, no identifier that follows you to other sites, no document text and no email address.'],
          ],
          after:
            'Running Groundline yourself with local models keeps document text inside your own infrastructure; the hosted demo does not.',
        },
        {
          h: 'How long it is kept',
          body: 'Documents, history and cached answers stay until you delete them or delete your account. Login codes expire after 10 minutes, and the record of a code request (address and IP) is deleted after seven days. Sessions last seven days; logging out ends every session of the account. LangFuse keeps traces for 30 days on its free plan.',
        },
        {
          h: 'How to delete it',
          body: 'The Documents screen has two buttons: one clears documents, cache and history; the other deletes the account entirely. Deletion is immediate and cascades to every table - there is no soft delete and no recovery. The same is available over the API as DELETE /me.',
        },
        {
          h: 'What is not done',
          list: [
            ['No advertising and no third-party trackers', 'the landing page and the app measure page views and load times through Vercel, which sets no cookies and builds no cross-site profile. Nothing else is loaded.'],
            ['No selling or sharing', 'data goes only to the services listed above, and only to answer your questions.'],
            ['No training on your documents', 'the providers are used through their APIs; check their own terms for their retention policies.'],
          ],
        },
        {
          h: 'Contact',
          body: 'Data controller: Anton Minin Baranovskii (a private individual). Enquiries about personal data: hi@antonmb.com.',
          after:
            'Write if you want to talk about the product, an engineering problem, a consultation or working together. Open to conversations about the book as well: interviews, publications, talks.',
          links: [
            ['hi@antonmb.com', 'mailto:hi@antonmb.com'],
            ['Telegram', 'https://t.me/AntonMinin'],
            ['LinkedIn', 'https://www.linkedin.com/in/antonmininbaranovskii/'],
          ],
        },
      ],
    },
    terms: {
      title: 'Terms - Groundline',
      heading: 'Terms of use',
      description: 'Terms for the Groundline demo: a demonstration service, offered as is, with per-account quotas and no availability guarantee.',
      lede: 'Short version: this is a demonstration project, not a product you should depend on. It can be slow, it can be down, and it can lose your data. Do not upload anything confidential.',
      sections: [
        {
          h: 'What this is',
          body: 'Groundline is a personal portfolio project that answers questions about documents you upload. It runs on free tiers of external services and is offered free of charge.',
        },
        {
          h: 'No guarantees',
          body: 'The service is provided as is, without any warranty. There is no uptime commitment, no support commitment and no backup of your data. The backend sleeps when idle, so the first request after a pause can take up to a minute. Quotas of external providers can run out and refuse requests until they reset.',
        },
        {
          h: 'Do not upload confidential data',
          body: 'Document text is sent to external model providers to answer questions, as listed in the privacy notice. Do not upload personal data about other people, trade secrets, credentials, medical or financial records, or anything you are not free to share with those providers.',
        },
        {
          h: 'Limits',
          list: [
            ['50 questions per account per day', 'answers served from cache are free and do not count.'],
            ['At least 15 seconds between questions', 'the demo runs on one small instance.'],
            ['1 document per account, up to 0.3 MB', 'delete it to upload another; 200 MB of storage per account.'],
            ['3 login codes per address per day', 'and a limit per IP address.'],
            ['PDF, TXT and MD only', 'other formats are rejected.'],
          ],
        },
        {
          h: 'Acceptable use',
          body: 'Do not use the service to break the law, to upload content you have no right to, to attack the infrastructure or to work around its quotas. Accounts doing any of that can be removed without notice.',
        },
        {
          h: 'Answers are not advice',
          body: 'Answers are generated from your documents by a language model and can be wrong or incomplete. Every answer cites the fragments it used - check them before acting. Nothing here is legal, medical or financial advice.',
        },
        {
          h: 'Changes and shutdown',
          body: 'The service can change or disappear at any time, including permanent deletion of stored data. Export anything you care about.',
        },
        {
          h: 'Who runs this',
          body: 'Data controller: Anton Minin Baranovskii (a private individual). Enquiries about personal data: hi@antonmb.com.',
          links: [
            ['hi@antonmb.com', 'mailto:hi@antonmb.com'],
            ['Telegram', 'https://t.me/AntonMinin'],
            ['LinkedIn', 'https://www.linkedin.com/in/antonmininbaranovskii/'],
          ],
        },
      ],
    },
  },

  ru: {
    privacy: {
      title: 'Конфиденциальность - Groundline',
      heading: 'Что Groundline хранит, куда это уходит и как всё удалить',
      description:
        'Понятное описание приватности демо Groundline: что собирается (email, загруженные документы, вопросы), где хранится и какие внешние сервисы это получают.',
      lede: 'Коротко: Groundline хранит ваш адрес почты, загруженные вами документы, а также вопросы и ответы вашего аккаунта. Текст документов уходит во внешние модели, чтобы отвечать на вопросы. Удаление аккаунта убирает всё это сразу.',
      sections: [
        {
          h: 'Что собирается',
          list: [
            ['Адрес электронной почты', 'единственный идентификатор аккаунта. Пароля нет, профиля нет, слежки по другим сайтам нет.'],
            ['Загруженные документы', 'хранятся как извлечённый текст, нарезанный на фрагменты, у каждого - числовое представление смысла для поиска.'],
            ['Вопросы и ответы', 'остаются в истории и в кэше, чтобы повторный вопрос не оплачивался заново.'],
            ['Технические записи', 'время и количество токенов по каждому запросу, IP-адрес при запросе кода входа (чтобы ограничивать злоупотребления), серверные логи.'],
          ],
        },
        {
          h: 'Где это хранится',
          body: 'В одной базе Postgres на Supabase в ЕС. Каждая строка привязана к аккаунту, и то, что один аккаунт не прочитает строки другого, обеспечивает сама база, а не только код приложения.',
        },
        {
          h: 'Какой сервис что получает',
          table: [
            ['Render', 'На нём работает бэкенд, поэтому через него проходит каждый запрос: вопросы, загруженные файлы и адрес почты. В его логах лежат технические записи, перечисленные выше.'],
            ['Vercel', 'Отдаёт страницы, поэтому видит IP-адрес и браузер каждого визита. Без текста документов и без адреса почты.'],
            ['Groq', 'Ваш вопрос и отобранные фрагменты документов. Пишет ответ.'],
            ['OpenRouter и TypeSafe', 'Ваш вопрос, отобранные фрагменты документов, ответ и прошлый вопрос, к которому относится ответ из кэша. OpenRouter передаёт их модели Jev от TypeSafe: она проверяет, хватает ли фрагментов для ответа, тот ли это вопрос, что уже есть в кэше, и подтверждают ли источники ответ. Jev возвращает вероятности, а не текст.'],
            ['DeepInfra', 'Текст фрагментов документов и текст вопросов. Превращает текст в векторы, на которых работает поиск.'],
            ['Pinecone', 'Ваш вопрос и фрагменты-кандидаты. Определяет, в каких из них действительно есть ответ.'],
            ['LangFuse', 'Трассировку запроса: вопрос, ответ и использованные фрагменты - для отладки и анализа расходов.'],
            ['Resend', 'Ваш адрес почты и шестизначный код входа.'],
            ['Cloudflare Turnstile', 'Токен проверки и ваш IP-адрес, чтобы боты не заказывали коды входа.'],
            ['Upstash', 'Только счётчики: сколько кодов запросил IP, сколько потоков держит аккаунт. Текста документов там нет.'],
            ['Vercel Analytics и Speed Insights', 'Просмотры страниц и время их загрузки, в агрегированном виде. Без кук, без идентификатора, который следует за вами на другие сайты, без текста документов и без адреса почты.'],
          ],
          after:
            'Если развернуть Groundline у себя с локальными моделями, текст документов не покидает вашу инфраструктуру; в размещённом демо - покидает.',
        },
        {
          h: 'Сколько это хранится',
          body: 'Документы, история и кэш живут, пока вы их не удалите или не удалите аккаунт. Код входа истекает через 10 минут, а запись о запросе кода (адрес и IP) удаляется через семь дней. Сессия - семь дней; выход из аккаунта завершает все его сессии. LangFuse на бесплатном тарифе хранит трассировки 30 дней.',
        },
        {
          h: 'Как удалить',
          body: 'На экране «Документы» две кнопки: одна очищает документы, кэш и историю, вторая удаляет аккаунт целиком. Удаление немедленное и каскадное по всем таблицам - без «корзины» и без восстановления. То же доступно через API: DELETE /me.',
        },
        {
          h: 'Чего здесь нет',
          list: [
            ['Ни рекламы, ни сторонних трекеров', 'лендинг и приложение считают просмотры страниц и время загрузки через Vercel - без кук и без профиля, который следует за вами по другим сайтам. Больше ничего не грузится.'],
            ['Данные не продаются и не передаются', 'уходят только в перечисленные сервисы и только чтобы ответить на ваш вопрос.'],
            ['Обучения на ваших документах нет', 'провайдеры используются через их API; их собственные условия хранения смотрите у них.'],
          ],
        },
        {
          h: 'Связь',
          body: 'Контролёр данных: Антон Минин-Барановский (физическое лицо). Обращения по вопросам персональных данных: hi@antonmb.com.',
          after:
            'Напишите, если хотите обсудить продукт, инженерную задачу, консультацию или сотрудничество. Открыт и к разговорам о книге: интервью, публикации, выступления.',
          links: [
            ['hi@antonmb.com', 'mailto:hi@antonmb.com'],
            ['Telegram', 'https://t.me/AntonMinin'],
            ['LinkedIn', 'https://www.linkedin.com/in/antonmininbaranovskii/'],
          ],
        },
      ],
    },
    terms: {
      title: 'Условия - Groundline',
      heading: 'Условия использования',
      description: 'Условия демо Groundline: демонстрационный сервис «как есть», с квотами на аккаунт и без гарантий доступности.',
      lede: 'Коротко: это демонстрационный проект, а не продукт, на который стоит полагаться. Он может тормозить, лежать и терять данные. Не загружайте сюда ничего конфиденциального.',
      sections: [
        {
          h: 'Что это такое',
          body: 'Groundline - личный проект-портфолио, который отвечает на вопросы по загруженным вами документам. Работает на бесплатных тарифах внешних сервисов и предоставляется бесплатно.',
        },
        {
          h: 'Без гарантий',
          body: 'Сервис предоставляется «как есть», без каких-либо гарантий. Нет обязательств по доступности, нет обязательств по поддержке, нет резервных копий ваших данных. Бэкенд засыпает при простое, поэтому первый запрос после паузы может занять до минуты. Квоты внешних провайдеров могут закончиться, и запросы будут отклоняться до сброса.',
        },
        {
          h: 'Не загружайте конфиденциальное',
          body: 'Текст документов уходит во внешние модельные сервисы, перечисленные в разделе о конфиденциальности. Не загружайте персональные данные других людей, коммерческую тайну, пароли и ключи, медицинские или финансовые записи и всё, чем вы не вправе поделиться с этими провайдерами.',
        },
        {
          h: 'Лимиты',
          list: [
            ['50 вопросов на аккаунт в сутки', 'ответы из кэша бесплатны и в счёт не идут.'],
            ['Не чаще одного вопроса в 15 секунд', 'демо работает на одном небольшом инстансе.'],
            ['1 документ на аккаунт, до 0,3 МБ', 'удалите его, чтобы загрузить другой; 200 МБ хранилища на аккаунт.'],
            ['3 кода входа на адрес в сутки', 'плюс ограничение по IP-адресу.'],
            ['Только PDF, TXT и MD', 'остальные форматы отклоняются.'],
          ],
        },
        {
          h: 'Допустимое использование',
          body: 'Не используйте сервис для нарушения закона, для загрузки контента, прав на который у вас нет, для атак на инфраструктуру и для обхода квот. Аккаунты, которые этим занимаются, удаляются без предупреждения.',
        },
        {
          h: 'Ответы - не консультация',
          body: 'Ответы генерирует языковая модель по вашим документам, и они могут быть неточными или неполными. У каждого ответа указаны использованные фрагменты - проверяйте их, прежде чем действовать. Это не юридическая, не медицинская и не финансовая консультация.',
        },
        {
          h: 'Изменения и закрытие',
          body: 'Сервис может измениться или исчезнуть в любой момент, включая безвозвратное удаление хранимых данных. Сохраняйте у себя всё, что вам важно.',
        },
        {
          h: 'Кто этим занимается',
          body: 'Контролёр данных: Антон Минин-Барановский (физическое лицо). Обращения по вопросам персональных данных: hi@antonmb.com.',
          links: [
            ['hi@antonmb.com', 'mailto:hi@antonmb.com'],
            ['Telegram', 'https://t.me/AntonMinin'],
            ['LinkedIn', 'https://www.linkedin.com/in/antonmininbaranovskii/'],
          ],
        },
      ],
    },
  },
}
