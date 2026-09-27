import { useEffect, useState } from 'react';
import { api } from '../api';

let cached;

export default function DelayCauseSelect({ value, onChange }) {
  const [causes, setCauses] = useState(cached || []);

  useEffect(() => {
    if (cached) return;
    api('/delay-cause-categories').then((list) => { cached = list; setCauses(list); }).catch(() => {});
  }, []);

  return (
    <select className="delay-select" aria-label="Delay cause" value={value || ''} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">No delay cause</option>
      {causes.map((cause) => <option key={cause} value={cause}>{cause.replace('_', ' ')}</option>)}
    </select>
  );
}
