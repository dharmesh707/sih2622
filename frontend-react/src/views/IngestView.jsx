import { useMemo, useState } from 'react';
import Panel from '../components/Panel';
import MetricStrip from '../components/MetricStrip';
import StatusPill from '../components/StatusPill';
import Spinner from '../components/Spinner';
import { api, jsonOptions } from '../api';

const HIGH_CONFIDENCE = 'Piping crew completed spool XX102 at rack 3, 100%.';
const AMBIGUOUS = 'Piping crew working at rack 3, spool aligned, 50%.';

export default function IngestView({ metrics, setMetrics, setError, goToReview }) {
  const [reportText, setReportText] = useState('');
  const [voiceStatus, setVoiceStatus] = useState('Typed fallback ready');
  const [reportLoading, setReportLoading] = useState(false);
  const [agentLoading, setAgentLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [agentText, setAgentText] = useState('');
  const [chat, setChat] = useState([
    { role: 'system', text: 'Tell me what changed. I use the same matching and approval path as a report.' },
  ]);
  const [fileLoading, setFileLoading] = useState(false);

  const resultSummary = useMemo(() => {
    if (!result) return null;
    const m = result.match;
    return {
      decision: m?.decision || 'UNKNOWN',
      candidate: m?.activity_id ? `Candidate activity #${m.activity_id}` : 'Observation preserved without a schedule link',
      top: Number(m?.top_score || 0),
      second: Number(m?.second_score || 0),
      margin: Number(m?.margin || 0),
    };
  }, [result]);

  async function refresh() {
    const activities = await api('/projects/1/activities');
    const audit = await api('/audit');
    setMetrics({
      activities: activities.length,
      critical: activities.filter((a) => a.critical).length,
      reports: new Set(audit.map((a) => a.event_id)).size,
    });
  }

  async function submitReport(text = reportText, source = 'text') {
    if (!text.trim()) {
      setError('Enter a field report before processing it.');
      return;
    }
    setReportLoading(true);
    try {
      const started = performance.now();
      const data = await api('/reports', jsonOptions({ text, source }));
      data.client_latency_ms = Math.round(performance.now() - started);
      setResult(data);
      setMetrics((prev) => ({ ...prev, latency: data.client_latency_ms }));
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setReportLoading(false);
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

  async function sendAgent() {
    const text = agentText.trim();
    if (!text) return;
    setChat((current) => [...current, { role: 'user', text }]);
    setAgentText('');
    setAgentLoading(true);
    try {
      const result = await api('/agent/message', jsonOptions({ text, session_id: 'react-demo' }));
      setChat((current) => [
        ...current,
        {
          role: 'system',
          text: `${result.reply} ${result.match?.decision || 'UNKNOWN'} · margin ${Number(result.match?.margin || 0).toFixed(3)}`,
        },
      ]);
      setMetrics((prev) => ({ ...prev, latency: Number(result.latency_ms || 0) }));
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setAgentLoading(false);
    }
  }

  async function uploadSchedule(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setFileLoading(true);
    try {
      const form = new FormData();
      form.append('file', file);
      const data = await api('/projects/1/schedule/import', { method: 'POST', body: form });
      setError(data.errors?.length ? `${data.inserted} rows imported; ${data.errors.length} rows rejected.` : `Imported ${data.inserted} schedule rows.` , data.errors?.length ? 'warning' : 'success');
      await refresh();
    } catch (error) {
      setError(error.message);
    } finally {
      setFileLoading(false);
      event.target.value = '';
    }
  }

  return (
    <div className="view-enter">
      <div className="eyebrow">FIELD INTAKE / 01</div>
      <h1>Turn site language into schedule truth.</h1>
      <p className="lede">Capture a supervisor's observation, preserve its evidence, and let the plan show what changed.</p>

      <div className="grid two">
        <Panel className="report-panel">
          <div className="panel-head">
            <div><span className="kicker">New field report</span><h2>What happened on site?</h2></div>
            <StatusPill>LOCAL PIPELINE</StatusPill>
          </div>
          <textarea
            value={reportText}
            onChange={(e) => setReportText(e.target.value)}
            placeholder="e.g. Piping crew completed spool XX102 at rack 3, 100%."
          />
          <div className="sample-row">
            <button className="ghost" type="button" onClick={() => setReportText(HIGH_CONFIDENCE)}>Load high-confidence example</button>
            <button className="ghost" type="button" onClick={() => setReportText(AMBIGUOUS)}>Load ambiguous example</button>
          </div>
          <div className="actions">
            <button className="primary" type="button" disabled={reportLoading} onClick={() => submitReport()}>
              {reportLoading ? <Spinner label="Processing..." /> : <>Process report <span>→</span></>}
            </button>
            <button className="icon-button" type="button" onClick={startVoice} title="Use browser voice input">◉</button>
            <span className="muted">{voiceStatus}</span>
          </div>

          {resultSummary && (
            <div className="result">
              <div className="eyebrow">{resultSummary.decision}</div>
              <h3>{resultSummary.candidate}</h3>
              <p>
                Top <strong>{resultSummary.top.toFixed(3)}</strong> · runner-up <strong>{resultSummary.second.toFixed(3)}</strong> · margin <strong>{resultSummary.margin.toFixed(3)}</strong>
              </p>
              <p className="muted">
                Source span: {result?.event?.source_text || '—'}<br />
                Measured client latency: {result?.client_latency_ms ?? result?.latency_ms ?? '—'} ms
              </p>
              {resultSummary.decision !== 'AUTO_MATCHED' && (
                <button className="ghost" type="button" onClick={goToReview}>Open evidence queue →</button>
              )}
            </div>
          )}

          <div className="upload-row">
            <label>Import schedule CSV/XLSX <input type="file" accept=".csv,.xlsx" onChange={uploadSchedule} disabled={fileLoading} /></label>
            <span>{fileLoading ? 'Importing...' : 'Baseline schedule'}</span>
          </div>
        </Panel>

        <Panel className="agent-panel">
          <div className="panel-head">
            <div><span className="kicker">Time Agent</span><h2>Talk like the field</h2></div>
            <span className="agent-dot">●</span>
          </div>
          <div className="chat">
            {chat.map((message, index) => <div key={`${message.role}-${index}`} className={`bubble ${message.role}`}>{message.text}</div>)}
            {agentLoading && <div className="bubble system"><Spinner label="Thinking..." /></div>}
          </div>
          <div className="agent-input">
            <input value={agentText} onChange={(e) => setAgentText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && sendAgent()} placeholder="XX102 started at 09:30..." />
            <button className="primary compact" type="button" disabled={agentLoading} onClick={sendAgent}>Send</button>
          </div>
          <div className="agent-note">Browser microphone supported · deterministic offline fallback</div>
        </Panel>
      </div>

      <MetricStrip metrics={[
        { label: 'Schedule activities', value: metrics.activities ?? '--' },
        { label: 'Critical path', value: metrics.critical ?? '--' },
        { label: 'Reports processed', value: metrics.reports ?? '--' },
        { label: 'Last latency', value: `${metrics.latency ?? '--'} ms` },
      ]} />
    </div>
  );
}
