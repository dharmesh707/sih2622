import { useCallback, useEffect, useState } from 'react';
import Panel from '../components/Panel';
import Spinner from '../components/Spinner';
import { api } from '../api';

export default function ScheduleView({ setError }) {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [recomputing, setRecomputing] = useState(false);

  const load = useCallback(async () => {
    try {
      const rows = await api('/projects/1/activities');
      setActivities(rows);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [setError]);

  useEffect(() => { load(); }, [load]);

  async function recompute() {
    setRecomputing(true);
    try {
      await api('/projects/1/recompute', { method: 'POST' });
      await load();
    } catch (error) {
      setError(error.message);
    } finally {
      setRecomputing(false);
    }
  }

  return (
    <div className="view-enter">
      <div className="eyebrow">SCHEDULE GRAPH / 03</div>
      <div className="title-row">
        <div><h1>Baseline, actuals, consequence.</h1><p className="lede">Critical work is highlighted from the dependency graph, not a decorative timeline.</p></div>
        <button className="secondary" type="button" disabled={recomputing} onClick={recompute}>{recomputing ? <Spinner label="Recomputing..." /> : 'Recompute CPM'}</button>
      </div>
      <Panel>
        {loading ? <Spinner label="Loading schedule..." /> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Activity</th><th>Discipline</th><th>Plan</th><th>Actual</th><th>Float</th><th>State</th></tr></thead>
              <tbody>
                {activities.slice(0, 50).map((activity) => (
                  <tr key={activity.id}>
                    <td><strong>{activity.activity_code}</strong><br /><span className="muted">{activity.description}</span></td>
                    <td>{activity.discipline}</td>
                    <td>{activity.planned_start} → {activity.planned_finish}</td>
                    <td>{activity.actual_start || '—'}<br />{Number(activity.percent_complete || 0)}%</td>
                    <td className={activity.critical ? 'critical' : ''}>{Number(activity.total_float || 0).toFixed(1)}d</td>
                    <td className="state">{activity.at_risk ? 'AT RISK' : activity.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
