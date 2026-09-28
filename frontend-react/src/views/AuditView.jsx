import { useCallback, useEffect, useState } from "react";
import Panel from "../components/Panel";
import Spinner from "../components/Spinner";
import { api, download } from "../api";

const DISCIPLINES = [
  "",
  "civil",
  "piping",
  "static_equipment",
  "rotating_equipment",
  "electrical",
  "instrumentation",
  "hse",
];
const signed = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v}d`);

export default function AuditView({ projectId, setError }) {
  const [audit, setAudit] = useState([]);
  const [terms, setTerms] = useState([]);
  const [summary, setSummary] = useState([]);
  const [filters, setFilters] = useState({
    description: "",
    discipline: "",
    location: "",
    allProjects: false,
  });
  const [memory, setMemory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [memoryLoading, setMemoryLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const [auditRows, termRows, summaryRows] = await Promise.all([
        api(`/audit?project_id=${projectId}`),
        api("/terminology-map"),
        api(`/memory/summary?project_id=${projectId}`),
      ]);
      setAudit(auditRows);
      setTerms(termRows);
      setSummary(summaryRows);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }, [projectId, setError]);

  const searchMemory = useCallback(
    async (current) => {
      setMemoryLoading(true);
      try {
        const params = new URLSearchParams();
        if (!current.allProjects) params.set("project_id", projectId);
        if (current.description) params.set("description", current.description);
        if (current.discipline) params.set("discipline", current.discipline);
        if (current.location) params.set("location", current.location);
        setMemory(await api(`/memory/similar?${params}`));
      } catch (error) {
        setError(error.message);
      } finally {
        setMemoryLoading(false);
      }
    },
    [projectId, setError],
  );

  useEffect(() => {
    load();
    searchMemory(filters);
  }, [load]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (key) => (e) =>
    setFilters((f) => ({
      ...f,
      [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value,
    }));

  return (
    <div className="view-enter">
      <div className="eyebrow">PROVENANCE / 05</div>
      <h1>Every update keeps its receipt.</h1>
      <p className="lede">
        The audit trail of human decisions and the execution memory built from
        confirmed actuals.
      </p>

      <Panel>
        <div className="panel-head">
          <div>
            <h2>Audit trail</h2>
            <span className="muted">
              old value → new value · decision kind · actor · score
            </span>
          </div>
          <button
            className="secondary compact"
            type="button"
            onClick={() =>
              download(
                `/audit/export?project_id=${projectId}`,
                `audit-project-${projectId}.csv`,
              ).catch((error) => setError(error.message))
            }
          >
            Download CSV
          </button>
        </div>
        {loading ? (
          <Spinner label="Loading audit trail..." />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time (UTC)</th>
                  <th>Activity</th>
                  <th>Change</th>
                  <th>Evidence</th>
                  <th>Actor</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((row) => (
                  <tr key={row.id}>
                    <td>{row.created_at}</td>
                    <td>
                      <strong>
                        {row.activity_code || `#${row.activity_id}`}
                      </strong>
                      <br />
                      <span className="muted">
                        {row.approval_status} · event #{row.event_id}
                      </span>
                    </td>
                    <td>
                      {row.old_value} → {row.new_value}
                    </td>
                    <td>{row.evidence}</td>
                    <td>
                      {row.actor} · {Number(row.score || 0).toFixed(2)}
                    </td>
                  </tr>
                ))}
                {!audit.length && (
                  <tr>
                    <td colSpan="5">No confirmed updates yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel className="memory-panel">
        <div className="panel-head">
          <div>
            <h2>Institutional memory</h2>
            <span className="muted">
              confirmed actuals · actual duration only when both actual dates
              exist
            </span>
          </div>
        </div>
        <div className="memory-filters">
          <input
            aria-label="Memory description"
            placeholder="activity type / description, e.g. erect line spool"
            value={filters.description}
            onChange={set("description")}
            onKeyDown={(e) => e.key === "Enter" && searchMemory(filters)}
          />
          <select
            aria-label="Memory discipline"
            value={filters.discipline}
            onChange={set("discipline")}
          >
            {DISCIPLINES.map((d) => (
              <option key={d} value={d}>
                {d || "any discipline"}
              </option>
            ))}
          </select>
          <input
            aria-label="Memory location"
            placeholder="location, e.g. R03"
            value={filters.location}
            onChange={set("location")}
          />
          <label className="muted">
            <input
              type="checkbox"
              checked={filters.allProjects}
              onChange={set("allProjects")}
            />{" "}
            all projects
          </label>
          <button
            className="primary compact"
            type="button"
            onClick={() => searchMemory(filters)}
            disabled={memoryLoading}
          >
            {memoryLoading ? "Searching..." : "Search"}
          </button>
        </div>
        <div className="table-wrap">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Activity</th>
                <th>Type · discipline · location</th>
                <th>Planned</th>
                <th>Actual</th>
                <th>Variance (start / finish / duration)</th>
                <th>Delay cause</th>
                <th>Sim.</th>
              </tr>
            </thead>
            <tbody>
              {memory.map((row) => (
                <tr key={row.activity_id}>
                  <td>
                    <strong>{row.activity_code}</strong>
                    <br />
                    <span className="muted">
                      {row.description} · project #{row.project_id}
                    </span>
                  </td>
                  <td>
                    {row.activity_type}
                    <br />
                    <span className="muted">
                      {row.discipline} · {row.location || "—"}
                    </span>
                  </td>
                  <td>
                    {row.planned_start} → {row.planned_finish} (
                    {row.planned_duration}d)
                  </td>
                  <td>
                    {row.actual_start || "—"} → {row.actual_finish || "—"} (
                    {row.actual_duration == null
                      ? "n/a"
                      : `${row.actual_duration}d`}
                    )
                  </td>
                  <td>
                    {signed(row.start_variance)} / {signed(row.finish_variance)}{" "}
                    / {signed(row.duration_variance)}
                  </td>
                  <td>
                    {row.delay_cause
                      ? `${row.delay_cause}${row.notes ? `: ${row.notes}` : ""}`
                      : "—"}
                  </td>
                  <td>
                    {row.similarity == null ? "—" : row.similarity.toFixed(2)}
                  </td>
                </tr>
              ))}
              {!memory.length && !memoryLoading && (
                <tr>
                  <td colSpan="7">No execution history matches.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {summary.length > 0 && (
          <p className="muted">
            Summary by type:{" "}
            {summary
              .map(
                (s) =>
                  `${s.activity_type} (${s.discipline}) ${s.completed}/${s.records} done, avg actual ${s.avg_actual_duration ?? "—"}d, var ${signed(s.avg_duration_variance)}${s.top_delay_cause ? `, top cause ${s.top_delay_cause}` : ""}`,
              )
              .join(" · ")}
          </p>
        )}
      </Panel>

      <Panel>
        <div className="panel-head">
          <div>
            <h2>Terminology map</h2>
            <span className="muted">
              field language → canonical schedule language
            </span>
          </div>
        </div>
        <div className="table-wrap">
          <table className="compact-table">
            <thead>
              <tr>
                <th>Field term</th>
                <th>Canonical</th>
                <th>Discipline</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {terms.map((row) => (
                <tr key={`${row.field_term}-${row.canonical_term}`}>
                  <td>{row.field_term}</td>
                  <td>{row.canonical_term}</td>
                  <td>{row.discipline}</td>
                  <td className="muted">
                    {row.version} · {row.source}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
