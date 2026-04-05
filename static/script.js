// DOM refs
const statusBadge = document.getElementById('status-badge');
const statusText = document.getElementById('status-text');
const domainSubtitle = document.getElementById('domain-subtitle');
const servicesList = document.getElementById('services-list');
const activeCount = document.getElementById('active-count');
const smartFolderPath = document.getElementById('smart-folder-path');
const detectionDetails = document.getElementById('detection-details');
const projectTypeBadge = document.getElementById('project-type-badge');
const smartCommand = document.getElementById('smart-command');
const toastEl = document.getElementById('toast');
const depBar = document.getElementById('dep-bar');
const logViewer = document.getElementById('log-viewer');
const logContent = document.getElementById('log-content');
const logProjectName = document.getElementById('log-project-name');

let currentStatus = null;
let currentAnalytics = {};
let logInterval = null;
const metadataCache = {};

// ─── INIT ────────────────────────────────────────────────────────────────────
checkDependencies();
fetchStatus();
setInterval(fetchStatus, 5000);

// ─── DEPS ─────────────────────────────────────────────────────────────────────
async function checkDependencies() {
    try {
        const res = await fetch('/api/check_dependencies');
        const deps = await res.json();
        depBar.innerHTML = [
            { id: 'tailscale', label: 'Tailscale', icon: 'fa-shield-halved' },
            { id: 'node', label: 'Node.js', icon: 'fa-brands fa-node-js' },
            { id: 'python', label: 'Python', icon: 'fa-brands fa-python' },
        ].map(d => `
            <div class="dep-item ${deps[d.id] ? 'ready' : 'missing'}">
                <i class="fas ${d.icon}"></i> ${d.label}: ${deps[d.id] ? '✓ Bereit' : '✗ Fehlt'}
            </div>`).join('');
    } catch (e) { }
}

// ─── STATUS ───────────────────────────────────────────────────────────────────
async function fetchStatus() {
    try {
        const [statusRes, analyticsRes] = await Promise.all([
            fetch('/api/status'),
            fetch('/api/analytics')
        ]);
        currentStatus = await statusRes.json();
        currentAnalytics = await analyticsRes.json();
        updateUI();
    } catch (e) { }
}

function updateUI() {
    if (!currentStatus) return;
    const online = currentStatus.isLoggedIn;
    statusBadge.className = `status-badge ${online ? 'connected' : 'disconnected'}`;
    statusText.textContent = online ? 'Tailscale Online' : 'Nicht verbunden';

    const hostname = (currentStatus.nodeName || '').replace(/\.$/, '') || 'mediclean-pro.tail98157e.ts.net';
    const shortName = hostname.split('.')[0];
    domainSubtitle.innerHTML = `<a href="https://${hostname}" target="_blank" style="color:var(--cyan);text-decoration:none;"><i class="fas fa-link" style="font-size:0.8rem;margin-right:4px;"></i>${shortName}</a>`;

    renderSystemPorts();
    renderServices();
}

// ─── SYSTEM PORTS ─────────────────────────────────────────────────────────────
function renderSystemPorts() {
    const ports = currentStatus?.systemPorts || {};
    const keys = Object.keys(ports).map(Number).sort((a, b) => a - b);
    const container = document.getElementById('system-ports-grid');
    if (!container) return;

    if (keys.length === 0) {
        container.innerHTML = '<div style="color:var(--muted);font-size:0.8rem">Keine belegten Ports gefunden.</div>';
        return;
    }

    container.innerHTML = keys.slice(0, 15).map(p => `
        <div class="port-block busy" title="Port ${p}: ${ports[p]}">
            <span class="p-num">${p}</span>
            <span class="p-owner">${ports[p].substring(0, 8)}</span>
        </div>
    `).join('') + (keys.length > 15 ? `<div class="port-block more">+${keys.length - 15}</div>` : '');
}

// ─── RENDER SERVICES ──────────────────────────────────────────────────────────
function renderServices() {
    const managed = currentStatus?.managedProjects || {};
    const entries = Object.entries(managed);
    activeCount.textContent = entries.length;

    if (entries.length === 0) {
        servicesList.innerHTML = '<div class="empty-state">Noch keine aktiven Dienste. Füge unten einen hinzu.</div>';
        return;
    }

    const host = (currentStatus.nodeName || '').replace(/\.$/, '');
    servicesList.innerHTML = entries.map(([key, p]) => {
        const publicPort = p.publicPort || '443';
        const isPublic = publicPort !== 'tailnet';
        const servePath = p.serve_path || '';
        const port = p.port;
        const safePath = servePath ? (servePath.startsWith('/') ? servePath : '/' + servePath) : '';
        if (safePath === '/mediclean') {
            publicUrl = `https://${host}`;
        } else if (safePath) {
            publicUrl = `https://${host}:8443${safePath}`;
        } else {
            const urlPort = publicPort === '443' ? '' : `:${publicPort}`;
            publicUrl = isPublic ? `https://${host}${urlPort}/` : null;
        }

        // Trigger metadata fetch if not in cache
        if (!metadataCache[key] && port) {
            fetchServiceMetadata(key, port);
        }

        const meta = metadataCache[key] || {};
        const fallbackName = p.name || (safePath ? safePath : (p.path ? p.path.split(/[/\\]/).pop() : `Port ${p.port}`));
        const displayName = meta.title || fallbackName;
        const description = meta.description || '';
        const iconUrl = meta.icon;
        const iconHtml = iconUrl
            ? `<div class="service-icon-wrapper"><img src="${iconUrl}" onerror="this.src='';this.parentElement.innerHTML='<i class=\'fas fa-globe\'></i>'"></div>`
            : `<div class="service-icon-wrapper"><i class="fas ${p.icon || 'fa-globe'}"></i></div>`;

        const analytics = currentAnalytics[key] || { hits: 0, unique_ips: [], total_bytes: 0 };
        const hits = analytics.hits || 0;
        const unique = (analytics.unique_ips || []).length;
        const bandwidth = (analytics.total_bytes / (1024 * 1024)).toFixed(1); // MB
        const isHot = (Date.now() / 1000 - (analytics.last_hit || 0)) < 60;

        return `
        <div class="service-row" id="svc-${key}">
            ${iconHtml}
            <div class="service-left">
                <div class="service-title-row">
                    <div class="service-name">${displayName}</div>
                    <div class="health-dot ${p.pid ? 'running' : 'external'}" id="health-${key}" title="Status Check"></div>
                    ${publicUrl ? `<a href="${publicUrl}" target="_blank" class="service-url-link"><i class="fas fa-external-link-alt"></i> ${publicUrl}</a>` : '<span style="color:var(--amber);font-size:0.8rem"><i class="fas fa-lock"></i> Nur Tailnet</span>'}
                </div>
                ${description ? `<div class="service-description">${description}</div>` : ''}
                
                <div class="analytics-bar">
                    <div class="stat-item" title="Seit Start">
                        <i class="fas fa-chart-line stat-icon ${isHot ? 'traffic-pulse' : ''}"></i>
                        <span class="stat-label">Zugriffe:</span>
                        <span class="stat-value">${hits}</span>
                    </div>
                    <div class="stat-item" title="Eindeutige Tailscale IPs">
                        <i class="fas fa-users stat-icon"></i>
                        <span class="stat-label">Besucher:</span>
                        <span class="stat-value">${unique}</span>
                    </div>
                    <div class="stat-item" title="Datentransfer">
                        <i class="fas fa-database stat-icon"></i>
                        <span class="stat-label">Transfer:</span>
                        <span class="stat-value">${bandwidth} MB</span>
                    </div>
                </div>

                <div class="service-meta">
                    <span><i class="fas fa-plug"></i> Lokal: ${p.port}</span>
                    ${p.command ? `<span><i class="fas fa-terminal"></i> ${p.command}</span>` : ''}
                    ${safePath === '/mediclean' ? `<span class="port-pill public">via https://${host}</span>` : (safePath ? `<span class="port-pill public">via :8443${safePath}</span>` : `<span class="port-pill ${isPublic ? 'public' : ''}">:${publicPort}</span>`)}
                    ${publicUrl ? `<button onclick="copyToClipboard('${publicUrl}')" class="btn-icon-xs" title="URL kopieren"><i class="fas fa-copy"></i></button>` : ''}
                </div>
            </div>
            <div class="service-right">
                <button onclick="window.open('${publicUrl ? publicUrl : '#'}')" class="btn btn-sm btn-ghost-sm" ${!publicUrl ? 'disabled' : ''}><i class="fas fa-eye"></i> View</button>
                ${p.pid ? `<button onclick="viewLogs('${key}')" class="btn btn-sm btn-ghost-sm"><i class="fas fa-terminal"></i> Logs</button>` : ''}
                <button onclick="editPort('${key}', ${p.port})" class="btn btn-sm btn-ghost-sm"><i class="fas fa-cog"></i> Config</button>
                <button onclick="removeService('${key}')" class="btn btn-sm btn-danger-outline"><i class="fas fa-trash"></i></button>
            </div>
        </div>`;
    }).join('');
}

async function fetchServiceMetadata(key, port) {
    if (metadataCache[key] === 'loading') return;
    metadataCache[key] = 'loading';

    try {
        const res = await fetch(`/api/fetch_metadata?port=${port}&save=true`);
        const data = await res.json();
        if (data.status === 'success') {
            metadataCache[key] = data;
            // Partial update: only if the element is still there
            const row = document.getElementById(`svc-${key}`);
            if (row) {
                renderServices(); // Re-render all for simplicity, or we could surgically update
            }
        } else {
            metadataCache[key] = { error: true };
        }
    } catch (e) {
        metadataCache[key] = { error: true };
    }
}

// ─── ADD EXISTING APP ─────────────────────────────────────────────────────────
async function addExistingApp() {
    const localPort = parseInt(document.getElementById('existing-port').value);
    const publicPort = document.getElementById('existing-public-port').value;
    const servePath = document.getElementById('existing-serve-path').value.trim();

    if (!localPort || localPort < 1 || localPort > 65535) {
        showToast('Bitte einen gültigen Port eingeben (1-65535)', 'error');
        return;
    }

    showToast('Verbinde App mit Tailscale...');
    try {
        const params = new URLSearchParams({ local_port: localPort, public_port: publicPort });
        if (servePath) params.append('serve_path', servePath);
        const res = await fetch(`/api/add_existing?${params.toString()}`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            showToast(`App auf Port ${localPort} ist jetzt erreichbar! 🎉`, 'success');
            document.getElementById('existing-port').value = '';
            fetchStatus();
        } else {
            showToast('Fehler: ' + data.detail, 'error');
        }
    } catch (e) {
        showToast('Verbindung fehlgeschlagen', 'error');
    }
}

// ─── BROWSE + START PROJECT ───────────────────────────────────────────────────
async function browseFolder() {
    try {
        const res = await fetch('/api/browse');
        const data = await res.json();
        if (data.path) {
            smartFolderPath.value = data.path;
            detectionDetails.style.display = 'flex';
            projectTypeBadge.textContent = data.type.toUpperCase();
            smartCommand.value = data.suggestedCommand || '';

            const dataList = document.getElementById('command-suggestions');
            if (dataList) {
                dataList.innerHTML = '';
                if (data.fallbackCommands && data.fallbackCommands.length > 0) {
                    data.fallbackCommands.forEach(cmd => {
                        const option = document.createElement('option');
                        option.value = cmd;
                        dataList.appendChild(option);
                    });
                }
            }

            showToast(`Erkannt: ${data.type}`, 'success');
        }
    } catch (e) {
        showToast('Ordnerauswahl fehlgeschlagen', 'error');
    }
}

async function hostProject() {
    const path = smartFolderPath.value;
    const command = smartCommand.value;
    const publicPort = document.getElementById('new-public-port')?.value || '443';
    const servePath = document.getElementById('new-serve-path')?.value?.trim() || '';

    if (!path) {
        showToast('Bitte erst einen Ordner auswählen', 'error');
        return;
    }

    showToast('Starte Projekt...');
    try {
        const params = new URLSearchParams({ path, public_port: publicPort });
        if (command) params.append('command', command);
        if (servePath) params.append('serve_path', servePath);
        const res = await fetch(`/api/host_project?${params.toString()}`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
            showToast('Projekt gestartet und veröffentlicht! 🚀', 'success');
            smartFolderPath.value = '';
            detectionDetails.style.display = 'none';
            fetchStatus();
        } else {
            showToast('Fehler: ' + data.detail, 'error');
        }
    } catch (e) {
        showToast('Fehler beim Starten', 'error');
    }
}

// ─── RESET ALL ────────────────────────────────────────────────────────────────
async function resetAll() {
    if (!confirm('⚠️ Alle Dienste stoppen, Tailscale zurücksetzen und projects.json leeren?\n\nDies stoppt alle laufenden Apps!')) return;
    try {
        const res = await fetch('/api/reset_all', { method: 'POST' });
        if (res.ok) {
            showToast('Alles zurückgesetzt. ✓', 'success');
            fetchStatus();
        } else {
            const d = await res.json();
            showToast('Fehler: ' + d.detail, 'error');
        }
    } catch (e) {
        showToast('Fehler beim Zurücksetzen', 'error');
    }
}

// ─── REMOVE SERVICE ───────────────────────────────────────────────────────────
async function removeService(key) {
    if (!confirm('Dienst wirklich stoppen und URL deaktivieren?')) return;
    try {
        const res = await fetch(`/api/serve?path=${encodeURIComponent(key)}`, { method: 'DELETE' });
        if (res.ok) {
            showToast('Dienst gestoppt.', 'success');
            fetchStatus();
            if (logInterval) closeLogs();
        } else {
            const d = await res.json();
            showToast('Fehler: ' + d.detail, 'error');
        }
    } catch (e) {
        showToast('Fehler beim Stoppen', 'error');
    }
}

// ─── PORT EDITING ───────────────────────────────────────────────────────────
async function editPort(key, currentPort) {
    const newPortStr = prompt(`Neuen lokalen Port für "${key}" eingeben:`, currentPort);
    if (newPortStr === null) return;

    const newPort = parseInt(newPortStr);
    if (isNaN(newPort) || newPort < 1 || newPort > 65535) {
        showToast('Ungültiger Port (1-65535)', 'error');
        return;
    }

    if (newPort === currentPort) return;

    showToast('Aktualisiere Port und starte Projekt neu...');
    try {
        const params = new URLSearchParams({ key, new_port: newPort });
        const res = await fetch(`/api/update_project_port?${params.toString()}`, { method: 'POST' });
        const data = await res.json();

        if (res.ok) {
            showToast('Port erfolgreich aktualisiert! 🚀', 'success');
            fetchStatus();
        } else {
            showToast('Fehler: ' + data.detail, 'error');
        }
    } catch (e) {
        showToast('Fehler beim Aktualisieren des Ports', 'error');
    }
}

// ─── LOGS ─────────────────────────────────────────────────────────────────────
function viewLogs(key) {
    logProjectName.textContent = key;
    logViewer.style.display = 'flex';
    if (logInterval) clearInterval(logInterval);
    logInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/logs?path=${encodeURIComponent(key)}`);
            const logs = await res.json();
            logContent.textContent = logs.join('\n');
            logContent.scrollTop = logContent.scrollHeight;
        } catch (e) { }
    }, 1000);
}

function closeLogs() {
    logViewer.style.display = 'none';
    if (logInterval) clearInterval(logInterval);
    logInterval = null;
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('URL in die Zwischenablage kopiert! 📋', 'success');
    });
}

// ─── TOAST ────────────────────────────────────────────────────────────────────
function showToast(msg, type = '') {
    toastEl.textContent = msg;
    toastEl.className = `toast ${type} show`;
    setTimeout(() => toastEl.classList.remove('show'), 4000);
}
