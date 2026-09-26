import Panel from './Panel';
import StatusPill from './StatusPill';

const days = (value) => (value == null ? '—' : `${Number(value).toFixed(1)}d`);

export default function ConfirmResult({ result }) {
  if (!result) return null;
  const { activity, old, new: next, before, after, audit, impact } = result;
  const entered = impact?.critical_entered ?? after.critical.filter((id) => !before.critical.includes(id));
  const left = impact?.critical_left ?? before.critical.filter((id) => !after.critical.includes(id));

  return (
    <Panel className="diff-panel">
      <div className="panel-head">
        <div>
          <span className="kicker">CONFIRMED · {result.approval_status?.toUpperCase()}</span>
          <h2>{activity.activity_code} · {activity.description}</h2>
        </div>
        <StatusPill tone={result.critical_path_changed ? 'red' : 'teal'}>{result.critical_path_changed ? 'CRITICAL PATH CHANGED' : 'PATH STABLE'}</StatusPill>
      </div>
      <div className="diff-grid">
        <div><span>Schedule change</span><strong>{old.percent_complete}% → {next.percent_complete}%</strong><small className="muted"> {old.status} → {next.status}</small></div>
        <div><span>Actual start / finish</span><strong>{next.actual_start || '—'} / {next.actual_finish || '—'}</strong></div>
        <div><span>Forecast project finish</span><strong>{before.project_finish_date || days(before.project_finish)} → {after.project_finish_date || days(after.project_finish)}</strong>{impact && <small className="muted"> ({impact.project_finish_change_days > 0 ? '+' : ''}{impact.project_finish_change_days}d)</small>}</div>
      </div>
      <div className="entered-left">
        <div><span className="muted">Entered critical path</span><strong>{entered.join(', ') || 'None'}</strong></div>
        <div><span className="muted">Left critical path</span><strong>{left.join(', ') || 'None'}</strong></div>
        {impact && <div><span className="muted">Downstream float changes</span><strong>{impact.float_changes.length ? impact.float_changes.map((f) => `${f.activity_code} ${days(f.before)}→${days(f.after)}`).join(', ') : 'None'}</strong></div>}
        {impact && <div><span className="muted">At-risk activities now</span><strong>{impact.at_risk.join(', ') || 'None'}</strong></div>}
        {impact && <div><span className="muted">Milestone movement</span><strong>{impact.milestones.length ? impact.milestones.map((m) => `${m.activity_code} ${m.before}→${m.after}`).join(', ') : 'None'}</strong></div>}
      </div>
      <p className="muted">Audit #{audit.id} · {audit.approval_status} by {audit.actor} at {audit.created_at} · evidence: “{audit.evidence}”</p>
    </Panel>
  );
}
