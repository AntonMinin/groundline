const HONEST_MIN_UNANSWERABLE = 5

const fixed = (value, digits) => (typeof value === 'number' ? value.toFixed(digits) : null)
const whole = (value) => (typeof value === 'number' ? Math.round(value).toLocaleString('en-US') : null)
const perQuestion = (run, field) => (run?.summary?.all?.questions ? run.summary.all[field] / run.summary.all.questions : null)

const cells = (run) => {
  if (!run) return {}
  const all = run.summary?.all || {}
  const nodes = run.summary?.node_latency || {}
  const pairs = run.cache_pairs || {}
  return {
    faithfulness: fixed(all.faithfulness, 2),
    answer_correctness: fixed(all.answer_correctness, 2),
    context_precision: fixed(all.context_precision, 2),
    context_recall: fixed(all.context_recall, 2),
    groq_calls: fixed(perQuestion(run, 'groq_calls'), 1),
    groq_tokens: whole(perQuestion(run, 'groq_tokens')),
    done_median: whole(all.done_ms_median),
    check_cache: whole(nodes.check_cache?.median_ms),
    jev_sufficiency: run.jev ? whole(nodes.jev_sufficiency?.median_ms) : '—',
    check_sufficiency: whole(nodes.check_sufficiency?.median_ms),
    generate_answer: whole(nodes.generate_answer?.median_ms),
    cache_pairs: pairs.total ? `${pairs.correct}/${pairs.total}` : null,
    wrong_hits: pairs.total ? String(pairs.wrong_hits) : null,
    jev_cost: run.jev ? fixed(run.done ? (run.jev_cost_usd / run.done) * 100 : null, 3) : '—',
  }
}

export const readStatus = (status) => {
  const runs = status?.runs || []
  const baseline = runs.find((run) => run.jev === false)
  const jev = runs.find((run) => run.jev === true)
  const updated = runs.map((run) => run.updated_at).sort().at(-1)
  return {
    baseline,
    jev,
    updated,
    columns: [cells(baseline), cells(jev)],
    honest: Boolean(baseline && jev) && Math.min(baseline.unanswerable_scored, jev.unanswerable_scored) >= HONEST_MIN_UNANSWERABLE,
  }
}

const fill = (template, values) => template.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? '')

export async function showEvalStatus(container) {
  if (!container || container.dataset.measured) return
  let status
  try {
    const response = await fetch(container.dataset.statusUrl)
    if (!response.ok) return
    status = readStatus(await response.json())
  } catch {
    return
  }
  if (!status.baseline && !status.jev) return
  container.querySelectorAll('td[data-key]').forEach((cell) => {
    const value = status.columns[Number(cell.dataset.column)][cell.dataset.key]
    if (value == null) return
    cell.textContent = value
    cell.classList.remove('pending')
  })
  const note = container.querySelector('[data-jev-preliminary]')
  const lang = document.documentElement.lang || 'en'
  note.textContent = fill(note.dataset.template, {
    total: status.baseline?.total ?? status.jev?.total ?? 29,
    baseline: status.baseline?.done ?? 0,
    jev: status.jev?.done ?? 0,
    date: new Date(status.updated).toLocaleString(lang, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }) + ' UTC',
  })
  note.hidden = false
  container.hidden = false
  if (status.honest) document.querySelectorAll('[data-needs-results]').forEach((item) => (item.hidden = false))
}
