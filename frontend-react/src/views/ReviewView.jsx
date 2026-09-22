import { useCallback, useEffect, useState } from 'react';
import Panel from '../components/Panel';
import StatusPill from '../components/StatusPill';
import Spinner from '../components/Spinner';
import { api, jsonOptions } from '../api';

function scoreEntries(top) {
  return [
    ['ID', top?.score_id],
    ['LEXICAL', top?.score_lexical],
    ['SEMANTIC', top?.score_semantic],
    ['CONTEXT', top?.score_context],
  ];
}

export default function ReviewView({ setError, refreshMetrics }) {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [diff, setDiff] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const items = await api('/review-queue');
      const enriched = await Promise.all(items.map(async (event) => ({
        ...event,
        candidates: await api(`/events/${event.id}/candidates`),
      })));
      setQueue(enriched);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [setError]);

  useEffect(() => { load(); }, [load]);

  async function confirm(event) {
    const top = event.candidates?.[0];
    if (!top) return;
    setBusyId(event.id);
    try {
      const response = await api(`/events/${event.id}/confirm`, jsonOptions({ activity_id: Number(top.activity_id), actor: 'planner' }));
      setDiff(response);
      await load();
      await refreshMetrics();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusyId(null);
    }
  }

  async function reject(event) {
    setBusyId(event.id);
    try {
      await api(`/events/${event.id}/reject`, jsonOptions({ actor: 'planner' }));
      await load();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <><div className="eyebrow">DECISION DESK / 02</div><h1>Review only what the plan cannot know.</h1><p className="lede"><Spinner label="Loading review queue..." /></p></>;

  return (
    <div className="view-enter">
      <div className="eyebrow">DECISION DESK / 02</div>
      <h1>Review only what the plan cannot know.</h1>
      <p className="lede">A close second place is ambiguity, not permission to guess.</p>

      {diff && (
        <Panel className="diff-panel">
          <div className="panel-head">
            <div><span className="kicker">POST-CONFIRM IMPACT</span><h2>What changed in the schedule?</h2></div>
            <StatusPill tone={diff.critical_path_changed ? 'red' : 'teal'}>{diff.critical_path_changed ? 'CRITICAL PATH CHANGED' : 'PATH STABLE'}</StatusPill>
          </div>
          <div className="diff-grid">
            <div><span>Progress</span><strong>{diff.old?.percent_complete}% → {diff.new?.percent_complete}%</strong></div>
            <div><span>Status</span><strong>{diff.old?.status} → {diff.new?.status}</strong></div>
            <div><span>Project finish</span><strong>{Number(diff.before?.project_finish || 0).toFixed(1)} → {Number(diff.after?.project_finish || 0).toFixed(1)}</strong></div>
          </div>
          <div className="entered-left">
            <div><span className="muted">Entered critical path</span><strong>{diff.after?.critical?.filter((id) => !diff.before?.critical?.includes(id)).join(', ') || 'None'}</strong></div>
            <div><span className="muted">Left critical path</span><strong>{diff.before?.critical?.filter((id) => !diff.after?.critical?.includes(id)).join(', ') || 'None'}</strong></div>
          </div>
        </Panel>
      )}

      {!queue.length ? (
        <Panel><h2>Queue clear</h2><p className="muted">New ambiguous or unmatched observations will appear here.</p></Panel>
      ) : (
        <div className="review-list">
          {queue.map((event) => {
            const top = event.candidates?.[0];
            return (
              <article className="review-card" key={event.id}>
                <div className="eyebrow">{event.decision} · event #{event.id}</div>
                <h3>{event.activity_terms}</h3>
                <pre>{event.source_text}</pre>
                <div className="score-grid">
                  {scoreEntries(top).map(([name, value]) => {
                    const score = Number(value || 0);
                    return <div className="score" key={name}><span>{name}</span><strong>{score.toFixed(2)}</strong><div className="bar"><i style={{ width: `${Math.min(100, score * 100)}%` }} /></div></div>;
                  })}
                </div>
                <p className="muted">Top: {Number(event.top_score || 0).toFixed(3)} · runner-up: {Number(event.second_score || 0).toFixed(3)} · margin: {Number(event.margin || 0).toFixed(3)}</p>
                {top ? <>
                  <div className="candidate-row">
                    <div><strong>{top.activity_code} · {top.description}</strong><span className="muted"> / {top.location || '—'} / {top.wbs_path || '—'}</span></div>
                    <span className="match-chip">rank #1</span>
                  </div>
                  <div className="mapped-terms">Mapped terms: {(top.evidence?.mapped_terms || []).map((item) => `${item.field_term} → ${item.canonical_term}`).join(', ') || 'none'}</div>
                </> : <p className="muted">No candidate details available.</p>}
                <div className="review-actions">
                  <button className="primary compact" type="button" disabled={!top || busyId === event.id} onClick={() => confirm(event)}>
                    {busyId === event.id ? <Spinner label="Saving..." /> : 'Approve top candidate'}
                  </button>
                  <button className="secondary" type="button" disabled={busyId === event.id} onClick={() => reject(event)}>Reject</button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
