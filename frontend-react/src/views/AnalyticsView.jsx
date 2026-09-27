import { useCallback, useEffect, useState } from 'react';
import Panel from '../components/Panel';
import Spinner from '../components/Spinner';
import { api } from '../api';

const signed = (v) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v}d`);

export default function AnalyticsView({ projectId, setError }) {
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    try {
      const q = `?project_id=${projectId}`;
      const [variance, productivity, delays, wbs] = await Promise.all([
        api(`/analytics/variance${q}`), api(`/analytics/discipline-productivity${q}`), api(`/analytics/delay-causes${q}`), api(`/analytics/wbs-progress${q}`),
      ]);
      setData({ variance, productivity, delays, wbs });
    } catch (error) {
      setError(error.message);
    }
  }, [projectId, setError]);

  useEffect(() => { load(); }, [load]);

  if (!data) return <><div className="eyebrow">SIGNALS / 04</div><h1>Progress patterns worth acting on.</h1><Spinner label="Loading analytics..." /></>;
  const { variance, productivity, delays, wbs } = data;
  const s = variance.summary;
  const maxDelay = Math.max(1, ...delays.counts.map((d) => d.count));

  return (
    <div className="view-enter">
      <div className="eyebrow">SIGNALS / 04</div>
      <h1>Progress patterns worth acting on.</h1>
      <p className="lede">Computed from confirmed actual dates in project #{projectId}. Empty means no actuals yet, never a placeholder number.</p>

      <Panel className="wide-panel">
        <div className="panel-head"><div><h2>Planned vs actual</h2><span className="muted">days · positive = late / longer than planned</span></div></div>
        <div className="diff-grid">
          <div><span>Avg start variance</span><strong>{signed(s.avg_start_variance)}</strong></div>
          <div><span>Avg finish variance</span><strong>{signed(s.avg_finish_variance)}</strong></div>
          <div><span>Avg duration variance</span><strong>{signed(s.avg_duration_variance)}</strong><small className="muted"> {s.completed} completed / {s.with_actual_start} started</small></div>
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Activity</th><th>Planned</th><th>Actual</th><th>Start var.</th><th>Finish var.</th><th>Duration (plan → actual)</th></tr></thead>
            <tbody>
              {variance.activities.map((a) => (
                <tr key={a.activity_code}>
                  <td><strong>{a.activity_code}</strong><br /><span className="muted">{a.description}</span></td>
                  <td>{a.planned_start} → {a.planned_finish}</td>
                  <td>{a.actual_start} → {a.actual_finish || 'in progress'}</td>
                  <td>{signed(a.start_variance)}</td>
                  <td>{signed(a.finish_variance)}</td>
                  <td>{a.planned_duration}d → {a.actual_duration == null ? '—' : `${a.actual_duration}d (${signed(a.duration_variance)})`}</td>
                </tr>
              ))}
              {!variance.activities.length && <tr><td colSpan="6">No activity has an actual start yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="analytics-grid">
        <Panel>
          <div className="panel-head"><div><h2>Productivity</h2><span className="muted">discipline · activity type</span></div></div>
          <div className="table-wrap">
            <table className="compact-table">
              <thead><tr><th>Discipline / type</th><th>Progress</th><th>Done</th><th>Duration plan / actual</th></tr></thead>
              <tbody>
                {productivity.map((row) => (
                  <tr key={`${row.discipline}-${row.activity_type}`}>
                    <td>{row.discipline}<br /><span className="muted">{row.activity_type}</span></td>
                    <td><div className="wide-bar"><i style={{ width: `${Math.min(100, row.progress || 0)}%` }} /></div><small className="muted">{row.progress}%</small></td>
                    <td>{row.completed}/{row.activities}</td>
                    <td>{row.avg_planned_duration}d / {row.avg_actual_duration == null ? '—' : `${row.avg_actual_duration}d`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel>
          <div className="panel-head"><div><h2>Delay causes</h2><span className="muted">recorded by planners at confirmation</span></div></div>
          {!delays.counts.length ? <p className="muted">No delay causes recorded yet.</p> : delays.counts.map((row) => (
            <div className="discipline-row" key={row.cause}>
              <header><span>{row.cause.replace('_', ' ')}</span><strong>{row.count}</strong></header>
              <div className="wide-bar"><i style={{ width: `${(row.count / maxDelay) * 100}%`, background: 'var(--orange)' }} /></div>
            </div>
          ))}
          {delays.weekly.length > 0 && <p className="muted">By week: {delays.weekly.map((w) => `${w.week} ${w.cause}×${w.count}`).join(' · ')}</p>}
        </Panel>

        <Panel className="wide-panel">
          <div className="panel-head"><h2>WBS progress</h2></div>
          {wbs.map((row) => <div className="memory-item" key={row.wbs_path}><strong>{row.wbs_path || '—'}</strong><small>{row.activities} activities · {row.progress || 0}% average progress</small></div>)}
        </Panel>
      </div>
    </div>
  );
}
