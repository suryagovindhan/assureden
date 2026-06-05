// Setup WebSocket connection
let ws;
const terminal = document.getElementById('terminal');

// Auth Check
const token = localStorage.getItem('access_token');
if (!token) {
    window.location.href = '/login';
}

function initWebSocket() {
    // Determine the WS URL dynamically
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // For dashboard listener, we'll pretend we are agent 'dashboard' for now to listen
    // In a real app, this should be a dedicated reporting endpoint, but this works for demo.
    const wsUrl = `${protocol}//${window.location.host}/ws/agent/dashboard-listener`;

    ws = new WebSocket(wsUrl);

    ws.onopen = function (event) {
        logToTerminal('Connected to Server WebSocket', 'sys');
    };

    ws.onmessage = function (event) {
        logToTerminal(event.data, 'msg');
    };

    ws.onclose = function (event) {
        logToTerminal('Connection lost. Reconnecting...', 'err');
        setTimeout(initWebSocket, 3000);
    };
}

function logToTerminal(message, type) {
    const div = document.createElement('div');
    div.className = `log-line ${type}`;
    div.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
    terminal.appendChild(div);
    terminal.scrollTop = terminal.scrollHeight;
}

async function fetchMetrics() {
    try {
        const res = await fetch('/api/metrics/dashboard', { headers: { 'Authorization': `Bearer ${token}` } });
        if (res.ok) {
            const data = await res.json();
            document.getElementById('metric-total-tests').textContent = data.total_tests;
            document.getElementById('metric-pass-rate').textContent = `${data.pass_rate}%`;
            document.getElementById('metric-online-agents').textContent = data.online_agents;
            document.getElementById('metric-total-agents').textContent = data.total_agents;
        }
    } catch (e) {
        console.error("Failed to load metrics", e);
    }
}

window.addEventListener('load', () => {
    initWebSocket();
    fetchMetrics();

    // Also fetch current user name for the top header
    fetch('/auth/me', { headers: { 'Authorization': `Bearer ${token}` } })
        .then(res => res.json())
        .then(user => {
            const el = document.getElementById('current-user-name');
            if (el) el.textContent = user.username;
        }).catch(err => console.error(err));
});

// Trigger Tests API
async function triggerTest(module, action) {
    const endpoint = `/api/${module}/${action}`;
    try {
        logToTerminal(`Initiating ${module.toUpperCase()} test: ${action}...`, 'sys');
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            }
        });
        const data = await response.json();
        logToTerminal(`API Response: ${JSON.stringify(data)}`, 'sys');

        // Broadcast test to agent topic (Mock logic via WS)
        const instruction = {
            domain: module.toUpperCase(),
            action: action,
            target_url: "https://demo.target.local"
        };
        ws.send(JSON.stringify(instruction));
        logToTerminal(`Sent command -> ${JSON.stringify(instruction)}`, 'msg');

    } catch (error) {
        logToTerminal(`Error triggering test: ${error.message}`, 'err');
    }
}
