const fmt = (value) => (value == null ? '—' : Number(value).toFixed(2));

export default function CandidateList({ candidates, selectedId, onSelect, limit = 5, name }) {
  const rows = (candidates || []).slice(0, limit);
  if (!rows.length) return <p className="muted">No candidate activities in this project.</p>;
  const reranked = rows.some((c) => c.evidence?.reranker_probability != null);

  return (
    <div className="table-wrap">
      <table className="candidate-table">
        <thead>
          <tr>
            {onSelect && <th aria-label="Select" />}
            <th>#</th><th>Activity</th><th>Discipline / location</th>
            <th>ID</th><th>Lex</th><th>Sem</th><th>Ctx</th><th>Total</th>
            {reranked && <th>Reranker</th>}
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.id} className={selectedId === c.activity_id ? 'selected' : ''} onClick={onSelect ? () => onSelect(c.activity_id) : undefined}>
              {onSelect && (
                <td>
                  <input
                    type="radio"
                    name={name}
                    aria-label={`Select ${c.activity_code}`}
                    checked={selectedId === c.activity_id}
                    onChange={() => onSelect(c.activity_id)}
                  />
                </td>
              )}
              <td>{c.rank}</td>
              <td><strong>{c.activity_code}</strong>{c.evidence?.completed_activity && <span className="done-chip">already complete</span>}<br /><span className="muted">{c.description}</span></td>
              <td>{c.discipline}<br /><span className="muted">{c.location || '—'}</span></td>
              <td>{fmt(c.score_id)}</td>
              <td>{fmt(c.score_lexical)}</td>
              <td>{fmt(c.score_semantic)}</td>
              <td>{fmt(c.score_context)}</td>
              <td><strong>{Number(c.fused_score).toFixed(3)}</strong>{c.temporal_factor !== 1 && <><br /><span className="muted">×{c.temporal_factor} date</span></>}{c.evidence?.status_factor && <><br /><span className="muted">×{c.evidence.status_factor} done</span></>}</td>
              {reranked && <td>{c.evidence?.reranker_probability != null ? `p=${Number(c.evidence.reranker_probability).toFixed(3)}` : '—'}</td>}
              <td className="muted">
                {(c.evidence?.mapped_terms || []).map((t) => `${t.field_term} → ${t.canonical_term}`).join(', ') || 'no term mapping'}
                <br />{c.evidence?.matching_stage || ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
