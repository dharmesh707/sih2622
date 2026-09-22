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
  const [metrics, setMetrics] = useState({ activities: null, critical: null, reports: null, latency: null });
  const [toast, setToast] = useState({ message: '', kind: 'error' });

  const notify = useCallback((message, kind = 'error') => setToast({ message, kind }), []);

  const refreshMetrics = useCallback(async () => {
    try {
      const [activities, audit] = await Promise.all([api('/projects/1/activities'), api('/audit')]);
      setMetrics((current) => ({
        ...current,
        activities: activities.length,
        critical: activities.filter((activity) => activity.critical).length,
        reports: new Set(audit.map((row) => row.event_id)).size,
      }));
    } catch (error) {
      notify(error.message);
    }
  }, [notify]);

  useEffect(() => { refreshMetrics(); }, [refreshMetrics]);

  return (
    <Layout activeView={activeView} setActiveView={setActiveView}>
      {activeView === 'ingest' && <IngestView metrics={metrics} setMetrics={setMetrics} setError={notify} goToReview={() => setActiveView('review')} />}
      {activeView === 'review' && <ReviewView setError={notify} refreshMetrics={refreshMetrics} />}
      {activeView === 'schedule' && <ScheduleView setError={notify} />}
      {activeView === 'analytics' && <AnalyticsView setError={notify} />}
      {activeView === 'audit' && <AuditView setError={notify} />}
    </Layout>
  );
}
