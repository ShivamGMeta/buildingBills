const BASE = '/api';

export function getToken() { return localStorage.getItem('token'); }
export function getRole() { return localStorage.getItem('role'); }
export function getName() { return localStorage.getItem('name'); }

export function setSession({ access_token, role, name }) {
  localStorage.setItem('token', access_token);
  localStorage.setItem('role', role);
  localStorage.setItem('name', name);
}

export function clearSession() {
  localStorage.removeItem('token');
  localStorage.removeItem('role');
  localStorage.removeItem('name');
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(BASE + path, {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) {
    clearSession();
    location.hash = '#/login';
    throw new Error('Session expired — please log in again');
  }
  if (!res.ok) {
    let msg = `${res.status}`;
    try {
      const data = await res.json();
      msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    } catch { /* keep status code */ }
    throw new Error(msg);
  }
  if (res.headers.get('content-type')?.includes('application/json')) return res.json();
  return res;
}

export async function downloadPdf(path, filename) {
  const res = await fetch(BASE + path, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

export const MONTHS = ['', 'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'];

export function monthLabel(p) { return p ? `${MONTHS[p.month].slice(0, 3)} ${p.year}` : '—'; }

export function rupees(paise) {
  const r = Math.trunc(Math.abs(paise) / 100);
  const p = Math.abs(paise) % 100;
  let s = String(r);
  if (s.length > 3) {
    const tail = s.slice(-3);
    let head = s.slice(0, -3);
    const groups = [];
    while (head.length > 2) { groups.unshift(head.slice(-2)); head = head.slice(0, -2); }
    if (head) groups.unshift(head);
    s = groups.join(',') + ',' + tail;
  }
  return (paise < 0 ? '-' : '') + '₹' + s + (p ? '.' + String(p).padStart(2, '0') : '');
}

export async function uploadFile(path, file, fieldName = 'photo') {
  const form = new FormData();
  form.append(fieldName, file);
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: form,
  });
  if (!res.ok) {
    let msg = `${res.status}`;
    try {
      const data = await res.json();
      msg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    } catch { /* keep status code */ }
    throw new Error(msg);
  }
  return res.json();
}

export async function fetchBlobUrl(path) {
  const res = await fetch(BASE + path, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!res.ok) throw new Error(`Failed to load image (${res.status})`);
  return URL.createObjectURL(await res.blob());
}
