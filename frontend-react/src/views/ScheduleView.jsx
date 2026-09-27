import { useCallback, useEffect, useMemo, useState } from 'react';
import Panel from '../components/Panel';
import Spinner from '../components/Spinner';
import { api } from '../api';

const DAY = 86_400_000;
const toDay = (iso) => (iso ? Math.floor(Date.parse(`${iso.slice(0, 10)}T00:00:00Z`) / DAY) : null);
const todayDay = () => toDay(new Date().toLocaleDateString('en-CA')); // local date, same as the backend's date.today()
const label = (day) => new Date(day * DAY).toISOString().slice(5, 10);

export default function ScheduleView({ projectId, setError }) {
  const [activities, setActivities] = useState([]);
  const [deps, setDeps] = useState([]);
  const [loading, setLoading] = useState(true);
  const [recomputing, setRecomputing] = useState(false);
  const [onlyCritical, setOnlyCritical] = useState(false);

  const load = useCallback(async () => {
    try {
      const [rows, edges] = await Promise.all([api(`/projects/${projectId}/activities`), api(`/projects/${projectId}/dependencies`)]);
      setActivities(rows);
      setDeps(edges);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [projectId, setError]);

  useEffect(() => { load(); }, [load]);

  async function recompute() {
    setRecomputing(true);
    try {
      await api(`/projects/${projectId}/recompute`, { method: 'POST' });
      await load();
    } catch (error) {
      setError(error.message);
    } finally {
      setRecomputing(false);
    }
  }

  const predecessors = useMemo(() => {
    const map = {};
    deps.forEach((d) => { (map[d.successor_id] ||= []).push(`${d.predecessor_code}${d.dependency_type !== 'FS' || d.lag ? ` ${d.dependency_type}${d.lag ? `+${d.lag}` : ''}` : ''}`); });
    return map;
  }, [deps]);

  const today = todayDay();
  const range = useMemo(() => {
    const days = activities.flatMap((a) => [a.planned_start, a.planned_finish, a.actual_start, a.actual_finish].map(toDay)).filter((d) => d != null);
    if (!days.length) return null;
    const start = Math.min(...days, today) - 1;
    const end = Math.max(...days, today) + 2;
    return { start, span: end - start };
  }, [activities, today]);

  const pct = (day) => `${((day - range.start) / range.span) * 100}%`;
  const width = (from, to) => `${((to - from + 1) / range.span) * 100}%`;
  const rows = onlyCritical ? activities.filter((a) => a.critical) : activities;
  const ticks = range ? Array.from({ length: Math.ceil(range.span / 7) }, (_, i) => range.start + i * 7) : [];

  return (
    <div className="view-enter">
      <div className="eyebrow">SCHEDULE GRAPH / 03</div>
      <div className="title-row">
        <div><h1>Baseline, actuals, consequence.</h1><p className="lede">Planned bars, actual bars and progress from the live schedule. Critical work and float come from deterministic CPM over the stored dependency graph.</p></div>
        <div className="review-actions">
          <label className="muted"><input type="checkbox" checked={onlyCritical} onChange={(e) => setOnlyCritical(e.target.checked)} /> critical only</label>
          <button className="secondary" type="button" disabled={recomputing} onClick={recompute}>{recomputing ? <Spinner label="Recomputing..." /> : 'Recompute CPM'}</button>
        </div>
      </div>
      <Panel>
        <div className="gantt-legend muted">
          <span><i className="lg planned" /> planned</span><span><i className="lg planned critical" /> planned · critical</span>
          <span><i className="lg actual" /> actual</span><span><i className="lg today" /> today</span>
          <span>{activities.length} activities · {deps.length} dependencies · {activities.filter((a) => a.at_risk).length} at risk</span>
        </div>
        {loading ? <Spinner label="Loading schedule..." /> : !range ? <p className="muted">No activities in project #{projectId}. Import a schedule from Ingest.</p> : (
          <div className="gantt" role="table" aria-label="Gantt chart">
            <div className="gantt-row gantt-head" role="row">
              <div className="gantt-label" role="columnheader">Activity · after</div>
              <div className="gantt-meta" role="columnheader">Progress · float</div>
              <div className="gantt-track" role="columnheader">
                {ticks.map((d) => <span key={d} className="tick" style={{ left: pct(d) }}>{label(d)}</span>)}
              </div>
            </div>
            {rows.map((a) => {
              const ps = toDay(a.planned_start); const pf = toDay(a.planned_finish);
              const as = toDay(a.actual_start); const af = toDay(a.actual_finish) ?? (as != null ? today : null);
              return (
                <div className={`gantt-row ${a.at_risk ? 'risk' : ''}`} role="row" key={a.id} title={`${a.activity_code}: planned ${a.planned_start} → ${a.planned_finish}; actual ${a.actual_start || '—'} → ${a.actual_finish || '—'}; forecast finish ${a.early_finish || '—'}${a.at_risk_reason ? `; AT RISK: ${a.at_risk_reason}` : ''}`}>
                  <div className="gantt-label" role="cell">
                    <strong className={a.critical ? 'critical' : ''}>{a.activity_code}</strong> <span className="muted">{a.description}</span>
                    <small className="muted">{predecessors[a.id]?.length ? `after ${predecessors[a.id].join(', ')}` : 'no predecessor'}</small>
                  </div>
                  <div className="gantt-meta" role="cell">
                    {Number(a.percent_complete || 0)}% · {a.total_float == null ? '—' : `${Number(a.total_float).toFixed(1)}d`}
                    <small className="state">{a.at_risk ? 'AT RISK' : a.status}</small>
                    {a.early_finish && !a.actual_finish && <small className="muted">fcst {a.early_finish.slice(5)}</small>}
                  </div>
                  <div className="gantt-track" role="cell">
                    <span className="today-line" style={{ left: pct(today) }} />
                    {ps != null && pf != null && <span className={`bar planned ${a.critical ? 'critical' : ''}`} style={{ left: pct(ps), width: width(ps, pf) }} />}
                    {as != null && <span className="bar actual" style={{ left: pct(as), width: width(as, af) }}><i style={{ width: `${Math.min(100, Number(a.percent_complete || 0))}%` }} /></span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}
