const NAV_ITEMS = [
  ['ingest', '01', 'Ingest'],
  ['review', '02', 'Review queue'],
  ['schedule', '03', 'Schedule'],
  ['analytics', '04', 'Analytics'],
  ['audit', '05', 'Audit + memory'],
];

export default function Layout({ activeView, setActiveView, children, projects = [], projectId, setProjectId }) {
  return (
    <div className="app-frame">
      <header className="topbar">
        <div className="brand">
          <span className="mark">PS</span>
          <div>
            <strong>ProgressSync</strong>
            <small>execution intelligence</small>
          </div>
        </div>
        <div className="status">
          <span className="pulse" />
          <span className="status-label">LOCAL PIPELINE</span>
          <span className="divider" />
          <label>
            PROJECT{' '}
            <select value={projectId} onChange={(e) => setProjectId(Number(e.target.value))}>
              {!projects.some((p) => p.id === projectId) && <option value={projectId}>#{projectId}</option>}
              {projects.map((p) => <option key={p.id} value={p.id}>#{p.id} · {p.name}</option>)}
            </select>
          </label>
        </div>
      </header>

      <main className="shell">
        <aside className="rail">
          <nav className="nav-list" aria-label="Primary">
            {NAV_ITEMS.map(([view, number, label]) => (
              <button
                key={view}
                type="button"
                className={`nav ${activeView === view ? 'active' : ''}`}
                onClick={() => setActiveView(view)}
              >
                <span>{number}</span>
                {label}
              </button>
            ))}
          </nav>
          <div className="rail-footer">v1.2 / REACT FRONTEND</div>
        </aside>

        <section className="content">{children}</section>
      </main>
    </div>
  );
}
