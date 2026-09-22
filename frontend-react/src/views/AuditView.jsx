import { useCallback, useEffect, useState } from 'react';
import Panel from '../components/Panel';
import Spinner from '../components/Spinner';
import { api } from '../api';

export default function AuditView({ setError }) {
  const [audit, setAudit] = useState([]);
  const [terms, setTerms] = useState([]);
  const [query, setQuery] = useState('piping erection');
  const [memory, setMemory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [memoryLoading, setMemoryLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const [auditRows, termRows] = await Promise.all([api('/audit'), api('/terminology-map')]);
      setAudit(auditRows);
      setTerms(termRows);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [setError]);

  useEffect(() => { load(); }, [load]);

  async function searchMemory() {
    setMemoryLoading(true);
    try {
      const rows = await api(`/memory/similar?description=${encodeURIComponent(query)}`);
      setMemory(rows);
    } catch (error) {
      setError(error.message);
    } finally {
      setMemoryLoading(false);
    }
  }

  useEffect(() => { searchMemory(); }, []);

  return (
    <div className="view-enter">
      <div className="eyebrow">PROVENANCE / 05</div>
      <h1>Every update keeps its receipt.</h1>
      <p className="lede">Search the memory created by confirmed execution, not a black box.</p>

      <Panel>
        <div className="panel-head"><div><h2>Audit trail</h2><span className="muted">old value → new value · source · actor · score</span></div></div>
        {loading ? <Spinner label="Loading audit trail..." /> : <div className="table-wrap"><table><thead><tr><th>Time</th><th>Activity</th><th>Change</th><th>Evidence</th><th>Actor</th></tr></thead><tbody>{audit.map((row) => <tr key={row.id}><td>{row.created_at}</td><td>#{row.activity_id}</td><td>{row.old_value} → {row.new_value}</td><td>{row.evidence}</td><td>{row.actor} · {Number(row.score || 0).toFixed(2)}</td></tr>)}{!audit.length && <tr><td colSpan="5">No confirmed updates yet.</td></tr>}</tbody></table></div>}
      </Panel>

      <div className="grid two audit-bottom">
        <Panel>
          <div className="panel-head"><h2>Institutional memory</h2></div>
          <div className="agent-input"><input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && searchMemory()} /><button className="primary compact" type="button" onClick={searchMemory} disabled={memoryLoading}>{memoryLoading ? 'Searching...' : 'Search'}</button></div>
          <div>{memory.map((row) => <div className="memory-item" key={`${row.activity_code}-${row.description}`}><strong>{row.activity_code} · {row.description}</strong><small>{row.discipline} · similarity {Number(row.similarity || 0).toFixed(2)} · actual duration {row.actual_duration} days</small></div>)}{!memory.length && !memoryLoading && <p className="muted">No historical executions yet.</p>}</div>
        </Panel>

        <Panel>
          <div className="panel-head"><div><h2>Terminology map</h2><span className="muted">field language → canonical schedule language</span></div></div>
          <div className="table-wrap"><table className="compact-table"><thead><tr><th>Field term</th><th>Canonical</th><th>Discipline</th></tr></thead><tbody>{terms.map((row) => <tr key={`${row.field_term}-${row.canonical_term}`}><td>{row.field_term}</td><td>{row.canonical_term}</td><td>{row.discipline}</td></tr>)}</tbody></table></div>
        </Panel>
      </div>
    </div>
  );
}
