export async function api(path, options = {}) {
  const response = await fetch(`/api/v1${path}`, options);
  const contentType = response.headers.get('content-type') || '';
  const body = contentType.includes('application/json')
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = typeof body === 'string' ? body : body?.detail || body?.message;
    throw new Error(message || `Request failed (${response.status})`);
  }

  return body;
}

export function jsonOptions(payload) {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  };
}
