import { useCallback, useEffect, useState } from 'react';
import Layout from './components/Layout';
import Toast from './components/Toast';
import IngestView from './views/IngestView';
import ReviewView from './views/ReviewView';
import ScheduleView from './views/ScheduleView';
import AnalyticsView from './views/AnalyticsView';
import AuditView from './views/AuditView';
import { api } from './api';

export default function App() {
  const [activeView, setActiveView] = useState('ingest');
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState(1);
  const [metrics, setMetrics] = useState({ activities: null, critical: null, confirmed: null, latency: null });
  const [toast, setToast] = useState({ message: '', kind: 'error' });

  const notify = useCallback((message, kind = 'error') => setToast({ message, kind }), []);

  const refreshMetrics = useCallback(async () => {
    try {
      const [activities, audit] = await Promise.all([api(`/projects/${projectId}/activities`), api(`/audit?project_id=${projectId}`)]);
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
      setProjects(await api('/projects'));
    } catch (error) {
      notify(error.message);
    }
  }, [notify]);

  useEffect(() => { loadProjects(); }, [loadProjects]);
  useEffect(() => { refreshMetrics(); }, [refreshMetrics]);

  const shared = { projectId, setError: notify };

  return (
    <Layout activeView={activeView} setActiveView={setActiveView} projects={projects} projectId={projectId} setProjectId={setProjectId}>
      {activeView === 'ingest' && <IngestView key={projectId} {...shared} metrics={metrics} setMetrics={setMetrics} refreshMetrics={refreshMetrics} onProjectsChanged={loadProjects} goToReview={() => setActiveView('review')} />}
      {activeView === 'review' && <ReviewView key={projectId} {...shared} refreshMetrics={refreshMetrics} />}
      {activeView === 'schedule' && <ScheduleView key={projectId} {...shared} />}
      {activeView === 'analytics' && <AnalyticsView key={projectId} {...shared} />}
      {activeView === 'audit' && <AuditView key={projectId} {...shared} />}
      <Toast message={toast.message} kind={toast.kind} onClose={() => setToast({ message: '', kind: 'error' })} />
    </Layout>
  );
}
