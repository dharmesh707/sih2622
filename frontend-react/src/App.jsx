import { useCallback, useEffect, useState } from "react";
import Layout from "./components/Layout";
import Toast from "./components/Toast";
import IngestView from "./views/IngestView";
import ReviewView from "./views/ReviewView";
import ScheduleView from "./views/ScheduleView";
import AnalyticsView from "./views/AnalyticsView";
import AuditView from "./views/AuditView";
import { api, clearToken, getToken, setToken } from "./api";

function LoginScreen({ onLogin }) {
  const [value, setValue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setToken(value);
    try {
      await api("/projects");
      onLogin();
    } catch (requestError) {
      clearToken();
      setError(requestError.message || "The token was rejected.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-shell">
      <form className="login-panel" onSubmit={submit}>
        <span className="eyebrow">PROGRESSSYNC AI</span>
        <h1>Demo access</h1>
        <p className="lede">
          Enter the shared deployment token to open the project workspace.
        </p>
        <label htmlFor="demo-token">API token</label>
        <input
          id="demo-token"
          type="password"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          autoComplete="current-password"
          required
        />
        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Checking..." : "Open workspace"}
        </button>
      </form>
    </main>
  );
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(Boolean(getToken()));
  const [activeView, setActiveView] = useState("ingest");
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(1);
  const [metrics, setMetrics] = useState({
    activities: null,
    critical: null,
    confirmed: null,
    latency: null,
  });
  const [toast, setToast] = useState({ message: "", kind: "error" });

  const notify = useCallback(
    (message, kind = "error") => setToast({ message, kind }),
    [],
  );

  useEffect(() => {
    const handleUnauthorized = () => setAuthenticated(false);
    window.addEventListener("progresssync:unauthorized", handleUnauthorized);
    return () =>
      window.removeEventListener(
        "progresssync:unauthorized",
        handleUnauthorized,
      );
  }, []);

  const refreshMetrics = useCallback(async () => {
    try {
      const [activities, audit] = await Promise.all([
        api(`/projects/${projectId}/activities`),
        api(`/audit?project_id=${projectId}`),
      ]);
      setMetrics((current) => ({
        ...current,
        activities: activities.length,
        critical: activities.filter((activity) => activity.critical).length,
        confirmed: audit.length,
      }));
    } catch (error) {
      notify(error.message);
    }
  }, [notify, projectId]);

  const loadProjects = useCallback(async () => {
    try {
      setProjects(await api("/projects"));
    } catch (error) {
      notify(error.message);
    }
  }, [notify]);

  useEffect(() => {
    if (authenticated) loadProjects();
  }, [authenticated, loadProjects]);
  useEffect(() => {
    if (authenticated) refreshMetrics();
  }, [authenticated, refreshMetrics]);

  if (!authenticated)
    return <LoginScreen onLogin={() => setAuthenticated(true)} />;

  const shared = { projectId, setProjectId, setError: notify };

  return (
    <Layout
      activeView={activeView}
      setActiveView={setActiveView}
      projects={projects}
      projectId={projectId}
      setProjectId={setProjectId}
      onLogout={() => {
        clearToken();
        setAuthenticated(false);
      }}
    >
      {activeView === "ingest" && (
        <IngestView
          key={projectId}
          {...shared}
          metrics={metrics}
          setMetrics={setMetrics}
          refreshMetrics={refreshMetrics}
          onProjectsChanged={loadProjects}
          goToReview={() => setActiveView("review")}
        />
      )}
      {activeView === "review" && (
        <ReviewView
          key={projectId}
          {...shared}
          refreshMetrics={refreshMetrics}
        />
      )}
      {activeView === "schedule" && (
        <ScheduleView key={projectId} {...shared} />
      )}
      {activeView === "analytics" && (
        <AnalyticsView key={projectId} {...shared} />
      )}
      {activeView === "audit" && <AuditView key={projectId} {...shared} />}
      <Toast
        message={toast.message}
        kind={toast.kind}
        onClose={() => setToast({ message: "", kind: "error" })}
      />
    </Layout>
  );
}
