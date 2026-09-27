import { useState } from 'react';
import Panel from '../components/Panel';
import MetricStrip from '../components/MetricStrip';
import StatusPill from '../components/StatusPill';
import Spinner from '../components/Spinner';
import CandidateList from '../components/CandidateList';
import ConfirmResult from '../components/ConfirmResult';
import TimeAgentPanel from '../components/TimeAgentPanel';
import DelayCauseSelect from '../components/DelayCauseSelect';
import { api, jsonOptions } from '../api';

const HIGH_CONFIDENCE = 'Piping crew completed spool XX102 at rack 3, 100%.';
// Five seeded pump activities share tag CT-103: a genuine tie that a planner must resolve.
const AMBIGUOUS = 'Pump CT103 installed at Unit 2, 50%.';
const UNKNOWN = 'ZZ-999 unknown activity at offshore platform, 20%.';

function ExtractedEvent({ event }) {
  return (
    <p className="muted">
      Extracted · discipline {event.discipline || '—'} · identifiers {(event.identifiers || []).join(', ') || '—'} · location {event.location_terms || '—'} · progress {event.progress ?? '—'}% · time {event.time_text || '—'}<br />
      Source span [{event.source_span?.join(', ')}]: “{event.source_text}”
    </p>
  );
}

export default function IngestView({ projectId, metrics, setMetrics, refreshMetrics, setError, goToReview, onProjectsChanged }) {
  const [reportText, setReportText] = useState('');
  const [voiceStatus, setVoiceStatus] = useState('Typed fallback ready');
  const [reportLoading, setReportLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [confirmed, setConfirmed] = useState(null);
  const [delayCause, setDelayCause] = useState(null);
  const [fileLoading, setFileLoading] = useState(false);

  async function submitReport() {
    if (!reportText.trim()) {
      setError('Enter a field report before processing it.');
      return;
    }
    setReportLoading(true);
    setConfirmed(null);
    try {
      const started = performance.now();
      const data = await api('/reports', jsonOptions({ project_id: projectId, text: reportText, source: 'text' }));
      const latency = Math.round(performance.now() - started);
      setResult(data);
      setCandidates(await api(`/events/${data.event_id}/candidates`));
      await refreshMetrics();
      setMetrics((prev) => ({ ...prev, latency }));
    } catch (error) {
      setError(error.message);
    } finally {
      setReportLoading(false);
    }
  }

  async function confirmAuto() {
    setConfirming(true);
    try {
      const response = await api(`/events/${result.event_id}/confirm`, jsonOptions({ actor: 'planner', comment: 'confirmed AUTO_MATCHED from ingest', delay_cause: delayCause }));
      setConfirmed(response);
      await refreshMetrics();
    } catch (error) {
      setError(error.message);
    } finally {
      setConfirming(false);
    }
  }

  function startVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setVoiceStatus('Microphone unavailable · type instead');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.onstart = () => setVoiceStatus('Listening...');
    recognition.onresult = (event) => {
      setReportText(event.results[0][0].transcript);
      setVoiceStatus('Transcript captured');
    };
    recognition.onerror = () => setVoiceStatus('Microphone failed · type instead');
    recognition.onend = () => setVoiceStatus('Voice ready');
    recognition.start();
  }

  async function uploadSchedule(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setFileLoading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const data = await api(`/projects/${projectId}/schedule/import`, { method: 'POST', body: form });
      const depNote = data.dependencies_inserted != null ? `, ${data.dependencies_inserted} dependencies` : '';
      setError(
        data.errors?.length ? `${data.inserted} rows imported${depNote}; ${data.errors.length} rejected: ${data.errors.slice(0, 3).map((e) => `row ${e.row}: ${e.error}`).join('; ')}` : `Imported ${data.inserted} schedule rows${depNote}.`,
        data.errors?.length ? 'warning' : 'success',
      );
      await refreshMetrics();
      onProjectsChanged?.();
    } catch (error) {
      setError(error.message);
    } finally {
      setFileLoading(false);
      event.target.value = '';
    }
  }

  const match = result?.match;
  const top = candidates.find((c) => c.activity_id === match?.activity_id) || candidates[0];

  return (
    <div className="view-enter">
      <div className="eyebrow">FIELD INTAKE / 01</div>
      <h1>Turn site language into schedule truth.</h1>
      <p className="lede">Capture a supervisor's observation, preserve its evidence, and let the plan show what changed.</p>

      <div className="grid two">
        <Panel className="report-panel">
          <div className="panel-head">
            <div><span className="kicker">New field report · project #{projectId}</span><h2>What happened on site?</h2></div>
            <StatusPill>LOCAL PIPELINE</StatusPill>
          </div>
          <textarea
            aria-label="Field report"
            value={reportText}
            onChange={(e) => setReportText(e.target.value)}
            placeholder="e.g. Piping crew completed spool XX102 at rack 3, 100%."
          />
          <div className="sample-row">
            <button className="ghost" type="button" onClick={() => setReportText(HIGH_CONFIDENCE)}>Load high-confidence example</button>
            <button className="ghost" type="button" onClick={() => setReportText(AMBIGUOUS)}>Load ambiguous example</button>
            <button className="ghost" type="button" onClick={() => setReportText(UNKNOWN)}>Load unknown example</button>
          </div>
          <div className="actions">
            <button className="primary" type="button" disabled={reportLoading} onClick={submitReport}>
              {reportLoading ? <Spinner label="Processing..." /> : <>Process report <span>→</span></>}
            </button>
            <button className="icon-button" type="button" onClick={startVoice} title="Use browser voice input" aria-label="Use browser voice input">◉</button>
            <span className="muted">{voiceStatus}</span>
          </div>

          <div className="upload-row">
            <label>Import schedule CSV/XLSX <input type="file" accept=".csv,.xlsx" onChange={uploadSchedule} disabled={fileLoading} /></label>
            <span>{fileLoading ? 'Importing...' : `into project #${projectId}`}</span>
          </div>
        </Panel>

        <TimeAgentPanel projectId={projectId} setError={setError} onResolved={refreshMetrics} />

      </div>

      {result && (
        <Panel className="result-panel">
          <div className="panel-head">
            <div>
              <span className="kicker">{match.decision} · event #{result.event_id}</span>
              <h2>{match.decision === 'UNMATCHED' ? 'Observation preserved without a schedule link' : `${top?.activity_code} · ${top?.description}`}</h2>
            </div>
            <StatusPill tone={match.decision === 'AUTO_MATCHED' ? 'teal' : 'red'}>{match.decision}</StatusPill>
          </div>
          <p>
            Why: {match.reason}. Top <strong>{Number(match.top_score).toFixed(3)}</strong> · runner-up <strong>{Number(match.second_score).toFixed(3)}</strong> · margin <strong>{Number(match.margin).toFixed(3)}</strong>
            {' '}· {match.reranker_used ? `reranker v${match.reranker_version}` : 'fusion score (reranker off)'} · server {result.latency_ms} ms
          </p>
          <ExtractedEvent event={result.event} />
          <CandidateList candidates={candidates} limit={3} />
          {match.decision === 'AUTO_MATCHED' && !confirmed && (
            <div className="review-actions">
              <DelayCauseSelect value={delayCause} onChange={setDelayCause} />
              <button className="primary compact" type="button" disabled={confirming} onClick={confirmAuto}>
                {confirming ? <Spinner label="Confirming..." /> : `Confirm update to ${top?.activity_code}`}
              </button>
            </div>
          )}
          {match.decision !== 'AUTO_MATCHED' && (
            <button className="ghost" type="button" onClick={goToReview}>Open review queue to decide →</button>
          )}
        </Panel>
      )}

      <ConfirmResult result={confirmed} />

      <MetricStrip metrics={[
        { label: 'Schedule activities', value: metrics.activities ?? '--' },
        { label: 'Critical path', value: metrics.critical ?? '--' },
        { label: 'Confirmed updates', value: metrics.confirmed ?? '--' },
        { label: 'Last latency (client)', value: `${metrics.latency ?? '--'} ms` },
      ]} />
    </div>
  );
}
