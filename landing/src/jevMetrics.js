const HONEST_MIN_UNANSWERABLE = 5
const DASH = '—'

const isNumber = (value) => typeof value === 'number' && Number.isFinite(value)
const fixed = (value, digits) => (isNumber(value) ? value.toFixed(digits) : null)
const whole = (value) => (isNumber(value) ? Math.round(value).toLocaleString('en-US') : null)
const seconds = (ms, digits = 1) => (isNumber(ms) ? (ms / 1000).toFixed(digits) : null)
const percent = (share) => (isNumber(share) ? `${Math.round(share * 100)}%` : null)
const fill = (template, values) => template.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? '')
const when = (iso, lang) =>
  new Date(iso).toLocaleString(lang, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }) + ' UTC'

export const liveColumns = (live, copy) => {
  const baseline = live?.baseline?.average
  const average = live?.jev?.average
  const last = live?.jev?.last
  return [
    baseline && {
      answer_ms: seconds(baseline.answer_ms),
      llm_calls: fixed(baseline.llm_calls, 1),
      llm_tokens: whole(baseline.llm_tokens),
      cache_hit: percent(baseline.cache_hit),
      jev_ms: DASH,
      supported: DASH,
      jev_cost_usd: DASH,
    },
    average && {
      answer_ms: seconds(average.answer_ms),
      llm_calls: fixed(average.llm_calls, 1),
      llm_tokens: whole(average.llm_tokens),
      cache_hit: percent(average.cache_hit),
      jev_ms: seconds(average.jev_ms, 2),
      supported: percent(average.supported),
      jev_cost_usd: fixed(average.jev_cost_usd, 5),
    },
    last && {
      answer_ms: seconds(last.answer_ms),
      llm_calls: String(last.llm_calls),
      llm_tokens: whole(last.llm_tokens),
      cache_hit: last.cache_hit ? copy.yes : copy.no,
      jev_ms: seconds(last.jev_ms, 2),
      supported: last.grounding ? copy.verdicts[last.grounding] || last.grounding : DASH,
      jev_cost_usd: DASH,
    },
  ]
}

const perQuestion = (all, field) => (all?.questions ? all[field] / all.questions : null)

export const evalColumns = (status) => {
  const runs = Object.fromEntries((status?.runs || []).map((run) => [run.label, run]))
  const cells = (run) => {
    const all = run?.summary?.all
    if (!all) return null
    return {
      faithfulness: fixed(all.faithfulness, 2),
      answer_correctness: fixed(all.answer_correctness, 2),
      context_precision: fixed(all.context_precision, 2),
      context_recall: fixed(all.context_recall, 2),
      llm_calls: fixed(perQuestion(all, 'groq_calls'), 1),
      llm_tokens: whole(perQuestion(all, 'groq_tokens')),
    }
  }
  const scored = [runs.jev, runs.jev_first].map((run) => run?.unanswerable_scored ?? 0)
  return {
    runs,
    cells: Object.fromEntries(Object.entries(runs).map(([label, run]) => [label, cells(run)])),
    honest: (runs.baseline?.unanswerable_scored ?? 0) >= HONEST_MIN_UNANSWERABLE && Math.max(...scored) >= HONEST_MIN_UNANSWERABLE,
  }
}

const fetchJson = async (url) => {
  try {
    const response = await fetch(url)
    return response.ok ? await response.json() : null
  } catch {
    return null
  }
}

const put = (cell, value) => {
  if (value == null) return
  cell.textContent = value
  cell.classList.remove('pending')
}

export async function showJevMetrics(container) {
  if (!container) return
  const copy = JSON.parse(container.dataset.copy)
  const lang = document.documentElement.lang || 'en'
  const [live, status] = await Promise.all([fetchJson(container.dataset.liveUrl), fetchJson(container.dataset.statusUrl)])

  const columns = liveColumns(live, copy)
  if (columns.some(Boolean)) {
    container.querySelectorAll('td[data-live-key]').forEach((cell) => {
      put(cell, columns[Number(cell.dataset.column)]?.[cell.dataset.liveKey])
    })
    const lastAt = live.jev?.last?.at || live.baseline?.last?.at
    container.querySelector('[data-live-note]').textContent = fill(copy.liveNote, {
      baseline: live.baseline?.questions ?? 0,
      jev: live.jev?.questions ?? 0,
      date: lastAt ? when(lastAt, lang) : DASH,
    })
    container.querySelector('[data-live]').hidden = false
  }

  const measured = evalColumns(status)
  const labels = Object.keys(measured.runs)
  if (labels.length) {
    container.querySelectorAll('td[data-eval-key]').forEach((cell) => {
      put(cell, measured.cells[cell.dataset.run]?.[cell.dataset.evalKey])
    })
    const progress = labels
      .filter((label) => copy.evalColumns[label])
      .map((label) => `${copy.evalColumns[label]} ${measured.runs[label].done}/${measured.runs[label].total ?? 29}`)
      .join(', ')
    const updated = labels.map((label) => measured.runs[label].updated_at).sort().at(-1)
    container.querySelector('[data-eval-note]').textContent = fill(copy.evalNote, { progress, date: when(updated, lang) })
    container.querySelector('[data-eval]').hidden = false
  }
  if (measured.honest) document.querySelectorAll('[data-needs-results]').forEach((item) => (item.hidden = false))
}
