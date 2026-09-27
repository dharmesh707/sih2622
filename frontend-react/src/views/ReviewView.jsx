import { useCallback, useEffect, useState } from 'react';
import Panel from '../components/Panel';
import Spinner from '../components/Spinner';
import CandidateList from '../components/CandidateList';
import ConfirmResult from '../components/ConfirmResult';
import DelayCauseSelect from '../components/DelayCauseSelect';
import { api, jsonOptions } from '../api';

function ReviewCard({ event, busy, onConfirm, onReject }) {
  const [selected, setSelected] = useState(null);
  const [comment, setComment] = useState('');
  const [delayCause, setDelayCause] = useState(null);
  const unmatched = event.decision === 'UNMATCHED';
  const suggested = event.activity_id;
  const selectedCode = event.candidates.find((c) => c.activity_id === selected)?.activity_code;

  return (
    <article className={`review-card ${unmatched ? 'unmatched' : ''}`}>
      <div className="eyebrow">{event.decision} · event #{event.id}</div>
      <pre>{event.source_text}</pre>
      <p className="muted">
        Why {unmatched ? 'unmatched' : 'review'}: {event.reason || '—'} · top {Number(event.top_score || 0).toFixed(3)} · runner-up {Number(event.second_score || 0).toFixed(3)} · margin {Number(event.margin || 0).toFixed(3)}
      </p>
      {unmatched && (
        <p className="warning-note">
          The observation is preserved with no schedule link. The candidates below scored too low to be trusted.
          Associate it only if you know which activity it belongs to.
        </p>
      )}
      <CandidateList candidates={event.candidates} selectedId={selected} onSelect={setSelected} name={`event-${event.id}`} />
      <div className="review-actions">
        <input className="comment" aria-label="Decision comment" placeholder="Comment / delay notes" value={comment} onChange={(e) => setComment(e.target.value)} />
        <DelayCauseSelect value={delayCause} onChange={setDelayCause} />
        <button className="primary compact" type="button" disabled={!selected || busy} onClick={() => onConfirm(event, selected, comment, delayCause)}>
          {busy ? <Spinner label="Saving..." /> : !selected ? 'Select an activity' : unmatched ? `Associate manually with ${selectedCode}` : selected === suggested ? `Confirm ${selectedCode}` : `Reassign to ${selectedCode}`}
        </button>
        <button className="secondary" type="button" disabled={busy} onClick={() => onReject(event, comment)}>Reject</button>
      </div>
    </article>
  );
}

export default function ReviewView({ projectId, setError, refreshMetrics }) {
  const [queue, setQueue] = useState([]);
  const [awaiting, setAwaiting] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [confirmed, setConfirmed] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [items, pending] = await Promise.all([api(`/review-queue?project_id=${projectId}`), api(`/awaiting-confirmation?project_id=${projectId}`)]);
      const withCandidates = (list) => Promise.all(list.map(async (event) => ({ ...event, candidates: await api(`/events/${event.id}/candidates`) })));
      setQueue(await withCandidates(items));
      setAwaiting(await withCandidates(pending));
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [projectId, setError]);

  useEffect(() => { load(); }, [load]);

  async function confirm(event, activityId, comment, delayCause) {
    setBusyId(event.id);
    try {
      setConfirmed(await api(`/events/${event.id}/confirm`, jsonOptions({ activity_id: activityId, actor: 'planner', comment, delay_cause: delayCause })));
      await load();
      await refreshMetrics();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusyId(null);
    }
  }

  async function reject(event, comment) {
    setBusyId(event.id);
    try {
      await api(`/events/${event.id}/reject`, jsonOptions({ actor: 'planner', comment }));
      await load();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusyId(null);
    }
  }

  async function sendToReview(event) {
    setBusyId(event.id);
    try {
      await api(`/events/${event.id}/send-to-review`, jsonOptions({ actor: 'planner' }));
      await load();
    } catch (error) {
      setError(error.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="view-enter">
      <div className="eyebrow">DECISION DESK / 02</div>
      <h1>Review only what the plan cannot know.</h1>
      <p className="lede">A close second place is ambiguity, not permission to guess. Pick the activity explicitly.</p>

      <ConfirmResult result={confirmed} />

      {!loading && awaiting.length > 0 && (
        <section className="awaiting" aria-label="Awaiting confirmation">
          <h2>Awaiting confirmation <span className="muted">· {awaiting.length} confident match{awaiting.length === 1 ? '' : 'es'} not yet confirmed</span></h2>
          <div className="review-list">
            {awaiting.map((event) => (
              <article className="review-card auto" key={event.id}>
                <div className="eyebrow">AUTO_MATCHED · event #{event.id} · project #{event.project_id} · {event.source} · {event.submitted_at}</div>
                <pre>{event.source_text}</pre>
                <p className="muted">Proposed <strong>{event.activity_code}</strong> · {event.description} · {event.reason} · progress {event.progress ?? '—'}%</p>
                <CandidateList candidates={event.candidates} limit={3} />
                <div className="review-actions">
                  <button className="primary compact" type="button" disabled={busyId === event.id} onClick={() => confirm(event, event.activity_id, 'confirmed from awaiting-confirmation list', null)}>
                    {busyId === event.id ? <Spinner label="Saving..." /> : `Confirm ${event.activity_code}`}
                  </button>
                  <button className="secondary" type="button" disabled={busyId === event.id} onClick={() => sendToReview(event)}>Send to review</button>
                  <button className="secondary" type="button" disabled={busyId === event.id} onClick={() => reject(event, '')}>Reject</button>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {loading ? <Spinner label="Loading review queue..." /> : !queue.length ? (
        <Panel><h2>Queue clear</h2><p className="muted">New ambiguous or unmatched observations for project #{projectId} will appear here.</p></Panel>
      ) : (
        <div className="review-list">
          {queue.map((event) => <ReviewCard key={event.id} event={event} busy={busyId === event.id} onConfirm={confirm} onReject={reject} />)}
        </div>
      )}
    </div>
  );
}
