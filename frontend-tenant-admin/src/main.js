import './style.css';
import {
  api, clearSession, downloadPdf, getName, getRole, getToken, monthLabel,
  MONTHS, rupees, setSession,
} from './api.js';

const app = document.getElementById('app');
const state = { periods: [], periodId: null };

const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const isAdmin = () => getRole() === 'admin' || getRole() === 'superuser';

function header(title, back = null, right = '') {
  return `<div class="header">
    ${back ? `<button class="iconbtn" onclick="location.hash='${back}'">‹</button>` : ''}
    <div class="grow"><h1>${esc(title)}</h1>
      ${back ? '' : `<div class="sub">${isAdmin() ? 'Admin' : 'Tenant'} · ${esc(getName() || '')}</div>`}</div>
    ${right}
  </div>`;
}

function nav(active) {
  const item = (href, icon, label, key) =>
    `<a href="${href}" class="${active === key ? 'active' : ''}">
       <span class="nicon">${icon}</span>${label}</a>`;
  if (!isAdmin()) {
    return `<div class="bottomnav">
      ${item('#/', '📄', 'My Bills', 'bills')}
      ${item('#/profile', '👤', 'Profile', 'profile')}
    </div>`;
  }
  return `<div class="bottomnav">
    ${item('#/', '🏠', 'Home', 'home')}
    ${item('#/meters', '📟', 'Meters', 'meters')}
    <button class="fab" onclick="location.hash='#/add-reading'">+</button>
    ${item('#/bills', '📄', 'Bills', 'bills')}
    ${item('#/more', '⋯', 'More', 'more')}
  </div>`;
}

async function loadPeriods() {
  state.periods = await api('/periods');
  if (!state.periodId && state.periods.length) state.periodId = state.periods[0].id;
}
const currentPeriod = () => state.periods.find((p) => p.id === state.periodId);

function periodTabs() {
  return `<div class="pill-tabs">${state.periods.map((p) =>
    `<button class="pill ${p.id === state.periodId ? 'active' : ''}"
       data-period="${p.id}">${monthLabel(p)}</button>`).join('')}</div>`;
}
function bindPeriodTabs(rerender) {
  document.querySelectorAll('[data-period]').forEach((el) =>
    el.addEventListener('click', () => { state.periodId = +el.dataset.period; rerender(); }));
}

function fail(e) {
  app.innerHTML = `${header('Building Bills')}
    <div class="page"><div class="error">${esc(e.message)}</div></div>${nav('')}`;
}

// ---------- auth ----------
async function loginView() {
  app.innerHTML = `<div class="login-wrap"><div class="login-card">
    <h1>Building Bills</h1>
    <div class="sub">Tenant & Admin — sign in</div>
    <div id="err"></div>
    <label class="field">Email<input id="email" type="email" autocomplete="username"></label>
    <label class="field">Password<input id="pw" type="password" autocomplete="current-password"></label>
    <button class="btn" id="go">Sign in</button>
  </div></div>`;
  document.getElementById('go').onclick = async () => {
    try {
      const session = await api('/auth/login', { method: 'POST', body: {
        email: document.getElementById('email').value.trim(),
        password: document.getElementById('pw').value,
      } });
      setSession(session);
      location.hash = '#/';
      route();
    } catch (e) {
      document.getElementById('err').innerHTML = `<div class="error">${esc(e.message)}</div>`;
    }
  };
}

// ---------- tenant views ----------
async function myBillsView() {
  const bills = await api('/tenant/bills');
  app.innerHTML = `${header('My Bills')}
  <div class="page"><div class="card">
    <h2>Published Bills</h2>
    ${bills.length ? bills.map((b) => `
      <div class="list-row" onclick="location.hash='#/bill/${b.id}'">
        <div class="icon">📄</div>
        <div><div class="title">${MONTHS[b.period_month]} ${b.period_year}</div>
          <div class="sub">${b.billable_units} units
            <span class="badge ${b.is_paid ? 'paid' : 'unpaid'}">${b.is_paid ? 'PAID' : 'UNPAID'}</span></div></div>
        <div class="right"><div class="big">${rupees(b.total_paise)}</div></div>
      </div>`).join('')
    : '<p class="note">No bills published yet — you\'ll get an email when one is ready.</p>'}
  </div></div>${nav('bills')}`;
}

async function myBillView(id) {
  const b = await api(`/tenant/bills/${id}`);
  app.innerHTML = `${header('Bill', '#/', `<button class="iconbtn" id="pdf">⤓</button>`)}
  <div class="page"><div class="card">
    <div class="section-head"><h2>${esc(b.unit_name)}</h2>
      <span class="badge ${b.is_paid ? 'paid' : 'unpaid'}">${b.is_paid ? 'PAID' : 'UNPAID'}</span></div>
    <span class="badge published">${MONTHS[b.period_month]} ${b.period_year}</span>
    <h2 style="margin-top:14px">Electricity Details</h2>
    <div class="kv"><span class="k">Previous Reading</span><span class="v">${b.prev_reading} kWh</span></div>
    <div class="kv"><span class="k">Current Reading</span><span class="v">${b.curr_reading} kWh</span></div>
    <div class="kv"><span class="k">Units Consumed</span><span class="v">${b.own_units} kWh</span></div>
    <div class="kv"><span class="k">Add: Lift & Parking Share</span><span class="v">${b.common_share_units} kWh</span></div>
    ${b.ev_units ? `<div class="kv"><span class="k">Add: EV Charging</span><span class="v">${b.ev_units} kWh</span></div>` : ''}
    <div class="kv"><span class="k">Billable Units</span><span class="v">${b.billable_units} kWh</span></div>
    <div class="kv"><span class="k">Rate</span><span class="v">${rupees(b.rate_paise)} / unit</span></div>
    <div class="kv"><span class="k"><b>Electricity Bill</b></span><span class="v">${rupees(b.electricity_paise)}</span></div>
    <h2 style="margin-top:14px">Other Charges</h2>
    ${b.charge_lines.map((l) => `
      <div class="kv"><span class="k">${esc(l.label)}</span><span class="v">${rupees(l.amount_paise)}</span></div>`).join('')}
    <div class="kv total"><span class="k">Total Amount</span><span class="v">${rupees(b.total_paise)}</span></div>
  </div>
  <button class="btn" id="dl">⤓ Download PDF</button>
  </div>${nav('bills')}`;
  const dl = () => downloadPdf(`/tenant/bills/${id}/pdf`, `bill-${MONTHS[b.period_month]}-${b.period_year}.pdf`)
    .catch((e) => alert(e.message));
  document.getElementById('pdf').onclick = dl;
  document.getElementById('dl').onclick = dl;
}

async function profileView() {
  const me = await api('/tenant/me');
  let unit = null;
  try { unit = await api('/tenant/unit'); } catch { /* no unit linked */ }
  app.innerHTML = `${header('My Profile')}
  <div class="page"><div class="card">
    <h2>Personal Details</h2>
    <div class="kv"><span class="k">Name</span><span class="v">${esc(me.name)}</span></div>
    <div class="kv"><span class="k">Email</span><span class="v">${esc(me.email)}</span></div>
    <div class="kv"><span class="k">Phone</span><span class="v">${esc(me.phone || '—')}</span></div>
    ${unit ? `<div class="kv"><span class="k">Unit</span><span class="v">${esc(unit.name)}</span></div>
    <div class="kv"><span class="k">Meter</span><span class="v">${esc(unit.meter_no)}</span></div>` : ''}
    <p class="note" style="margin-top:12px">Details are read-only. Contact the building admin for changes.</p>
  </div>
  <button class="btn outline" id="logout">Log out</button>
  </div>${nav('profile')}`;
  document.getElementById('logout').onclick = () => { clearSession(); location.hash = '#/login'; route(); };
}

// ---------- admin views (scoped by the API to assigned floors) ----------
async function homeView() {
  await loadPeriods();
  const d = await api(`/dashboard${state.periodId ? `?period_id=${state.periodId}` : ''}`);
  const pct = d.total_billed_paise
    ? Math.round((d.total_collected_paise / d.total_billed_paise) * 100) : 0;
  app.innerHTML = `${header('Building Bills')}
  <div class="page">
    <div class="card row">
      <div class="grow">
        <div class="sub" style="color:var(--muted);font-weight:700">${monthLabel(d.period)} · My Floors</div>
        <div class="bignum">${rupees(d.total_billed_paise)}</div>
        <div class="trend">${d.bills_paid}/${d.bills_count} bills paid</div>
      </div>
      <div class="donut" style="background:conic-gradient(var(--blue) ${pct * 3.6}deg, #e2e8f0 0deg)">
        <div class="inner">${pct}%<small>Collected</small></div>
      </div>
    </div>
    <div class="card">
      <h2>Quick Actions</h2>
      <div class="quick">
        <button onclick="location.hash='#/add-reading'"><div class="qicon">📷</div>Add Reading</button>
        <button onclick="location.hash='#/generate'"><div class="qicon" style="background:#dcfce7">🧾</div>Generate Bills</button>
        <button onclick="location.hash='#/bills'"><div class="qicon">📄</div>View Bills</button>
        <button onclick="location.hash='#/tenants'"><div class="qicon" style="background:#fef3c7">👥</div>Tenants</button>
      </div>
    </div>
    <div class="card">
      <div class="section-head"><h2>Summary</h2>
        <span class="badge published">${monthLabel(d.period)}</span></div>
      <div class="kv"><span class="k">⚡ Units Consumed</span><span class="v">${d.total_units_consumed.toLocaleString('en-IN')} kWh</span></div>
      <div class="kv"><span class="k">🔌 Electricity</span><span class="v">${rupees(d.total_electricity_paise)}</span></div>
      <div class="kv"><span class="k">🏠 Other Charges</span><span class="v">${rupees(d.total_other_charges_paise)}</span></div>
      <div class="kv"><span class="k">📊 Billed</span><span class="v">${rupees(d.total_billed_paise)}</span></div>
    </div>
    <p class="note">You see only your assigned floors. Building-wide settings live in the Superuser console.</p>
  </div>${nav('home')}`;
}

async function metersView() {
  await loadPeriods();
  const units = await api('/units');
  const readings = state.periodId ? await api(`/readings?period_id=${state.periodId}`) : [];
  const byUnit = Object.fromEntries(readings.map((r) => [r.unit_id, r]));
  const idx = state.periods.findIndex((p) => p.id === state.periodId);
  const prevPeriod = state.periods[idx + 1];
  const prev = prevPeriod
    ? Object.fromEntries((await api(`/readings?period_id=${prevPeriod.id}`))
        .map((r) => [r.unit_id, r])) : {};
  app.innerHTML = `${header('Meters & Readings')}
  <div class="page">
    ${periodTabs()}
    <div class="card">
      ${units.map((u) => {
        const r = byUnit[u.id];
        const base = prev[u.id]?.reading ?? u.opening_reading;
        const delta = r ? r.reading - base : null;
        return `<div class="list-row" onclick="location.hash='#/add-reading?unit=${u.id}'">
          <div class="icon">${u.has_ev ? '🔌' : '🏢'}</div>
          <div><div class="title">${esc(u.name)}</div>
               <div class="sub">${esc(u.meter_no)}</div></div>
          <div class="right">
            <div class="big">${r ? `${r.reading.toLocaleString('en-IN')} kWh` : '—'}</div>
            ${delta !== null ? `<div class="delta">↑ ${delta} units</div>` : `<div class="sub">no reading</div>`}
          </div>
        </div>`;
      }).join('') || '<p class="note">No floors assigned to you yet.</p>'}
    </div>
  </div>${nav('meters')}`;
  bindPeriodTabs(metersView);
}

async function addReadingView(params) {
  await loadPeriods();
  const units = await api('/units');
  const preselect = +params.get('unit') || units[0]?.id;
  const today = new Date().toISOString().slice(0, 10);
  app.innerHTML = `${header('Add Meter Reading', '#/meters')}
  <div class="page"><div class="card">
    <label class="field">Billing month
      <select id="period">${state.periods.map((p) =>
        `<option value="${p.id}" ${p.id === state.periodId ? 'selected' : ''}>${monthLabel(p)}</option>`).join('')}
      </select></label>
    <label class="field">Meter
      <select id="unit">${units.map((u) =>
        `<option value="${u.id}" ${u.id === preselect ? 'selected' : ''}>${esc(u.name)} — ${esc(u.meter_no)}</option>`).join('')}
      </select></label>
    <label class="field">Current reading (kWh)<input id="reading" type="number" min="0" inputmode="numeric"></label>
    <label class="field">Reading date<input id="rdate" type="date" value="${today}"></label>
    <label class="field">Notes (optional)<input id="note" placeholder="Add any notes..."></label>
    <div id="err"></div>
    <button class="btn" id="save">✓ Save Reading</button>
  </div></div>${nav('meters')}`;
  document.getElementById('save').onclick = async () => {
    try {
      await api('/readings', { method: 'POST', body: {
        unit_id: +document.getElementById('unit').value,
        period_id: +document.getElementById('period').value,
        reading: +document.getElementById('reading').value,
        reading_date: document.getElementById('rdate').value,
        note: document.getElementById('note').value,
      } });
      location.hash = '#/meters';
    } catch (e) {
      document.getElementById('err').innerHTML = `<div class="error">${esc(e.message)}</div>`;
    }
  };
}

async function generateView() {
  await loadPeriods();
  const templates = await api('/charge-templates');
  const p = currentPeriod();
  app.innerHTML = `${header('Generate Bills', '#/')}
  <div class="page">
    ${periodTabs()}
    <div class="card" style="background:#ecfdf5">
      <b>Electricity Rate</b>
      <div class="sub" style="color:var(--muted)">${rupees(p?.rate_paise ?? 0)} per unit —
        set by the Superuser</div>
    </div>
    <div class="card">
      <h2>Include in Bill</h2>
      ${templates.filter((t) => t.is_active).map((t) => `
        <div class="checkrow">
          <input type="checkbox" checked data-tpl="${t.id}">
          <span class="lbl">${esc(t.label)}</span>
          <input type="number" min="0" value="${t.default_amount_paise / 100}" data-amt="${t.id}">
        </div>`).join('')}
    </div>
    <div id="err"></div>
    <button class="btn" id="gen">Generate Bills</button>
    <p class="note">Draft bills will be generated for your floors only.</p>
  </div>${nav('bills')}`;
  bindPeriodTabs(generateView);
  document.getElementById('gen').onclick = async () => {
    try {
      const lines = templates.filter((t) =>
        document.querySelector(`[data-tpl="${t.id}"]`)?.checked)
        .map((t) => ({ label: t.label,
          amount_paise: Math.round(+document.querySelector(`[data-amt="${t.id}"]`).value * 100) }))
        .filter((l) => l.amount_paise > 0);
      await api(`/periods/${state.periodId}/generate-bills`,
        { method: 'POST', body: { charge_lines: lines } });
      location.hash = '#/bills';
    } catch (e) {
      document.getElementById('err').innerHTML = `<div class="error">${esc(e.message)}</div>`;
    }
  };
}

async function billsView() {
  await loadPeriods();
  const bills = state.periodId ? await api(`/bills?period_id=${state.periodId}`) : [];
  app.innerHTML = `${header('Bills')}
  <div class="page">
    ${periodTabs()}
    <div class="card">
      ${bills.length ? bills.map((b) => `
        <div class="list-row" onclick="location.hash='#/staff-bill/${b.id}'">
          <div class="icon">📄</div>
          <div><div class="title">${esc(b.unit_name)}${b.tenant_name ? ` (${esc(b.tenant_name)})` : ''}</div>
            <div class="sub"><span class="badge ${b.status}">${b.status.toUpperCase()}</span>
            ${b.is_paid ? '<span class="badge paid">PAID</span>' : ''}</div></div>
          <div class="right"><div class="big">${rupees(b.total_paise)}</div></div>
        </div>`).join('')
      : `<p class="note">No bills for this month on your floors.</p>`}
    </div>
    <button class="btn" onclick="location.hash='#/generate'">Generate Bills</button>
  </div>${nav('bills')}`;
  bindPeriodTabs(billsView);
}

async function staffBillView(id) {
  const b = await api(`/bills/${id}`);
  const published = b.status === 'published';
  app.innerHTML = `${header('Bill Preview', '#/bills',
    `<button class="iconbtn" id="pdf">⤓</button>`)}
  <div class="page">
    <div class="card">
      <div class="section-head">
        <h2>${esc(b.unit_name)}${b.tenant_name ? ` (${esc(b.tenant_name)})` : ''}</h2>
        <span class="badge ${b.is_paid ? 'paid' : 'unpaid'}">${b.is_paid ? 'PAID' : 'UNPAID'}</span>
      </div>
      <span class="badge ${b.status}">${b.status.toUpperCase()}</span>
      <h2 style="margin-top:14px">Electricity Details</h2>
      <div class="kv"><span class="k">Previous Reading</span><span class="v">${b.prev_reading} kWh</span></div>
      <div class="kv"><span class="k">Current Reading</span><span class="v">${b.curr_reading} kWh</span></div>
      <div class="kv"><span class="k">Units Consumed</span><span class="v">${b.own_units} kWh</span></div>
      <div class="kv"><span class="k">Add: Lift & Parking Share</span><span class="v">${b.common_share_units} kWh</span></div>
      ${b.ev_units ? `<div class="kv"><span class="k">Add: EV Charging</span><span class="v">${b.ev_units} kWh</span></div>` : ''}
      <div class="kv"><span class="k">Billable Units</span><span class="v">${b.billable_units} kWh</span></div>
      <div class="kv"><span class="k">Rate</span><span class="v">${rupees(b.rate_paise)} / unit</span></div>
      <div class="kv"><span class="k"><b>Electricity Bill</b></span><span class="v">${rupees(b.electricity_paise)}</span></div>
      <h2 style="margin-top:14px">Other Charges
        ${published ? '' : `<button class="link" id="edit-charges">Edit</button>`}</h2>
      ${b.charge_lines.map((l) => `
        <div class="kv"><span class="k">${esc(l.label)}</span><span class="v">${rupees(l.amount_paise)}</span></div>`).join('')}
      <div class="kv total"><span class="k">Total Amount</span><span class="v">${rupees(b.total_paise)}</span></div>
    </div>
    <div id="err"></div>
    <div class="btnrow">
      <button class="btn green" id="paid">${b.is_paid ? '↺ Mark Unpaid' : '✓ Mark as Paid'}</button>
      <button class="btn ${published ? 'outline' : ''}" id="pub">
        ${published ? 'Unpublish' : 'Send to Tenant'}</button>
    </div>
  </div>${nav('bills')}`;
  document.getElementById('pdf').onclick = () =>
    downloadPdf(`/bills/${id}/pdf`, `bill-${id}.pdf`).catch((e) => alert(e.message));
  document.getElementById('paid').onclick = async () => {
    await api(`/bills/${id}/mark-paid`, { method: 'POST' }); staffBillView(id);
  };
  document.getElementById('pub').onclick = async () => {
    try {
      await api(`/bills/${id}/${published ? 'unpublish' : 'publish'}`, { method: 'POST' });
      staffBillView(id);
    } catch (e) {
      document.getElementById('err').innerHTML = `<div class="error">${esc(e.message)}</div>`;
    }
  };
  document.getElementById('edit-charges')?.addEventListener('click', async () => {
    const lines = [];
    for (const l of b.charge_lines) {
      const v = prompt(`${l.label} (₹, empty to remove):`, l.amount_paise / 100);
      if (v === null) { lines.push(l); continue; }
      if (v.trim() === '') continue;
      lines.push({ label: l.label, amount_paise: Math.round(parseFloat(v) * 100) });
    }
    try {
      await api(`/bills/${id}/charges`, { method: 'PUT', body: lines });
      staffBillView(id);
    } catch (e) { alert(e.message); }
  });
}

async function tenantsView() {
  const [tenants, units] = await Promise.all([api('/tenants'), api('/units')]);
  const unitName = (id) => units.find((u) => u.id === id)?.name || '—';
  app.innerHTML = `${header('Tenants', '#/more')}
  <div class="page">
    <div class="card">
      <h2>Tenants on My Floors</h2>
      ${tenants.map((t) => `
        <div class="list-row">
          <div class="icon">👤</div>
          <div><div class="title">${esc(t.name)}</div>
            <div class="sub">${esc(t.email)} · ${esc(unitName(t.unit_id))}</div></div>
          <div class="right"><button class="link" data-tenant="${t.id}">${t.is_active ? 'Deactivate' : 'Activate'}</button></div>
        </div>`).join('') || '<p class="note">No tenants on your floors.</p>'}
    </div>
    <div class="card">
      <h2>Add Tenant (your floors only)</h2>
      <label class="field">Name<input id="t-name"></label>
      <label class="field">Email<input id="t-email" type="email"></label>
      <label class="field">Password<input id="t-pw" type="password" placeholder="min 8 chars"></label>
      <label class="field">Unit<select id="t-unit">${units.map((u) =>
        `<option value="${u.id}">${esc(u.name)}</option>`).join('')}</select></label>
      <div id="err"></div>
      <button class="btn" id="add">Add Tenant</button>
    </div>
  </div>${nav('more')}`;
  document.getElementById('add').onclick = async () => {
    try {
      await api('/tenants', { method: 'POST', body: {
        name: document.getElementById('t-name').value.trim(),
        email: document.getElementById('t-email').value.trim(),
        password: document.getElementById('t-pw').value,
        unit_id: +document.getElementById('t-unit').value,
      } });
      tenantsView();
    } catch (e) {
      document.getElementById('err').innerHTML = `<div class="error">${esc(e.message)}</div>`;
    }
  };
  document.querySelectorAll('[data-tenant]').forEach((btn) =>
    btn.addEventListener('click', async () => {
      const t = tenants.find((x) => x.id === +btn.dataset.tenant);
      await api(`/tenants/${t.id}`, { method: 'PATCH', body: { is_active: !t.is_active } });
      tenantsView();
    }));
}

async function moreView() {
  app.innerHTML = `${header('More')}
  <div class="page"><div class="card">
    <div class="list-row" onclick="location.hash='#/tenants'">
      <div class="icon">👥</div><div class="title">Manage Tenants</div><div class="right">›</div></div>
    <div class="list-row" id="logout">
      <div class="icon" style="background:#fee2e2">🚪</div><div class="title">Log out</div></div>
    <p class="note" style="margin-top:12px">Admins, rates, shares and unit settings are managed in the Superuser console.</p>
  </div></div>${nav('more')}`;
  document.getElementById('logout').onclick = () => { clearSession(); location.hash = '#/login'; route(); };
}

// ---------- router ----------
const adminRoutes = [
  [/^#\/?$/, homeView],
  [/^#\/meters$/, metersView],
  [/^#\/add-reading/, (m, params) => addReadingView(params)],
  [/^#\/generate$/, generateView],
  [/^#\/bills$/, billsView],
  [/^#\/staff-bill\/(\d+)$/, (m) => staffBillView(+m[1])],
  [/^#\/tenants$/, tenantsView],
  [/^#\/more$/, moreView],
];
const tenantRoutes = [
  [/^#\/?$/, myBillsView],
  [/^#\/bill\/(\d+)$/, (m) => myBillView(+m[1])],
  [/^#\/profile$/, profileView],
];

async function route() {
  const hash = location.hash || '#/';
  if (!getToken()) {
    if (hash !== '#/login') { location.hash = '#/login'; return; }
    loginView();
    return;
  }
  if (hash === '#/login') { location.hash = '#/'; return; }
  const [path, query] = hash.split('?');
  const params = new URLSearchParams(query || '');
  const routes = isAdmin() ? adminRoutes : tenantRoutes;
  for (const [re, view] of routes) {
    const m = path.match(re);
    if (m) {
      try { await view(m, params); } catch (e) { fail(e); }
      return;
    }
  }
  location.hash = '#/';
}

window.addEventListener('hashchange', route);
route();
