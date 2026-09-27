import { useEffect, useState } from 'react';
import Panel from './Panel';
import Spinner from './Spinner';
import { api, jsonOptions } from '../api';

const GREETING = { role: 'agent', text: 'Tell me what changed on site. I ask when something is missing, and nothing is written until you confirm.' };
const storageKey = (projectId) => `progresssync.agentSession.${projectId}`;
const readSession = (projectId) => { try { return localStorage.getItem(storageKey(projectId)); } catch { return null; } };
const writeSession = (projectId, id) => { try { id ? localStorage.setItem(storageKey(projectId), id) : localStorage.removeItem(storageKey(projectId)); } catch { /* storage unavailable */ } };

export default function TimeAgentPanel({ projectId, setError, onResolved }) {
  const [text, setText] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(() => readSession(projectId));
  const [state, setState] = useState('idle');
  const [chat, setChat] = useState([GREETING]);

  // Restore a persisted conversation for this project (server-side session).
  useEffect(() => {
    if (!sessionId) return;
    api(`/agent/sessions/${sessionId}?project_id=${projectId}`)
      .then((s) => { setChat([GREETING, ...s.messages.map((m) => ({ role: m.role, text: m.text }))]); setState(s.state); })
      .catch(() => { setSessionId(null); writeSession(projectId, null); });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function send(message = text.trim()) {
    if (!message) return;
    setChat((current) => [...current, { role: 'user', text: message }]);
    setText('');
    setLoading(true);
    try {
      const result = await api('/agent/message', jsonOptions({ project_id: projectId, text: message, session_id: sessionId }));
      setSessionId(result.session_id);
      writeSession(projectId, result.session_id);
      setState(result.state);
      setChat((current) => [...current, { role: 'agent', text: result.reply, decision: result.match?.decision, eventId: result.event_id }]);
      if (result.confirmation) onResolved?.(result);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setSessionId(null);
    writeSession(projectId, null);
    setState('idle');
    setChat([GREETING]);
  }

  return (
    <Panel className="agent-panel">
      <div className="panel-head">
        <div><span className="kicker">Time Agent · {state.replace('_', ' ')}</span><h2>Talk like the field</h2></div>
        <button className="ghost" type="button" onClick={reset}>New conversation</button>
      </div>
      <div className="chat" aria-live="polite">
        {chat.map((message, index) => (
          <div key={`${message.role}-${index}`} className={`bubble ${message.role === 'user' ? 'user' : 'system'}`}>
            {message.text}
            {message.decision && <small className="muted"> · {message.decision} · event #{message.eventId}</small>}
          </div>
        ))}
        {loading && <div className="bubble system"><Spinner label="Thinking..." /></div>}
      </div>
      {state === 'awaiting_confirmation' && (
        <div className="review-actions">
          <button className="primary compact" type="button" disabled={loading} onClick={() => send('yes')}>Yes, record it</button>
          <button className="secondary" type="button" disabled={loading} onClick={() => send('no')}>No, send to planner</button>
        </div>
      )}
      <div className="agent-input">
        <input aria-label="Time Agent message" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()} placeholder={state === 'clarifying' ? 'Answer the question…' : 'XX102 started at 9.'} />
        <button className="primary compact" type="button" disabled={loading} onClick={() => send()}>Send</button>
      </div>
      <div className="agent-note">Session {sessionId ? sessionId.slice(0, 8) : 'new'} · same matching pipeline and audit as reports</div>
    </Panel>
  );
}
