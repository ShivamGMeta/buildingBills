import './style.css';
import {
  api, clearSession, downloadPdf, getName, getToken, monthLabel, rupees, setSession,
} from './api.js';

const app = document.getElementById('app');
const state = { periods: [], periodId: null, units: [] };

// ---------- tiny helpers ----------
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function header(title, back = null, right = '') {
  return `<div class="header">
    ${back ? `<button class="iconbtn" onclick="location.hash='${back}'">‹</button>` : ''}
    <div class="grow"><h1>${esc(title)}</h1>
      ${back ? '' : `<div class="sub">Superuser · ${esc(getName() || '')}</div>`}</div>
    ${right}
  </div>`;
}

function nav(active) {
  const item = (href, icon, label, key) =>
    `<a href="${href}" class="${active === key ? 'active' : ''}">
       <span class="nicon">${icon}</span>${label}</a>`;
  return `<div class="bottomnav">
    ${item('#/', '🏠', 'Home', 'home')}
    ${item('#/meters', '📟', 'Meters', 'meters')}
    <button class="fab" onclick="location.hash='#/add-reading'">+</button>
    ${item('#/bills', '📄', 'Bills', 'bills')}
    ${item('#/more', '⋯', 'More', 'more')}
  </div>`;
}

function periodTabs(onchangeRoute) {
  return `<div class="pill-tabs">${state.periods.map((p) =>
    `<button class="pill ${p.id === state.periodId ? 'active' : ''}"
       data-period="${p.id}">${monthLabel(p)}</button>`).join('')}
    <button class="pill" id="new-period">+ Month</button>
  </div>`;
}

function bindPeriodTabs(rerender) {
  document.querySelectorAll('[data-period]').forEach((el) =>
    el.addEventListener('click', () => { state.periodId = +el.dataset.period; rerender(); }));
  document.getElementById('new-period')?.addEventListener('click', async () => {
    const ym = prompt('New billing month (YYYY-MM):');
    if (!ym) return;
    const [y, m] = ym.split('-').map(Number);
    try {
      const p = await api('/periods', { method: 'POST', body: { year: y, month: m } });
      await loadPeriods();
      state.periodId = p.id;
      rerender();
    } catch (e) { alert(e.message); }
  });
}

async function loadPeriods() {
  state.periods = await api('/periods');
  if (!state.periodId && state.periods.length) state.periodId = state.periods[0].id;
}

const currentPeriod = () => state.periods.find((p) => p.id === state.periodId);

function fail(e) {
  app.innerHTML = `${header('Building Bills')}
    <div class="page"><div class="error">${esc(e.message)}</div></div>${nav('')}`;
}

// ---------- views ----------
async function loginView() {
  app.innerHTML = `<div class="login-wrap"><div class="login-card">
    <h1>Building Bills</h1>
    <div class="sub">Superuser console — sign in</div>
    <div id="err"></div>
    <label class="field">Email<input id="email" type="email" autocomplete="username"></label>
    <label class="field">Password<input id="pw" type="password" autocomplete="current-password"></label>
    <button class="btn" id="go">Sign in</button>
  </div></div>`;
  document.getElementById('go').onclick = async () => {
    try {
      const body = {
        email: document.getElementById('email').value.trim(),
        password: document.getElementById('pw').value,
      };
      const session = await api('/auth/login', { method: 'POST', body });
      if (session.role !== 'superuser') {
        throw new Error('This console is for the Superuser. Use the Tenant & Admin app.');
      }
      setSession(session);
      location.hash = '#/';
    } catch (e) {
      document.getElementById('err').innerHTML = `<div class="error">${esc(e.message)}</div>`;
    }
  };
}

async function homeView() {
  await loadPeriods();
  const d = await api(`/dashboard${state.periodId ? `?period_id=${state.periodId}` : ''}`);
  const pct = d.total_billed_paise
    ? Math.round((d.total_collected_paise / d.total_billed_paise) * 100) : 0;
  app.innerHTML = `${header('Building Bills')}
  <div class="page">
    <div class="card row">
      <div class="grow">
        <div class="sub" style="color:var(--muted);font-weight:700">${monthLabel(d.period)} · Total Billed</div>
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
        <button onclick="location.hash='#/settings'"><div class="qicon" style="background:#fef3c7">⚙️</div>Settings</button>
      </div>
    </div>
    <div class="card">
      <div class="section-head"><h2>Summary</h2>
        <span class="badge published">${monthLabel(d.period)}</span></div>
      <div class="kv"><span class="k">⚡ Total Units Consumed</span><span class="v">${d.total_units_consumed.toLocaleString('en-IN')} kWh</span></div>
      <div class="kv"><span class="k">🔌 Total Electricity Bill</span><span class="v">${rupees(d.total_electricity_paise)}</span></div>
      <div class="kv"><span class="k">🏠 Total Other Charges</span><span class="v">${rupees(d.total_other_charges_paise)}</span></div>
      <div class="kv"><span class="k">📊 Total Bills Generated</span><span class="v">${rupees(d.total_billed_paise)}</span></div>
      <div class="kv"><span class="k">💰 Collected</span><span class="v">${rupees(d.total_collected_paise)}</span></div>
    </div>
  </div>${nav('home')}`;
}

async function metersView() {
  await loadPeriods();
  state.units = await api('/units');
  const readings = state.periodId ? await api(`/readings?period_id=${state.periodId}`) : [];
  const byUnit = Object.fromEntries(readings.map((r) => [r.unit_id, r]));
  // previous period readings for the delta
  const idx = state.periods.findIndex((p) => p.id === state.periodId);
  const prevPeriod = state.periods[idx + 1];
  const prev = prevPeriod
    ? Object.fromEntries((await api(`/readings?period_id=${prevPeriod.id}`))
        .map((r) => [r.unit_id, r])) : {};
  app.innerHTML = `${header('Meters & Readings')}
  <div class="page">
    ${periodTabs()}
    <div class="card">
      ${state.units.map((u) => {
        const r = byUnit[u.id];
        const base = prev[u.id]?.reading ?? u.opening_reading;
        const delta = r ? r.reading - base : null;
        return `<div class="list-row" onclick="location.hash='#/add-reading?unit=${u.id}'">
          <div class="icon">${u.has_ev ? '🔌' : '🏢'}</div>
          <div><div class="title">${esc(u.name)}</div>
               <div class="sub">${esc(u.meter_no)} · share ${(u.common_share_bps / 100).toFixed(0)}%${u.has_ev ? ' · EV' : ''}</div></div>
          <div class="right">
            <div class="big">${r ? `${r.reading.toLocaleString('en-IN')} kWh` : '—'}</div>
            ${delta !== null ? `<div class="delta">↑ ${delta} units</div>` : `<div class="sub">no reading</div>`}
          </div>
        </div>`;
      }).join('')}
    </div>
    <div class="card">
      <div class="kv"><span class="k">Common-area units (lift/parking)</span>
        <span class="v">${currentPeriod()?.common_area_units ?? 0} kWh</span></div>
      <div class="kv"><span class="k">EV charging units</span>
        <span class="v">${currentPeriod()?.ev_units ?? 0} kWh</span></div>
      <button class="link" onclick="location.hash='#/settings'">Edit in Settings →</button>
    </div>
  </div>${nav('meters')}`;
  bindPeriodTabs(metersView);
}

async function addReadingView(params) {
  await loadPeriods();
  state.units = await api('/units');
  const preselect = +params.get('unit') || state.units[0]?.id;
  const today = new Date().toISOString().slice(0, 10);
  app.innerHTML = `${header('Add Meter Reading', '#/meters')}
  <div class="page"><div class="card">
    <label class="field">Billing month
      <select id="period">${state.periods.map((p) =>
        `<option value="${p.id}" ${p.id === state.periodId ? 'selected' : ''}>${monthLabel(p)}</option>`).join('')}
      </select></label>
    <label class="field">Meter
      <select id="unit">${state.units.map((u) =>
        `<option value="${u.id}" ${u.id === preselect ? 'selected' : ''}>${esc(u.name)} — ${esc(u.meter_no)}</option>`).join('')}
      </select></label>
    <label class="field">Current reading (kWh)<input id="reading" type="number" min="0" inputmode="numeric"></label>
    <label class="field">Reading date<input id="rdate" type="date" value="${today}"></label>
    <label class="field">Notes (optional)<input id="note" placeholder="Add any notes..."></label>
    <div id="err"></div>
    <button class="btn" id="save">✓ Save Reading</button>
    <p class="note" style="margin-top:10px">Phase 2 will read the meter photo automatically — manual entry always stays available.</p>
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
      <div class="row">
        <div class="grow"><b>Electricity Rate</b>
          <div class="sub" style="color:var(--muted)">${rupees(p?.rate_paise ?? 0)} per unit</div></div>
        <button class="btn small outline" style="border-color:var(--green);color:var(--green)" id="edit-rate">Edit Rate</button>
      </div>
    </div>
    <div class="card">
      <h2>Include in Bill</h2>
      <div class="sub" style="color:var(--muted);margin-bottom:8px">
        Defaults come from charge templates; amounts apply to every bill this run.
        Per-flat tweaks: open the draft bill after generating.</div>
      ${templates.filter((t) => t.is_active).map((t) => `
        <div class="checkrow">
          <input type="checkbox" checked data-tpl="${t.id}">
          <span class="lbl">${esc(t.label)}</span>
          <input type="number" min="0" value="${t.default_amount_paise / 100}" data-amt="${t.id}">
        </div>`).join('')}
    </div>
    <div id="err"></div>
    <button class="btn" id="gen">Generate Bills</button>
    <p class="note">Draft bills will be generated for all floors. Published bills are never overwritten.</p>
  </div>${nav('bills')}`;
  bindPeriodTabs(generateView);
  document.getElementById('edit-rate').onclick = async () => {
    const v = prompt('New rate (₹ per unit):', (p.rate_paise / 100).toFixed(2));
    if (!v) return;
    try {
      await api(`/periods/${p.id}`, { method: 'PATCH',
        body: { rate_paise: Math.round(parseFloat(v) * 100) } });
      await loadPeriods(); generateView();
    } catch (e) { alert(e.message); }
  };
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
        <div class="list-row" onclick="location.hash='#/bill/${b.id}'">
          <div class="icon">📄</div>
          <div><div class="title">${esc(b.unit_name)}${b.tenant_name ? ` (${esc(b.tenant_name)})` : ''}</div>
            <div class="sub">${b.billable_units} units · <span class="badge ${b.status}">${b.status.toUpperCase()}</span>
            ${b.is_paid ? '<span class="badge paid">PAID</span>' : ''}</div></div>
          <div class="right"><div class="big">${rupees(b.total_paise)}</div></div>
        </div>`).join('')
      : `<p class="note">No bills yet for this month — generate them first.</p>`}
    </div>
    <button class="btn" onclick="location.hash='#/generate'">Generate Bills</button>
  </div>${nav('bills')}`;
  bindPeriodTabs(billsView);
}

async function billView(id) {
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
      <div id="charges">
      ${b.charge_lines.map((l) => `
        <div class="kv"><span class="k">${esc(l.label)}</span><span class="v">${rupees(l.amount_paise)}</span></div>`).join('')}
      </div>
      <div class="kv total"><span class="k">Total Amount</span><span class="v">${rupees(b.total_paise)}</span></div>
    </div>
    <div id="err"></div>
    <div class="btnrow">
      <button class="btn green" id="paid">${b.is_paid ? '↺ Mark Unpaid' : '✓ Mark as Paid'}</button>
      <button class="btn ${published ? 'outline' : ''}" id="pub">
        ${published ? 'Unpublish' : 'Send to Tenant'}</button>
    </div>
    ${published ? `<p class="note">Published ${new Date(b.published_at).toLocaleDateString()}. This bill is a frozen snapshot — unpublish to edit.</p>`
                : `<p class="note">Draft — recomputes live as readings, rate or charges change. “Send to Tenant” publishes it and emails the tenant.</p>`}
  </div>${nav('bills')}`;

  document.getElementById('pdf').onclick = () =>
    downloadPdf(`/bills/${id}/pdf`, `bill-${id}.pdf`).catch((e) => alert(e.message));
  document.getElementById('paid').onclick = async () => {
    await api(`/bills/${id}/mark-paid`, { method: 'POST' }); billView(id);
  };
  document.getElementById('pub').onclick = async () => {
    try {
      await api(`/bills/${id}/${published ? 'unpublish' : 'publish'}`, { method: 'POST' });
      billView(id);
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
    const extra = prompt('Add another charge? (label:amount, or leave empty)');
    if (extra?.includes(':')) {
      const [label, amt] = extra.split(':');
      lines.push({ label: label.trim(), amount_paise: Math.round(parseFloat(amt) * 100) });
    }
    try {
      await api(`/bills/${id}/charges`, { method: 'PUT', body: lines });
      billView(id);
    } catch (e) { alert(e.message); }
  });
}

async function adminsView() {
  const [admins, units] = await Promise.all([api('/admins'), api('/units')]);
  const unitName = (id) => units.find((u) => u.id === id)?.name || `#${id}`;
  app.innerHTML = `${header('Admins', '#/more')}
  <div class="page">
    <div class="card">
      <h2>Floor Admins</h2>
      ${admins.length ? admins.map((a) => `
        <div class="list-row" data-admin="${a.id}">
          <div class="icon">🧑‍💼</div>
          <div><div class="title">${esc(a.name)} ${a.is_active ? '' : '<span class="badge unpaid">INACTIVE</span>'}</div>
            <div class="sub">${esc(a.email)}<br>Floors: ${a.unit_ids.map(unitName).map(esc).join(', ') || 'none'}</div></div>
          <div class="right"><button class="link">Edit</button></div>
        </div>`).join('') : '<p class="note">No admins yet.</p>'}
    </div>
    <div class="card">
      <h2>Add Admin</h2>
      <label class="field">Name<input id="a-name"></label>
      <label class="field">Email<input id="a-email" type="email"></label>
      <label class="field">Password<input id="a-pw" type="password" placeholder="min 8 chars"></label>
      <label class="field">Assigned floors</label>
      ${units.map((u) => `<div class="checkrow">
        <input type="checkbox" data-scope="${u.id}"><span class="lbl">${esc(u.name)}</span></div>`).join('')}
      <div id="err"></div>
      <button class="btn" id="add" style="margin-top:10px">Add Admin</button>
    </div>
  </div>${nav('more')}`;
  document.getElementById('add').onclick = async () => {
    try {
      await api('/admins', { method: 'POST', body: {
        name: document.getElementById('a-name').value.trim(),
        email: document.getElementById('a-email').value.trim(),
        password: document.getElementById('a-pw').value,
        unit_ids: units.filter((u) => document.querySelector(`[data-scope="${u.id}"]`).checked)
          .map((u) => u.id),
      } });
      adminsView();
    } catch (e) {
      document.getElementById('err').innerHTML = `<div class="error">${esc(e.message)}</div>`;
    }
  };
  document.querySelectorAll('[data-admin]').forEach((row) =>
    row.querySelector('.link').addEventListener('click', async () => {
      const a = admins.find((x) => x.id === +row.dataset.admin);
      const ids = prompt(
        `Floors for ${a.name} (comma-separated unit ids)\n${units.map((u) => `${u.id}=${u.name}`).join(', ')}`,
        a.unit_ids.join(','));
      if (ids === null) return;
      const active = confirm('Keep this admin active? OK = active, Cancel = deactivate');
      try {
        await api(`/admins/${a.id}`, { method: 'PATCH', body: {
          unit_ids: ids.split(',').map((s) => +s.trim()).filter(Boolean),
          is_active: active,
        } });
        adminsView();
      } catch (e) { alert(e.message); }
    }));
}

async function tenantsView() {
  const [tenants, units] = await Promise.all([api('/tenants'), api('/units')]);
  const unitName = (id) => units.find((u) => u.id === id)?.name || '—';
  app.innerHTML = `${header('Tenants', '#/more')}
  <div class="page">
    <div class="card">
      <h2>Tenants</h2>
      ${tenants.map((t) => `
        <div class="list-row">
          <div class="icon">👤</div>
          <div><div class="title">${esc(t.name)} ${t.is_active ? '' : '<span class="badge unpaid">INACTIVE</span>'}</div>
            <div class="sub">${esc(t.email)} · ${esc(unitName(t.unit_id))}</div></div>
          <div class="right"><button class="link" data-tenant="${t.id}">${t.is_active ? 'Deactivate' : 'Activate'}</button></div>
        </div>`).join('') || '<p class="note">No tenants yet.</p>'}
    </div>
    <div class="card">
      <h2>Add Tenant</h2>
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

async function settingsView() {
  await loadPeriods();
  const [units, templates] = await Promise.all([api('/units'), api('/charge-templates')]);
  const p = currentPeriod();
  const totalShare = units.reduce((s, u) => s + u.common_share_bps, 0);
  app.innerHTML = `${header('Building Settings', '#/more')}
  <div class="page">
    ${periodTabs()}
    <div class="card">
      <h2>${monthLabel(p)} inputs</h2>
      <label class="field">Electricity rate (₹/unit)
        <input id="rate" type="number" step="0.01" value="${(p?.rate_paise ?? 0) / 100}"></label>
      <label class="field">Common-area units — lift & parking (kWh)
        <input id="common" type="number" min="0" value="${p?.common_area_units ?? 0}"></label>
      <label class="field">EV charging units (kWh)
        <input id="ev" type="number" min="0" value="${p?.ev_units ?? 0}"></label>
      <button class="btn" id="save-period">Save Month Inputs</button>
      <p class="note">Changing these recomputes DRAFT bills only — published bills stay frozen.</p>
    </div>
    <div class="card">
      <h2>Units & Shares ${totalShare !== 10000 ? '<span class="badge unpaid">shares ≠ 100%</span>' : ''}</h2>
      ${units.map((u) => `
        <div class="checkrow" data-unit="${u.id}">
          <span class="lbl">${esc(u.name)}${u.has_ev ? ' 🔌' : ''}</span>
          <input type="number" min="0" max="100" step="0.01" value="${u.common_share_bps / 100}" data-share="${u.id}" title="common share %">
        </div>`).join('')}
      <button class="btn" id="save-shares" style="margin-top:10px">Save Shares (%)</button>
      <p class="note">Shares & EV ownership are data on the flat — used for every future bill.</p>
    </div>
    <div class="card">
      <h2>Charge Templates</h2>
      ${templates.map((t) => `
        <div class="checkrow">
          <input type="checkbox" ${t.is_active ? 'checked' : ''} data-tact="${t.id}">
          <span class="lbl">${esc(t.label)}</span>
          <input type="number" min="0" value="${t.default_amount_paise / 100}" data-tamt="${t.id}">
        </div>`).join('')}
      <div class="row" style="margin-top:10px">
        <input id="new-label" placeholder="New charge label">
        <input id="new-amt" type="number" min="0" placeholder="₹" style="width:110px">
      </div>
      <button class="btn" id="save-templates" style="margin-top:10px">Save Templates</button>
    </div>
  </div>${nav('more')}`;
  bindPeriodTabs(settingsView);
  document.getElementById('save-period').onclick = async () => {
    try {
      await api(`/periods/${p.id}`, { method: 'PATCH', body: {
        rate_paise: Math.round(+document.getElementById('rate').value * 100),
        common_area_units: +document.getElementById('common').value,
        ev_units: +document.getElementById('ev').value,
      } });
      await loadPeriods(); settingsView();
    } catch (e) { alert(e.message); }
  };
  document.getElementById('save-shares').onclick = async () => {
    try {
      for (const u of units) {
        const bps = Math.round(+document.querySelector(`[data-share="${u.id}"]`).value * 100);
        if (bps !== u.common_share_bps) {
          await api(`/units/${u.id}`, { method: 'PATCH', body: { common_share_bps: bps } });
        }
      }
      settingsView();
    } catch (e) { alert(e.message); }
  };
  document.getElementById('save-templates').onclick = async () => {
    try {
      for (const t of templates) {
        await api(`/charge-templates/${t.id}`, { method: 'PATCH', body: {
          label: t.label,
          default_amount_paise: Math.round(+document.querySelector(`[data-tamt="${t.id}"]`).value * 100),
          is_active: document.querySelector(`[data-tact="${t.id}"]`).checked,
        } });
      }
      const label = document.getElementById('new-label').value.trim();
      if (label) {
        await api('/charge-templates', { method: 'POST', body: {
          label, default_amount_paise: Math.round(+document.getElementById('new-amt').value * 100 || 0),
        } });
      }
      settingsView();
    } catch (e) { alert(e.message); }
  };
}

async function moreView() {
  app.innerHTML = `${header('More')}
  <div class="page"><div class="card">
    <div class="list-row" onclick="location.hash='#/admins'">
      <div class="icon">🧑‍💼</div><div class="title">Manage Admins</div><div class="right">›</div></div>
    <div class="list-row" onclick="location.hash='#/tenants'">
      <div class="icon">👥</div><div class="title">Manage Tenants</div><div class="right">›</div></div>
    <div class="list-row" onclick="location.hash='#/settings'">
      <div class="icon">⚙️</div><div class="title">Building Settings</div><div class="right">›</div></div>
    <div class="list-row" id="logout">
      <div class="icon" style="background:#fee2e2">🚪</div><div class="title">Log out</div></div>
  </div></div>${nav('more')}`;
  document.getElementById('logout').onclick = () => { clearSession(); location.hash = '#/login'; };
}

// ---------- router ----------
const routes = [
  [/^#\/login$/, loginView],
  [/^#\/?$/, homeView],
  [/^#\/meters$/, metersView],
  [/^#\/add-reading/, (m, params) => addReadingView(params)],
  [/^#\/generate$/, generateView],
  [/^#\/bills$/, billsView],
  [/^#\/bill\/(\d+)$/, (m) => billView(+m[1])],
  [/^#\/admins$/, adminsView],
  [/^#\/tenants$/, tenantsView],
  [/^#\/settings$/, settingsView],
  [/^#\/more$/, moreView],
];

async function route() {
  const hash = location.hash || '#/';
  if (!getToken() && hash !== '#/login') { location.hash = '#/login'; return; }
  const [path, query] = hash.split('?');
  const params = new URLSearchParams(query || '');
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
