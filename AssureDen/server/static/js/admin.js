/**
 * admin.js — AssureDen Admin Center CRUD logic
 * Handles all 4 entity tabs: Users, Applications, Modules, Cases
 */

const T = localStorage.getItem('ad_token');
if (!T) window.location.href = '/login';
const H = { 'Authorization': `Bearer ${T}`, 'Content-Type': 'application/json' };

function logout() { localStorage.removeItem('ad_token'); window.location.href = '/login'; }

fetch('/api/auth/me', { headers: H }).then(r => r.json())
    .then(u => { document.getElementById('userName').textContent = u.username; });

// ── Tab switching ─────────────────────────────────────────
const LOADERS = { users: loadUsers, applications: loadApps, modules: loadMods, cases: loadCases };

function sw(name, el) {
    document.querySelectorAll('.tab-view').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.subnav-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
    el.classList.add('active');
    if (LOADERS[name]) LOADERS[name]();
}

// Handle URL hash on load
window.addEventListener('load', () => {
    const hash = location.hash.replace('#', '');
    const btn = document.getElementById('btn-' + hash);
    if (btn) { sw(hash, btn); }
    else { loadUsers(); loadModsForDropdowns(); }
});

// ── Modal helpers ─────────────────────────────────────────
function openM(id) { document.getElementById(id).classList.add('open'); }
function closeM(id) { document.getElementById(id).classList.remove('open'); }
function showErr(id, msg) { const el = document.getElementById(id); el.textContent = msg; el.style.display = 'block'; }
function hideErr(id) { document.getElementById(id).style.display = 'none'; }
function fv(id) { return document.getElementById(id).value.trim(); }
function fe(id) { return document.getElementById(id).value; }

// ── USERS ─────────────────────────────────────────────────
async function loadUsers() {
    const tbody = document.getElementById('tbody-users');
    const res = await fetch('/api/admin/users', { headers: H });
    const users = await res.json();
    if (!users.length) { tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-secondary);">No users found.</td></tr>`; return; }
    tbody.innerHTML = users.map(u => `<tr>
        <td style="font-weight:600;color:var(--text-primary);">${u.username}</td>
        <td style="color:var(--text-secondary);">${u.email}</td>
        <td><span class="badge badge-${u.role.toLowerCase()}">${u.role}</span></td>
        <td><span class="badge ${u.is_active ? 'badge-active' : 'badge-inactive'}">${u.is_active ? 'Active' : 'Disabled'}</span></td>
        <td style="color:var(--text-secondary);font-size:0.8rem;">${u.created_at ? new Date(u.created_at).toLocaleDateString() : '-'}</td>
        <td>
            <button class="btn btn-secondary btn-sm" onclick="toggleUser('${u.id}',${u.is_active})">${u.is_active ? 'Disable' : 'Enable'}</button>
            <button class="btn btn-danger btn-sm" onclick="deleteUser('${u.id}','${u.username}')">Delete</button>
        </td></tr>`).join('');
}

async function createUser() {
    hideErr('u-err');
    const payload = { username: fv('u-username'), email: fv('u-email'), password: document.getElementById('u-pass').value, role: fe('u-role') };
    if (!payload.username || !payload.email || !payload.password) { showErr('u-err', 'All fields required.'); return; }
    const res = await fetch('/api/admin/users', { method: 'POST', headers: H, body: JSON.stringify(payload) });
    if (res.ok) { closeM('mUser'); loadUsers();['u-username', 'u-email', 'u-pass'].forEach(i => document.getElementById(i).value = ''); }
    else { const e = await res.json(); showErr('u-err', e.detail || 'Failed.'); }
}

async function toggleUser(id, active) {
    await fetch(`/api/admin/users/${id}`, { method: 'PATCH', headers: H, body: JSON.stringify({ is_active: !active }) });
    loadUsers();
}

async function deleteUser(id, name) {
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    await fetch(`/api/admin/users/${id}`, { method: 'DELETE', headers: H });
    loadUsers();
}

// ── APPLICATIONS ──────────────────────────────────────────
async function loadApps() {
    const tbody = document.getElementById('tbody-applications');
    const res = await fetch('/api/admin/applications', { headers: H });
    const apps = await res.json();
    if (!apps.length) { tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-secondary);">No applications registered.</td></tr>`; return; }
    tbody.innerHTML = apps.map(a => `<tr>
        <td style="font-weight:600;color:var(--text-primary);">${a.name}</td>
        <td><span class="badge badge-${a.app_type.toLowerCase()}">${a.app_type}</span></td>
        <td style="color:var(--text-secondary);">${a.vendor || '-'}</td>
        <td style="color:var(--text-secondary);font-size:0.8rem;max-width:180px;overflow:hidden;text-overflow:ellipsis;">${a.base_url || '-'}</td>
        <td><span class="badge ${a.is_active ? 'badge-active' : 'badge-inactive'}">${a.is_active ? 'Active' : 'Inactive'}</span></td>
        <td><button class="btn btn-danger btn-sm" onclick="deleteApp('${a.id}','${a.name}')">Delete</button></td>
    </tr>`).join('');
}

async function createApp() {
    hideErr('a-err');
    const payload = { name: fv('a-name'), app_type: fe('a-type'), vendor: fv('a-vendor') || null, base_url: fv('a-url') || null, description: fv('a-desc') || null };
    if (!payload.name) { showErr('a-err', 'Name is required.'); return; }
    const res = await fetch('/api/admin/applications', { method: 'POST', headers: H, body: JSON.stringify(payload) });
    if (res.ok) { closeM('mApp'); loadApps();['a-name', 'a-vendor', 'a-url', 'a-desc'].forEach(i => document.getElementById(i).value = ''); }
    else { const e = await res.json(); showErr('a-err', e.detail || 'Failed.'); }
}

async function deleteApp(id, name) {
    if (!confirm(`Remove "${name}"?`)) return;
    await fetch(`/api/admin/applications/${id}`, { method: 'DELETE', headers: H });
    loadApps();
}

// ── TEST MODULES ──────────────────────────────────────────
let _modules = [];

async function loadMods() {
    const tbody = document.getElementById('tbody-modules');
    const res = await fetch('/api/admin/modules', { headers: H });
    _modules = await res.json();
    if (!_modules.length) { tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-secondary);">No modules registered.</td></tr>`; return; }
    tbody.innerHTML = _modules.map(m => `<tr>
        <td><span class="badge badge-${m.domain.toLowerCase()}">${m.domain}</span></td>
        <td style="font-weight:600;color:var(--text-primary);">${m.name}</td>
        <td style="font-family:monospace;font-size:0.78rem;color:var(--text-secondary);">${m.action_key}</td>
        <td style="color:var(--text-secondary);font-size:0.8rem;">${m.url_path || '-'}</td>
        <td><span class="badge ${m.is_active ? 'badge-active' : 'badge-inactive'}">${m.is_active ? 'Active' : 'Inactive'}</span></td>
        <td>
            <button class="btn btn-secondary btn-sm" onclick="toggleMod('${m.id}',${m.is_active})">${m.is_active ? 'Disable' : 'Enable'}</button>
            <button class="btn btn-danger btn-sm" onclick="deleteMod('${m.id}','${m.name}')">Delete</button>
        </td></tr>`).join('');
}

async function createMod() {
    hideErr('m-err');
    const payload = { domain: fe('m-domain'), name: fv('m-name'), action_key: fv('m-key'), url_path: fv('m-url') || null, description: fv('m-desc') || null };
    if (!payload.name || !payload.action_key) { showErr('m-err', 'Name and Action Key required.'); return; }
    const res = await fetch('/api/admin/modules', { method: 'POST', headers: H, body: JSON.stringify(payload) });
    if (res.ok) { closeM('mMod'); loadMods();['m-name', 'm-key', 'm-url', 'm-desc'].forEach(i => document.getElementById(i).value = ''); }
    else { const e = await res.json(); showErr('m-err', e.detail || 'Failed.'); }
}

async function toggleMod(id, active) {
    await fetch(`/api/admin/modules/${id}`, { method: 'PATCH', headers: H, body: JSON.stringify({ is_active: !active }) });
    loadMods();
}

async function deleteMod(id, name) {
    if (!confirm(`Delete module "${name}"?`)) return;
    await fetch(`/api/admin/modules/${id}`, { method: 'DELETE', headers: H });
    loadMods();
}

// ── TEST CASES ────────────────────────────────────────────
async function loadModsForDropdowns() {
    const res = await fetch('/api/admin/modules', { headers: H });
    _modules = await res.json();
    ['c-module', 'caseModFilter'].forEach(selectId => {
        const sel = document.getElementById(selectId);
        if (!sel) return;
        const preserveFirst = selectId === 'caseModFilter';
        if (!preserveFirst) sel.innerHTML = '';
        _modules.forEach(m => {
            const o = document.createElement('option');
            o.value = m.id; o.textContent = `[${m.domain}] ${m.name}`;
            sel.appendChild(o);
        });
    });
}

async function loadCases() {
    const tbody = document.getElementById('tbody-cases');
    const modId = document.getElementById('caseModFilter')?.value || '';
    const url = modId ? `/api/admin/cases?module_id=${modId}` : '/api/admin/cases';
    const res = await fetch(url, { headers: H });
    const cases = await res.json();
    const modMap = Object.fromEntries(_modules.map(m => [m.id, m.name]));
    if (!cases.length) { tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-secondary);">No test cases found.</td></tr>`; return; }
    tbody.innerHTML = cases.map(c => `<tr>
        <td style="font-weight:600;color:var(--text-primary);">${c.name}</td>
        <td style="color:var(--text-secondary);">${modMap[c.module_id] || c.module_id}</td>
        <td><span class="badge badge-${c.priority.toLowerCase()}">${c.priority}</span></td>
        <td><span class="badge ${c.is_active ? 'badge-active' : 'badge-inactive'}">${c.is_active ? 'Active' : 'Inactive'}</span></td>
        <td style="color:var(--text-secondary);font-size:0.8rem;">${c.created_at ? new Date(c.created_at).toLocaleDateString() : '-'}</td>
        <td><button class="btn btn-danger btn-sm" onclick="deleteCase('${c.id}','${c.name}')">Delete</button></td>
    </tr>`).join('');
}

async function createCase() {
    hideErr('c-err');
    const stepsRaw = document.getElementById('c-steps').value.trim();
    const stepsArr = stepsRaw ? stepsRaw.split('\n').filter(s => s.trim()) : [];
    const payload = { module_id: fe('c-module'), name: fv('c-name'), priority: fe('c-priority'), description: fv('c-desc') || null, steps: JSON.stringify(stepsArr), expected_result: fv('c-expected') || null };
    if (!payload.module_id || !payload.name) { showErr('c-err', 'Module and Name required.'); return; }
    const res = await fetch('/api/admin/cases', { method: 'POST', headers: H, body: JSON.stringify(payload) });
    if (res.ok) { closeM('mCase'); loadCases();['c-name', 'c-desc', 'c-steps', 'c-expected'].forEach(i => document.getElementById(i).value = ''); }
    else { const e = await res.json(); showErr('c-err', e.detail || 'Failed.'); }
}

async function deleteCase(id, name) {
    if (!confirm(`Delete case "${name}"?`)) return;
    await fetch(`/api/admin/cases/${id}`, { method: 'DELETE', headers: H });
    loadCases();
}
