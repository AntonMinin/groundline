export default function StatsBar({ stats }) {
  if (!stats) return null
  const { cache_hit_rate, cache_hits, total_queries, tokens_saved, usage, limits } = stats
  return (
    <section className="stats">
      <div>
        <span className="value">{(cache_hit_rate * 100).toFixed(1)}%</span>
        <span className="label">cache hit rate ({cache_hits}/{total_queries})</span>
      </div>
      <div>
        <span className="value">{tokens_saved.toLocaleString()}</span>
        <span className="label">tokens saved</span>
      </div>
      <div>
        <span className="value">{usage.queries_last_24h}/{limits.queries_per_day}</span>
        <span className="label">LLM queries today</span>
      </div>
      <div>
        <span className="value">{usage.documents}/{limits.max_documents}</span>
        <span className="label">documents</span>
      </div>
    </section>
  )
}
