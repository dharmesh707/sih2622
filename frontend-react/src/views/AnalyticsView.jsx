import { useCallback, useEffect, useState } from 'react';
import Panel from '../components/Panel';
import Spinner from '../components/Spinner';
import { api } from '../api';

export default function AnalyticsView({ setError }) {
  const [data, setData] = useState({ productivity: [], variance: [], delayCauses: [] });
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [productivity, variance, delayCauses] = await Promise.all([
        api('/analytics/discipline-productivity'),
        api('/analytics/variance'),
        api('/analytics/delay-causes'),
      ]);
      setData({ productivity, variance, delayCauses });
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [setError]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <><div className="eyebrow">SIGNALS / 04</div><h1>Progress patterns worth acting on.</h1><p className="lede"><Spinner label="Loading analytics..." /></p></>;

  return (
    <div className="view-enter">
      <div className="eyebrow">SIGNALS / 04</div>
      <h1>Progress patterns worth acting on.</h1>
      <p className="lede">Backend-derived productivity, delay causes, and variance — with no dashboard numbers painted on.</p>
      <div className="analytics-grid">
        <Panel>
          <div className="panel-head"><h2>Discipline progress</h2></div>
          {!data.productivity.length ? <p className="muted">No productivity data yet.</p> : data.productivity.map((row) => {
            const progress = Number(row.progress || 0);
            return <div className="discipline-row" key={row.discipline}><header><span>{row.discipline}</span><strong>{progress}%</strong></header><div className="wide-bar"><i style={{ width: `${Math.min(100, progress)}%` }} /></div></div>;
          })}
        </Panel>
        <Panel>
          <div className="panel-head"><h2>WBS variance</h2></div>
          {!data.variance.length ? <p className="muted">No variance data yet.</p> : data.variance.map((row) => <div className="memory-item" key={row.wbs_path}><strong>{row.wbs_path}</strong><small>{row.activities} activities · {row.progress || 0}% average progress</small></div>)}
        </Panel>
        <Panel className="wide-panel">
          <div className="panel-head"><h2>Delay causes</h2><span className="muted">confirmed events only</span></div>
          {!data.delayCauses.length ? <p className="muted">No delay causes logged yet.</p> : data.delayCauses.map((row) => <div className="delay-row" key={row.cause}><strong>{row.cause}</strong><span>{row.count}</span></div>)}
        </Panel>
      </div>
    </div>
  );
}
