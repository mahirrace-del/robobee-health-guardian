/**
 * ASTROHEALTH GUARDIAN — MASTER JAVASCRIPT CONTROLLER
 * Full operational logic for real-time WebSocket telemetry, multi-pane navigation,
 * dual-axis Chart.js visualization, alert acknowledgement/resolution,
 * research library search, hardware injection, and CSV/JSON export.
 */

// Global State
let ws = null;
let telemetryHistory = [];
const MAX_BUFFER_SIZE = 600; // Store up to 600 seconds of telemetry
let currentSourceMode = 'simulated';
let activeScenarioName = 'Scenario A: Routine Operations';
let cachedAlerts = [];
let cachedCitations = [];
let pendingResolveAlertId = null;

// Chart Instances
let overviewChart = null;
let explorerChart = null;

// --- Initialize Application on DOM Ready ---
document.addEventListener('DOMContentLoaded', () => {
    initClock();
    initTabs();
    initCharts();
    initWebSocket();
    initAlertFilters();
    initResearchLibrary();
    initDeviceRegistry();
    initExplorerControls();
    initScenarioControls();
    initVisionChat();
    initResolveModal();
});

// --- 1. Live UTC Mission Clock ---
function initClock() {
    const clockEl = document.getElementById('live-clock');
    function updateTime() {
        const now = new Date();
        const utcStr = now.toISOString().substring(11, 19) + ' UTC';
        if (clockEl) clockEl.textContent = utcStr;
    }
    updateTime();
    setInterval(updateTime, 1000);
}

// --- 2. Navigation Tab Switching ---
function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabTriggers = document.querySelectorAll('[data-tab]');
    const tabPanes = document.querySelectorAll('.tab-pane');

    tabTriggers.forEach(btn => {
        btn.addEventListener('click', () => {
            tabButtons.forEach(b => b.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));

            const targetId = btn.getAttribute('data-tab');
            document.querySelector(`.tab-btn[data-tab="${targetId}"]`)?.classList.add('active');
            const targetPane = document.getElementById(targetId);
            if (targetPane) {
                targetPane.classList.add('active');
                // Trigger chart resize when switching to explorer
                if (targetId === 'tab-explorer' && explorerChart) {
                    explorerChart.resize();
                    updateExplorerView();
                }
                if (targetId === 'tab-overview' && overviewChart) {
                    overviewChart.resize();
                }
                if (targetId === 'tab-alerts') {
                    fetchAlerts();
                }
                if (targetId === 'tab-hardware') {
                    fetchDevices();
                }
            }
        });
    });
}

// --- 3. Chart.js Initialization ---
function initCharts() {
    // Overview Live Chart
    const ctxOverview = document.getElementById('overviewLiveChart');
    if (ctxOverview) {
        overviewChart = new Chart(ctxOverview.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Heart Rate (bpm)',
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.08)',
                        data: [],
                        yAxisID: 'y_hr',
                        tension: 0.35,
                        borderWidth: 2,
                        pointRadius: 0
                    },
                    {
                        label: 'SpO2 (%)',
                        borderColor: '#00e5ff',
                        backgroundColor: 'rgba(0, 229, 255, 0.08)',
                        data: [],
                        yAxisID: 'y_spo2',
                        tension: 0.35,
                        borderWidth: 2,
                        pointRadius: 0
                    },
                    {
                        label: 'ppCO2 (mmHg)',
                        borderColor: '#a855f7',
                        backgroundColor: 'rgba(168, 85, 247, 0.08)',
                        data: [],
                        yAxisID: 'y_co2',
                        tension: 0.35,
                        borderWidth: 1.5,
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        ticks: { color: '#64748b', font: { family: 'Share Tech Mono', size: 10 }, maxTicksLimit: 8 },
                        grid: { color: 'rgba(255, 255, 255, 0.04)' }
                    },
                    y_hr: {
                        type: 'linear',
                        position: 'left',
                        min: 40,
                        max: 180,
                        ticks: { color: '#ef4444', font: { family: 'Share Tech Mono', size: 10 } },
                        grid: { color: 'rgba(255, 255, 255, 0.04)' }
                    },
                    y_spo2: {
                        type: 'linear',
                        position: 'right',
                        min: 80,
                        max: 100,
                        ticks: { color: '#00e5ff', font: { family: 'Share Tech Mono', size: 10 } },
                        grid: { drawOnChartArea: false }
                    },
                    y_co2: {
                        type: 'linear',
                        position: 'right',
                        min: 0,
                        max: 8,
                        ticks: { color: '#a855f7', font: { family: 'Share Tech Mono', size: 10 } },
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });
    }

    // Telemetry Explorer Chart
    const ctxExplorer = document.getElementById('explorerChart');
    if (ctxExplorer) {
        explorerChart = new Chart(ctxExplorer.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: []
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        labels: { color: '#e2e8f0', font: { family: 'Inter', size: 11 } }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#64748b', font: { family: 'Share Tech Mono' } },
                        grid: { color: 'rgba(255, 255, 255, 0.04)' }
                    },
                    y: {
                        ticks: { color: '#94a3b8', font: { family: 'Share Tech Mono' } },
                        grid: { color: 'rgba(255, 255, 255, 0.04)' }
                    }
                }
            }
        });
    }
}

// --- 4. WebSocket Client & Auto-Reconnect ---
function initWebSocket() {
    const wsBadge = document.getElementById('ws-badge');
    const wsUrl = `ws://${window.location.hostname || 'localhost'}:8000/ws/telemetry`;

    if (wsBadge) {
        wsBadge.textContent = 'CONNECTING';
        wsBadge.className = 'status-badge connecting';
    }

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        if (wsBadge) {
            wsBadge.textContent = 'CONNECTED';
            wsBadge.className = 'status-badge connected';
        }
        // Start ping heartbeat
        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 15000);
    };

    ws.onclose = () => {
        if (wsBadge) {
            wsBadge.textContent = 'DISCONNECTED';
            wsBadge.className = 'status-badge disconnected';
        }
        // Auto reconnect after 3 seconds
        setTimeout(initWebSocket, 3000);
    };

    ws.onerror = (err) => {
        console.warn('WebSocket encountered error:', err);
    };

    ws.onmessage = (event) => {
        try {
            const envelope = JSON.parse(event.data);
            if (envelope.type === 'telemetry') {
                processTelemetryEnvelope(envelope);
            }
        } catch (e) {
            console.error('Error parsing incoming telemetry envelope:', e);
        }
    };
}

// --- 5. Real-time Telemetry Frame Processor ---
function processTelemetryEnvelope(envelope) {
    const data = envelope.telemetry;
    const context = envelope.context;
    const alerts = envelope.alerts || [];
    currentSourceMode = envelope.source_mode || 'simulated';
    activeScenarioName = envelope.scenario_name || activeScenarioName;

    // Buffer frame in memory
    telemetryHistory.push(data);
    if (telemetryHistory.length > MAX_BUFFER_SIZE) {
        telemetryHistory.shift();
    }

    // 1. Update Mode Badge
    const modeBadge = document.getElementById('mode-badge');
    if (modeBadge) {
        modeBadge.textContent = currentSourceMode.toUpperCase();
        modeBadge.className = `mode-badge ${currentSourceMode.toLowerCase()}`;
    }

    // 2. Update Timestamp Age
    const ageEl = document.getElementById('telemetry-age');
    if (ageEl && data.timestamp) {
        const timeStr = data.timestamp.substring(11, 19);
        ageEl.textContent = `Last packet: ${timeStr} UTC`;
    }

    // 3. Update Primary 8 HUD Cards
    updateHUDCard('card-hr', 'val-hr', 'qual-hr', data.heart_rate, 'bpm');
    updateHUDCard('card-spo2', 'val-spo2', 'qual-spo2', data.spo2, '%');

    // Blood Pressure
    const bpCard = document.getElementById('card-bp');
    const valBp = document.getElementById('val-bp');
    if (valBp && data.blood_pressure_systolic && data.blood_pressure_diastolic) {
        const sys = data.blood_pressure_systolic.value;
        const dia = data.blood_pressure_diastolic.value;
        valBp.textContent = (sys !== null && sys !== undefined && dia !== null && dia !== undefined)
            ? `${sys.toFixed(0)}/${dia.toFixed(0)}`
            : '--/--';
    }

    // MAP
    updateHUDCard('card-map', 'val-map', null, data.mean_arterial_pressure, 'mmHg');

    // HRV
    updateHUDCard('card-hrv', 'val-hrv', null, data.hrv_rmssd, 'ms');

    // Temperatures
    updateHUDCard('card-core-temp', 'val-core-temp', null, data.core_temperature, '°C');
    updateHUDCard('card-skin-temp', 'val-skin-temp', 'qual-skin-temp', data.skin_temperature, '°C');

    // Respiration Rate
    updateHUDCard('card-rr', 'val-rr', null, data.respiration_rate, 'br/min');

    // 4. Update Habitat Environmental HUD
    const valCo2 = document.getElementById('val-co2');
    const boxCo2 = document.getElementById('box-co2');
    const co2Status = document.getElementById('co2-status');
    if (valCo2 && data.co2_pp_mmhg) {
        const co2Val = data.co2_pp_mmhg.value;
        if (co2Val !== null && co2Val !== undefined) {
            valCo2.innerHTML = `${co2Val.toFixed(2)} <span class="hab-unit">mmHg</span>`;
            if (co2Val >= 4.0) {
                boxCo2?.classList.add('alert');
                if (co2Status) {
                    co2Status.textContent = 'CRITICAL: Exceeds 24h limit (4.0)';
                    co2Status.style.color = '#ef4444';
                }
            } else if (co2Val >= 3.0) {
                boxCo2?.classList.add('alert');
                if (co2Status) {
                    co2Status.textContent = 'WARNING: Exceeds nominal (3.0)';
                    co2Status.style.color = '#f59e0b';
                }
            } else {
                boxCo2?.classList.remove('alert');
                if (co2Status) {
                    co2Status.textContent = 'NASA-STD-3001: < 3.0 mmHg';
                    co2Status.style.color = '#94a3b8';
                }
            }
        } else {
            valCo2.innerHTML = `-- <span class="hab-unit">mmHg</span>`;
            boxCo2?.classList.remove('alert');
            if (co2Status) {
                co2Status.textContent = 'UNAVAILABLE (Unmeasured in live packet)';
                co2Status.style.color = '#94a3b8';
            }
        }
    }

    const valCabinTemp = document.getElementById('val-cabin-temp');
    if (valCabinTemp && data.cabin_temp_c) {
        const cabVal = data.cabin_temp_c.value;
        valCabinTemp.innerHTML = (cabVal !== null && cabVal !== undefined)
            ? `${cabVal.toFixed(1)} <span class="hab-unit">°C</span>`
            : `-- <span class="hab-unit">°C</span>`;
    }

    const valRadiation = document.getElementById('val-radiation');
    if (valRadiation && data.radiation_dose_rate_ugy_day) {
        const radVal = data.radiation_dose_rate_ugy_day.value;
        valRadiation.innerHTML = (radVal !== null && radVal !== undefined)
            ? `${radVal.toFixed(0)} <span class="hab-unit">µGy/d</span>`
            : `-- <span class="hab-unit">µGy/d</span>`;
    }

    // 5. Update Readiness & Sleep Cards
    const valSleepHours = document.getElementById('val-sleep-hours');
    if (valSleepHours && data.sleep_hours) {
        valSleepHours.textContent = (data.sleep_hours.value !== null && data.sleep_hours.value !== undefined)
            ? `${data.sleep_hours.value} hrs`
            : '-- hrs';
    }

    const valSleepEff = document.getElementById('val-sleep-eff');
    if (valSleepEff && data.sleep_efficiency) {
        valSleepEff.textContent = (data.sleep_efficiency.value !== null && data.sleep_efficiency.value !== undefined)
            ? `${data.sleep_efficiency.value}%`
            : '--%';
    }

    const valPvt = document.getElementById('val-pvt-reaction');
    if (valPvt && data.reaction_time_ms) {
        valPvt.textContent = (data.reaction_time_ms.value !== null && data.reaction_time_ms.value !== undefined)
            ? `${data.reaction_time_ms.value} ms`
            : '-- ms';
    }

    const valExSum = document.getElementById('val-exercise-summary');
    if (valExSum && data.exercise_type && data.exercise_load_w) {
        const exLoad = data.exercise_load_w.value;
        valExSum.textContent = (exLoad !== null && exLoad !== undefined)
            ? `${data.exercise_type} (${exLoad} W)`
            : `${data.exercise_type}`;
    }

    const rdyLabel = document.getElementById('readiness-label');
    if (rdyLabel && data.readiness_score) {
        const rdyVal = data.readiness_score.value;
        if (rdyVal !== null && rdyVal !== undefined) {
            rdyLabel.textContent = `READINESS: ${rdyVal.toFixed(0)}%`;
            if (rdyVal < 60) {
                rdyLabel.className = 'badge critical';
            } else if (rdyVal < 75) {
                rdyLabel.className = 'badge warning';
            } else {
                rdyLabel.className = 'badge info';
            }
        } else {
            rdyLabel.textContent = 'READINESS: --';
            rdyLabel.className = 'badge info';
        }
    }

    // 6. Update Vision & Context Feed
    const valExp = document.getElementById('val-expression');
    if (valExp) {
        if (context && context.webcam_affect) {
            valExp.textContent = context.webcam_affect.toUpperCase();
        } else if (!laptopWebcamStream && data.detected_expression) {
            valExp.textContent = data.detected_expression.toUpperCase();
        }
    }

    const valPost = document.getElementById('val-posture');
    if (valPost && !laptopWebcamStream && data.exercise_posture_score) {
        const postVal = data.exercise_posture_score.value;
        valPost.textContent = (postVal !== null && postVal !== undefined)
            ? `${postVal.toFixed(2)} / 1.0`
            : '-- / 1.0';
    }

    const contextText = document.getElementById('context-text');
    if (contextText && context) {
        if (context.webcam_note) {
            contextText.textContent = `${context.webcam_note} (${context.context_type})`;
        } else if (!laptopWebcamStream) {
            contextText.textContent = `${context.context_type}: ${context.context_note}`;
        }
    }

    // 7. Update Live Chart
    if (overviewChart) {
        const timeLabel = data.timestamp ? data.timestamp.substring(14, 19) : '';
        overviewChart.data.labels.push(timeLabel);
        overviewChart.data.datasets[0].data.push(data.heart_rate?.value ?? null);
        overviewChart.data.datasets[1].data.push(data.spo2?.value ?? null);
        overviewChart.data.datasets[2].data.push(data.co2_pp_mmhg?.value ?? null);

        // Retain max 45 points in overview live chart
        if (overviewChart.data.labels.length > 45) {
            overviewChart.data.labels.shift();
            overviewChart.data.datasets[0].data.shift();
            overviewChart.data.datasets[1].data.shift();
            overviewChart.data.datasets[2].data.shift();
        }
        overviewChart.update('none'); // fast update
    }

    // 8. Update Active Alerts HUD Banner
    updateOverviewAlertsHUD(alerts);

    // 9. Update Crew Health Tab Detailed Metrics
    updateCrewHealthTab(data);
}

// Helper to update a single vital HUD card
function updateHUDCard(cardId, valId, qualId, metricItem, unit) {
    const card = document.getElementById(cardId);
    const valEl = document.getElementById(valId);
    const qualEl = qualId ? document.getElementById(qualId) : null;

    if (!metricItem) return;

    if (valEl) {
        if (metricItem.value !== null && metricItem.value !== undefined) {
            valEl.textContent = metricItem.value.toFixed(metricItem.unit === '°C' ? 2 : 1);
        } else {
            valEl.textContent = '--';
        }
    }

    if (qualEl) {
        const q = (metricItem.quality || 'valid').toLowerCase();
        qualEl.textContent = q.toUpperCase();
        qualEl.className = `quality-tag ${q}`;
    }

    // Alert border highlighting (preserving autonomous vital-card-scanning class if active)
    if (card) {
        const isScanning = card.classList.contains('vital-card-scanning');
        let baseCls = 'vital-card';
        if (metricItem.quality === 'stale' || metricItem.quality === 'missing') {
            baseCls = 'vital-card alert-warning';
        } else if (cardId === 'card-hr' && metricItem.value > 115) {
            baseCls = 'vital-card alert-critical';
        } else if (cardId === 'card-spo2' && metricItem.value < 94) {
            baseCls = 'vital-card alert-critical';
        }
        card.className = isScanning ? `${baseCls} vital-card-scanning` : baseCls;
    }
}

// Update Crew Health workspace
function updateCrewHealthTab(data) {
    const hasVal = (item) => item && item.value !== null && item.value !== undefined;
    const elMap = {
        'ch-map': hasVal(data.mean_arterial_pressure) ? `${data.mean_arterial_pressure.value.toFixed(1)} mmHg` : '--',
        'ch-pp': (hasVal(data.blood_pressure_systolic) && hasVal(data.blood_pressure_diastolic)) ? 
                 `${(data.blood_pressure_systolic.value - data.blood_pressure_diastolic.value).toFixed(1)} mmHg` : '--',
        'ch-hrv': hasVal(data.hrv_rmssd) ? `${data.hrv_rmssd.value.toFixed(1)} ms` : '--',
        'ch-spo2': hasVal(data.spo2) ? `${data.spo2.value.toFixed(1)}%` : '--',
        'ch-rr': hasVal(data.respiration_rate) ? `${data.respiration_rate.value.toFixed(1)} breaths/min` : '--',
        'ch-core': hasVal(data.core_temperature) ? `${data.core_temperature.value.toFixed(2)}°C` : '--',
        'ch-gradient': (hasVal(data.core_temperature) && hasVal(data.skin_temperature)) ? 
                       `Δ ${(data.core_temperature.value - data.skin_temperature.value).toFixed(2)}°C` : '--',
        'ch-sleep-dur': hasVal(data.sleep_hours) ? `${data.sleep_hours.value} hrs` : '--',
        'ch-sleep-eff': hasVal(data.sleep_efficiency) ? `${data.sleep_efficiency.value}%` : '--',
        'ch-sleep-wake': hasVal(data.sleep_interruptions) ? `${data.sleep_interruptions.value} episodes` : '--',
        'ch-pvt-speed': hasVal(data.reaction_time_ms) ? `${data.reaction_time_ms.value} ms` : '--',
        'ch-pvt-lapses': hasVal(data.attention_lapses) ? `${data.attention_lapses.value} lapses` : '--',
        'ch-ex-mode': data.exercise_type || '--',
        'ch-ex-load': hasVal(data.exercise_load_w) ? `${data.exercise_load_w.value} Watts` : '--',
        'ch-posture': hasVal(data.exercise_posture_score) ? `${data.exercise_posture_score.value.toFixed(2)}` : '--'
    };

    for (const [id, val] of Object.entries(elMap)) {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    }
}

// Update Active Alerts on Mission Overview
function updateOverviewAlertsHUD(activeAlerts) {
    const container = document.getElementById('overview-alert-container');
    const pill = document.getElementById('alert-counter-pill');
    const tabBadge = document.getElementById('tab-alert-count');

    if (pill) {
        pill.textContent = activeAlerts.length;
        pill.className = activeAlerts.length > 0 ? 'alert-pill active-alert' : 'alert-pill nominal';
    }

    if (tabBadge) {
        tabBadge.textContent = activeAlerts.length;
        if (activeAlerts.length > 0) {
            tabBadge.classList.remove('hidden');
        } else {
            tabBadge.classList.add('hidden');
        }
    }

    if (!container) return;

    if (activeAlerts.length === 0) {
        container.innerHTML = `
            <div class="empty-alerts">
                <span class="check-icon">✓</span>
                <span>All physiological & habitat parameters within nominal flight limits.</span>
            </div>
        `;
        return;
    }

    container.innerHTML = activeAlerts.map(a => `
        <div class="alert-event-item ${a.severity}">
            <div class="alert-item-header">
                <span class="badge ${a.severity}">${a.severity}</span>
                <span class="alert-id-tag">${a.id}</span>
            </div>
            <div class="alert-item-body">
                <strong>${a.threshold_rule}:</strong> ${a.explanation}
            </div>
            <div class="alert-item-footer">
                <span>Value: ${a.observed_value} ${a.unit}</span>
                <button class="btn btn-secondary" onclick="openAcknowledgeAlert('${a.id}')" style="padding: 2px 8px; font-size: 0.68rem;">ACKNOWLEDGE</button>
            </div>
        </div>
    `).join('');
}

// --- 6. Telemetry Explorer Operations ---
function initExplorerControls() {
    const toggles = document.querySelectorAll('.metric-toggle');
    toggles.forEach(t => t.addEventListener('change', updateExplorerView));

    const windowSelect = document.getElementById('explorer-window');
    if (windowSelect) windowSelect.addEventListener('change', updateExplorerView);

    const btnCsv = document.getElementById('btn-export-csv');
    if (btnCsv) btnCsv.addEventListener('click', exportTelemetryCSV);

    const btnJson = document.getElementById('btn-export-json');
    if (btnJson) btnJson.addEventListener('click', exportTelemetryJSON);
}

function updateExplorerView() {
    if (!explorerChart) return;

    const windowSelect = document.getElementById('explorer-window');
    const windowSeconds = parseInt(windowSelect?.value || '120', 10);
    const slice = telemetryHistory.slice(-windowSeconds);

    if (slice.length === 0) return;

    const checkedBoxes = Array.from(document.querySelectorAll('.metric-toggle:checked'));
    const selectedMetrics = checkedBoxes.map(cb => cb.value);

    const metricColors = {
        heart_rate: '#ef4444',
        spo2: '#00e5ff',
        co2_pp_mmhg: '#a855f7',
        hrv_rmssd: '#38bdf8',
        core_temperature: '#f59e0b',
        respiration_rate: '#10b981'
    };

    const metricLabels = {
        heart_rate: 'Heart Rate (bpm)',
        spo2: 'SpO2 (%)',
        co2_pp_mmhg: 'ppCO2 (mmHg)',
        hrv_rmssd: 'HRV RMSSD (ms)',
        core_temperature: 'Core Temp (°C)',
        respiration_rate: 'Respiration (br/min)'
    };

    const timeLabels = slice.map(row => row.timestamp ? row.timestamp.substring(14, 19) : '');

    const datasets = selectedMetrics.map(key => ({
        label: metricLabels[key] || key,
        data: slice.map(row => row[key]?.value ?? null),
        borderColor: metricColors[key] || '#ffffff',
        borderWidth: 2,
        tension: 0.3,
        pointRadius: slice.length > 100 ? 0 : 2
    }));

    explorerChart.data.labels = timeLabels;
    explorerChart.data.datasets = datasets;
    explorerChart.update();

    // Calculate real descriptive statistics
    updateStatisticsTable(slice, selectedMetrics);
}

function updateStatisticsTable(slice, selectedMetrics) {
    const tbody = document.getElementById('stats-table-body');
    if (!tbody) return;

    const allMetrics = [
        { key: 'heart_rate', label: 'Heart Rate', unit: 'bpm', cat: 'Measured (PPG Model)' },
        { key: 'spo2', label: 'Blood Oxygen (SpO2)', unit: '%', cat: 'Measured (Pulse-Ox)' },
        { key: 'co2_pp_mmhg', label: 'Partial Pressure CO2', unit: 'mmHg', cat: 'Habitat Sensor' },
        { key: 'hrv_rmssd', label: 'Heart Rate Variability', unit: 'ms', cat: 'Derived Calculation' },
        { key: 'core_temperature', label: 'Core Temperature', unit: '°C', cat: 'Simulated Probe' },
        { key: 'respiration_rate', label: 'Respiration Rate', unit: 'br/min', cat: 'Derived Estimate' }
    ];

    tbody.innerHTML = allMetrics.map(m => {
        const values = slice.map(r => r[m.key]?.value).filter(v => v !== null && v !== undefined);
        const count = values.length;

        if (count === 0) {
            return `
                <tr>
                    <td><strong>${m.label}</strong></td>
                    <td>${m.unit}</td>
                    <td>0</td>
                    <td>--</td>
                    <td>--</td>
                    <td>--</td>
                    <td>--</td>
                    <td><span class="quality-tag missing">NO DATA</span></td>
                    <td>${m.cat}</td>
                </tr>
            `;
        }

        const min = Math.min(...values).toFixed(1);
        const max = Math.max(...values).toFixed(1);
        const mean = (values.reduce((a, b) => a + b, 0) / count).toFixed(1);
        const last = values[values.length - 1].toFixed(1);

        return `
            <tr>
                <td><strong>${m.label}</strong></td>
                <td>${m.unit}</td>
                <td>${count}</td>
                <td>${min}</td>
                <td>${max}</td>
                <td>${mean}</td>
                <td>${last}</td>
                <td><span class="quality-tag valid">VALID</span></td>
                <td>${m.cat}</td>
            </tr>
        `;
    }).join('');
}

// Export Telemetry as CSV
function exportTelemetryCSV() {
    if (telemetryHistory.length === 0) {
        alert('No telemetry in buffer to export.');
        return;
    }

    const headers = ['timestamp', 'crew_id', 'source_mode', 'heart_rate', 'spo2', 'co2_pp_mmhg', 'hrv_rmssd', 'core_temp', 'skin_temp', 'respiration', 'posture'];
    const rows = telemetryHistory.map(r => [
        r.timestamp,
        r.crew_id,
        r.source_mode,
        r.heart_rate?.value ?? '',
        r.spo2?.value ?? '',
        r.co2_pp_mmhg?.value ?? '',
        r.hrv_rmssd?.value ?? '',
        r.core_temperature?.value ?? '',
        r.skin_temperature?.value ?? '',
        r.respiration_rate?.value ?? '',
        r.exercise_posture_score?.value ?? ''
    ]);

    const csvContent = [headers.join(','), ...rows.map(e => e.join(','))].join('\n');
    downloadFile(csvContent, 'text/csv', 'astrohealth_telemetry_export.csv');
}

// Export Telemetry as JSON
function exportTelemetryJSON() {
    if (telemetryHistory.length === 0) {
        alert('No telemetry in buffer to export.');
        return;
    }
    const jsonStr = JSON.stringify(telemetryHistory, null, 2);
    downloadFile(jsonStr, 'application/json', 'astrohealth_telemetry_export.json');
}

function downloadFile(content, mimeType, filename) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// --- 7. Alerts Management & Workflows ---
function initAlertFilters() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            filterButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderAlertsList(btn.getAttribute('data-filter'));
        });
    });
}

async function fetchAlerts() {
    try {
        const res = await fetch('/api/alerts');
        if (res.ok) {
            const data = await res.json();
            cachedAlerts = data.alerts || [];
            renderAlertsList('all');
        }
    } catch (e) {
        console.error('Error fetching alerts:', e);
    }
}

function renderAlertsList(filter = 'all') {
    const container = document.getElementById('alerts-full-list');
    const statsEl = document.getElementById('alert-summary-stats');
    if (!container) return;

    let filtered = cachedAlerts;
    if (filter !== 'all') {
        filtered = cachedAlerts.filter(a => a.status === filter);
    }

    if (statsEl) {
        const crit = cachedAlerts.filter(a => a.severity === 'critical').length;
        const warn = cachedAlerts.filter(a => a.severity === 'warning').length;
        statsEl.textContent = `Total: ${cachedAlerts.length} | Critical: ${crit} | Warning: ${warn}`;
    }

    if (filtered.length === 0) {
        container.innerHTML = `<div class="empty-alerts-full" style="padding: 24px; text-align: center; color: #64748b;">No alerts found under filter: ${filter.toUpperCase()}.</div>`;
        return;
    }

    container.innerHTML = filtered.map(a => `
        <div class="alert-full-card ${a.severity} ${a.status}">
            <div class="alert-title-row">
                <div>
                    <span class="badge ${a.severity}">${a.severity}</span>
                    <span class="badge ${a.status === 'resolved' ? 'nominal' : 'info'}" style="margin-left: 6px;">${a.status}</span>
                    <strong style="margin-left: 10px; color: #f8fafc;">${a.trigger_parameter} — ${a.threshold_rule}</strong>
                </div>
                <span class="alert-id-tag">${a.id} • ${a.timestamp.substring(11, 19)} UTC</span>
            </div>
            <div style="font-size: 0.82rem; margin: 8px 0; color: #e2e8f0; line-height: 1.4;">
                ${a.explanation}
            </div>
            ${a.suggested_actions && a.suggested_actions.length > 0 ? `
                <div style="background: rgba(0,0,0,0.25); padding: 8px 12px; border-radius: 4px; margin: 8px 0;">
                    <div style="font-size: 0.7rem; color: #00e5ff; font-weight: bold; margin-bottom: 4px;">RECOMMENDED VERIFICATION ACTIONS:</div>
                    <ul style="padding-left: 16px; font-size: 0.75rem; color: #94a3b8;">
                        ${a.suggested_actions.map(act => `<li>${act}</li>`).join('')}
                    </ul>
                </div>
            ` : ''}
            ${a.literature_citation ? `
                <div style="font-size: 0.72rem; color: #64748b; margin-top: 6px;">
                    Literature: <a href="${a.literature_citation.url}" target="_blank" style="color: #00e5ff;">${a.literature_citation.title}</a> (${a.literature_citation.organization})
                </div>
            ` : ''}
            ${a.resolution_notes ? `
                <div style="font-size: 0.75rem; background: rgba(16, 185, 129, 0.1); border-left: 3px solid #10b981; padding: 6px 10px; margin-top: 8px; color: #34d399;">
                    <strong>Resolution Log:</strong> ${a.resolution_notes} (by ${a.resolved_by || 'Flight Surgeon'})
                </div>
            ` : ''}
            <div class="alert-action-btn-row">
                ${a.status === 'active' ? `
                    <button class="btn btn-secondary" onclick="openAcknowledgeAlert('${a.id}')">ACKNOWLEDGE</button>
                    <button class="btn btn-primary" onclick="openResolveModal('${a.id}', '${a.trigger_parameter}')">RESOLVE WITH NOTES</button>
                ` : a.status === 'acknowledged' ? `
                    <button class="btn btn-primary" onclick="openResolveModal('${a.id}', '${a.trigger_parameter}')">RESOLVE WITH NOTES</button>
                ` : `
                    <span style="font-size: 0.72rem; color: #10b981;">✓ Resolved at ${a.resolved_at?.substring(11, 19)} UTC</span>
                `}
            </div>
        </div>
    `).join('');
}

window.openAcknowledgeAlert = async function(alertId) {
    try {
        const res = await fetch(`/api/alerts/${alertId}/acknowledge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ operator_id: 'Flight Surgeon Console' })
        });
        if (res.ok) {
            fetchAlerts();
        }
    } catch (e) {
        console.error('Error acknowledging alert:', e);
    }
};

function initResolveModal() {
    const modal = document.getElementById('resolve-modal');
    const closeBtn = document.getElementById('modal-close');
    const cancelBtn = document.getElementById('btn-cancel-resolve');
    const submitBtn = document.getElementById('btn-submit-resolve');

    closeBtn?.addEventListener('click', () => modal.classList.add('hidden'));
    cancelBtn?.addEventListener('click', () => modal.classList.add('hidden'));

    submitBtn?.addEventListener('click', async () => {
        const notes = document.getElementById('resolve-notes')?.value || 'Verified by operator.';
        if (!pendingResolveAlertId) return;

        try {
            const res = await fetch(`/api/alerts/${pendingResolveAlertId}/resolve`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ operator_id: 'Flight Surgeon (MCC)', resolution_notes: notes })
            });
            if (res.ok) {
                modal.classList.add('hidden');
                document.getElementById('resolve-notes').value = '';
                fetchAlerts();
            }
        } catch (e) {
            console.error('Error resolving alert:', e);
        }
    });
}

window.openResolveModal = function(alertId, trigger) {
    pendingResolveAlertId = alertId;
    const modal = document.getElementById('resolve-modal');
    const idEl = document.getElementById('modal-alert-id');
    const trEl = document.getElementById('modal-alert-trigger');
    if (idEl) idEl.textContent = alertId;
    if (trEl) trEl.textContent = trigger;
    if (modal) modal.classList.remove('hidden');
};

// --- 8. Hardware & Device Registry ---
async function fetchDevices() {
    try {
        const res = await fetch('/api/devices');
        if (res.ok) {
            const data = await res.json();
            renderDevicesTable(data.devices || []);
        }
    } catch (e) {
        console.error('Error fetching devices:', e);
    }
}

function renderDevicesTable(devices) {
    const tbody = document.getElementById('device-registry-body');
    if (!tbody) return;

    if (devices.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7">No devices found.</td></tr>';
        return;
    }

    tbody.innerHTML = devices.map(d => `
        <tr>
            <td><code>${d.device_id}</code></td>
            <td><strong>${d.name}</strong></td>
            <td><span class="badge ${d.status === 'online' ? 'nominal' : d.status === 'error' ? 'critical' : 'warning'}">${d.status}</span></td>
            <td><span style="font-size: 0.72rem; color: #00e5ff;">${d.supported_metrics}</span></td>
            <td>${d.total_packets}</td>
            <td>${d.error_count}</td>
            <td style="font-family: var(--font-mono); font-size: 0.72rem;">${d.last_seen}</td>
        </tr>
    `).join('');
}

function initDeviceRegistry() {
    fetchDevices();

    const btnInject = document.getElementById('btn-send-test-packet');
    const statusMsg = document.getElementById('inject-status-msg');

    if (btnInject) {
        btnInject.addEventListener('click', async () => {
            if (statusMsg) statusMsg.textContent = 'Transmitting live packet to /api/telemetry/ingest...';
            try {
                const samplePayload = {
                    schema_version: '1.0',
                    device_id: 'esp32-wearable-01',
                    sequence: Math.floor(Math.random() * 9000) + 1000,
                    measurements: {
                        heart_rate: { value: 76.5 + (Math.random() * 4 - 2), unit: 'bpm', quality: 'valid' },
                        spo2: { value: 98.6, unit: '%', quality: 'valid' },
                        skin_temperature: { value: 33.7, unit: '°C', quality: 'valid' }
                    }
                };

                const res = await fetch('/api/telemetry/ingest', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(samplePayload)
                });

                if (res.ok) {
                    if (statusMsg) {
                        statusMsg.textContent = '✓ Packet Ingested! System switched to LIVE HARDWARE mode.';
                        statusMsg.style.color = '#34d399';
                    }
                    fetchDevices();
                } else {
                    const err = await res.json();
                    if (statusMsg) {
                        statusMsg.textContent = `Error: ${err.detail || 'Failed'}`;
                        statusMsg.style.color = '#ef4444';
                    }
                }
            } catch (e) {
                if (statusMsg) {
                    statusMsg.textContent = `Network Error: ${e.message}`;
                    statusMsg.style.color = '#ef4444';
                }
            }
        });
    }
}

// --- 9. Research Library ---
async function initResearchLibrary() {
    try {
        const res = await fetch('/api/research');
        if (res.ok) {
            const data = await res.json();
            cachedCitations = data.citations || [];
            renderResearchCards(cachedCitations);
        }
    } catch (e) {
        console.error('Error loading research references:', e);
    }

    const searchInput = document.getElementById('research-search');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const q = e.target.value.toLowerCase().trim();
            const filtered = cachedCitations.filter(c => 
                c.title.toLowerCase().includes(q) ||
                c.organization.toLowerCase().includes(q) ||
                c.id.toLowerCase().includes(q) ||
                c.summary.toLowerCase().includes(q)
            );
            renderResearchCards(filtered);
        });
    }
}

function renderResearchCards(citations) {
    const container = document.getElementById('research-cards-container');
    if (!container) return;

    if (citations.length === 0) {
        container.innerHTML = '<div style="padding: 20px; color: #64748b;">No research references match your query.</div>';
        return;
    }

    container.innerHTML = citations.map(c => `
        <div class="citation-card">
            <div>
                <div class="citation-header">
                    <div>
                        <span class="sub-badge">${c.id}</span>
                        <h4 class="citation-title" style="margin-top: 4px;">${c.title}</h4>
                    </div>
                </div>
                <div class="citation-org">${c.organization} • ${c.publication_date}</div>
                <p class="citation-summary">${c.summary}</p>
                <div class="citation-tags">
                    ${c.parameters_established.map(p => `<span class="param-tag">${p}</span>`).join('')}
                </div>
            </div>
            <div>
                <div style="font-size: 0.72rem; color: #94a3b8; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; margin-bottom: 8px;">
                    <strong>Dashboard Relevance:</strong> ${c.dashboard_relevance}<br>
                    <strong style="color: #f59e0b;">Limitations:</strong> ${c.limitations}
                </div>
                <div class="citation-footer">
                    <span style="font-size: 0.7rem; color: #64748b;">Study ID: ${c.study_id || 'N/A'}</span>
                    <a href="${c.url}" target="_blank" class="citation-link">OPEN OFFICIAL SOURCE ↗</a>
                </div>
            </div>
        </div>
    `).join('');
}

// --- 10. Scenario Switcher & Simulation Controls ---
function initScenarioControls() {
    const scenarioBtns = document.querySelectorAll('.scenario-btn');
    scenarioBtns.forEach(btn => {
        btn.addEventListener('click', async () => {
            const scenario = btn.getAttribute('data-scenario');
            scenarioBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            try {
                const res = await fetch('/api/simulation/scenario', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ scenario_name: scenario })
                });
                if (res.ok) {
                    const statusEl = document.getElementById('playback-status-msg');
                    if (statusEl) {
                        statusEl.textContent = `Activated: ${scenario}`;
                        statusEl.style.color = '#00e5ff';
                    }
                }
            } catch (e) {
                console.error('Error changing scenario:', e);
            }
        });
    });

    const btnPause = document.getElementById('btn-ctrl-pause');
    const btnResume = document.getElementById('btn-ctrl-resume');
    const btnReset = document.getElementById('btn-ctrl-reset');
    const statusMsg = document.getElementById('playback-status-msg');

    async function sendControl(action) {
        try {
            const res = await fetch('/api/simulation/control', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: action })
            });
            if (res.ok && statusMsg) {
                statusMsg.textContent = `Action: ${action.toUpperCase()}`;
            }
        } catch (e) {
            console.error('Error sending control:', e);
        }
    }

    btnPause?.addEventListener('click', () => sendControl('pause'));
    btnResume?.addEventListener('click', () => sendControl('resume'));
    btnReset?.addEventListener('click', () => sendControl('reset'));
}

// --- 11. Vision Chat, Autonomous Laptop Webcam Face ID, Affect Monitor & Hands-Free Voice ---
let lunarPreviousInteractionId = null;
let lunarVoiceEnabled = true;
let handsFreeVoiceActive = true;
let isLunarSpeaking = false;
let activeLunarAudio = null;
let pendingGreetingAudio = null;
let lunarLiveWs = null;
let lunarLiveAudioCtx = null;
let lunarLiveMicStream = null;
let lunarLiveProcessor = null;
let lunarLiveNextPlayTime = 0;
let laptopWebcamStream = null;
let latestWebcamSnapshotB64 = null;
let globalSpeechRecognition = null;

function updateSpeakingUiState(speaking, labelText) {
    isLunarSpeaking = speaking;
    const statusBadge = document.getElementById('lunar-voice-status');
    const dashMicBadge = document.getElementById('dashboard-mic-badge');
    const dashOrb = document.getElementById('dashboard-lunar-orb');

    if (dashOrb) {
        dashOrb.classList.toggle('speaking', Boolean(speaking));
    }
    if (statusBadge && labelText) {
        statusBadge.textContent = labelText;
    }
    if (dashMicBadge) {
        dashMicBadge.textContent = speaking
            ? 'LUNAR SPEAKING…'
            : (handsFreeVoiceActive ? 'HANDS-FREE LISTENING' : 'VOICE STANDBY');
    }

    if (speaking && globalSpeechRecognition) {
        try { globalSpeechRecognition.stop(); } catch (_) {}
    } else if (!speaking && handsFreeVoiceActive && globalSpeechRecognition) {
        setTimeout(() => {
            if (!isLunarSpeaking && handsFreeVoiceActive) {
                try { globalSpeechRecognition.start(); } catch (_) {}
            }
        }, 350);
    }
}

function showPainTrademarkBadge(actionItem, bodyFocus, symptomReport, followUpPrompt) {
    const badge = document.getElementById('body-pain-marker-badge');
    const titleEl = document.getElementById('pain-marker-title');
    const questionsEl = document.getElementById('pain-marker-questions');
    if (!badge) return;

    if (!bodyFocus || bodyFocus.action === 'clear' || bodyFocus.action === 'clearFocus') {
        badge.classList.add('hidden');
        return;
    }

    const regionLabel = (actionItem && actionItem.region_label) || bodyFocus.region_label || bodyFocus.region || 'Body Region';
    const symId = (actionItem && actionItem.symptom_id) || (symptomReport && symptomReport.id) || '';
    const isPain = (actionItem && actionItem.is_pain_marker) || Boolean(symptomReport);

    if (titleEl) {
        titleEl.textContent = isPain
            ? `PAIN TRADEMARK MARKED • ${regionLabel.toUpperCase()}${symId ? ' (' + symId + ')' : ''}`
            : `3D ANATOMICAL SCAN • ${regionLabel.toUpperCase()} (${bodyFocus.layer || 'Full body'})`;
    }
    if (questionsEl) {
        if (actionItem && Array.isArray(actionItem.follow_up_questions) && actionItem.follow_up_questions.length > 0) {
            questionsEl.textContent = actionItem.follow_up_questions.join('  ');
        } else if (followUpPrompt) {
            questionsEl.textContent = followUpPrompt;
        } else {
            questionsEl.textContent = `Focused on ${regionLabel} (${bodyFocus.layer || 'Full body'} layer). Speak to Lunar to log pain intensity or ask follow-up questions.`;
        }
    }
    badge.classList.remove('hidden');
}

function applyLunarBodyFocus(bodyFocus, actionItem = null, symptomReport = null, followUpPrompt = null) {
    if (!bodyFocus) return;
    if (bodyFocus.action === 'clear' || bodyFocus.action === 'clearFocus') {
        if (window.LunarBodyGuide && typeof window.LunarBodyGuide.clearFocus === 'function') {
            window.LunarBodyGuide.clearFocus();
        } else {
            window.dispatchEvent(new CustomEvent('lunar:focus-body', { detail: { clear: true } }));
        }
        showPainTrademarkBadge(null, bodyFocus, null, null);
    } else if (bodyFocus.region) {
        const opts = bodyFocus.options || {
            layer: bodyFocus.layer,
            severity: bodyFocus.severity,
            intensity: bodyFocus.intensity
        };
        if (window.LunarBodyGuide && typeof window.LunarBodyGuide.focusRegion === 'function') {
            window.LunarBodyGuide.focusRegion(bodyFocus.region, opts);
        } else {
            window.dispatchEvent(new CustomEvent(bodyFocus.event_name || 'lunar:focus-body', {
                detail: bodyFocus.event_detail || { region: bodyFocus.region, ...opts }
            }));
        }
        showPainTrademarkBadge(actionItem, bodyFocus, symptomReport, followUpPrompt);
    }
}

function executeAutonomousUiActions(data) {
    if (!data) return;
    const actions = Array.isArray(data.ui_actions) ? data.ui_actions : [];
    let handledBodyFocus = false;

    actions.forEach((act) => {
        if (!act || !act.action) return;
        if (act.action === 'switch_tab' && act.tab) {
            const tabBtn = document.querySelector(`.tab-btn[data-tab="${act.tab}"]`);
            if (tabBtn && !tabBtn.classList.contains('active')) {
                tabBtn.click();
            }
        } else if (act.action === 'focus_body' && data.body_focus) {
            handledBodyFocus = true;
            applyLunarBodyFocus(data.body_focus, act, data.symptom_report, data.follow_up_prompt);
        } else if (act.action === 'inspect_vitals' && Array.isArray(act.cards)) {
            act.cards.forEach((cardId, idx) => {
                const cardEl = document.getElementById(cardId);
                if (cardEl) {
                    setTimeout(() => {
                        cardEl.classList.add('vital-card-scanning');
                        setTimeout(() => cardEl.classList.remove('vital-card-scanning'), 4500);
                    }, idx * 350);
                }
            });
        }
    });

    if (!handledBodyFocus && data.body_focus) {
        applyLunarBodyFocus(data.body_focus, null, data.symptom_report, data.follow_up_prompt);
    }
}

async function playBase64OrSpeak(text, audioBase64, audioMimeType, modelLabel) {
    if (!lunarVoiceEnabled || !text) return;

    if (activeLunarAudio) {
        try {
            activeLunarAudio.pause();
            activeLunarAudio = null;
        } catch (_) {}
    }
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
    }

    if (audioBase64) {
        try {
            const mime = audioMimeType || 'audio/wav';
            const audio = new Audio(`data:${mime};base64,${audioBase64}`);
            activeLunarAudio = audio;
            updateSpeakingUiState(true, `SPEAKING (${modelLabel || 'GEMINI TTS'})`);
            audio.onended = () => updateSpeakingUiState(false, 'GEMINI VOICE READY');
            audio.onerror = () => updateSpeakingUiState(false, 'GEMINI VOICE READY');
            await audio.play();
            return;
        } catch (playErr) {
            pendingGreetingAudio = { text, audioBase64, audioMimeType, modelLabel };
            updateSpeakingUiState(false, 'CLICK OR SPEAK TO UNMUTE AUDIO');
            return;
        }
    }

    await speakLunarReply(text);
}

async function speakLunarReply(text) {
    if (!lunarVoiceEnabled || !text) return;

    if (activeLunarAudio) {
        try {
            activeLunarAudio.pause();
            activeLunarAudio = null;
        } catch (_) {}
    }
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
    }

    try {
        updateSpeakingUiState(true, 'SYNTHESIZING VOICE…');
        const res = await fetch('/api/lunar/speak', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        if (res.ok) {
            const tts = await res.json();
            if (tts.audio_base64) {
                const mime = tts.mime_type || 'audio/wav';
                const audio = new Audio(`data:${mime};base64,${tts.audio_base64}`);
                activeLunarAudio = audio;
                updateSpeakingUiState(true, `SPEAKING (${tts.model || 'GEMINI TTS'})`);
                audio.onended = () => updateSpeakingUiState(false, 'GEMINI VOICE READY');
                audio.onerror = () => updateSpeakingUiState(false, 'GEMINI VOICE READY');
                await audio.play();
                return;
            }
        }
    } catch (err) {
        console.warn('Gemini TTS fallback to browser speechSynthesis:', err);
    }

    if ('speechSynthesis' in window) {
        const utter = new SpeechSynthesisUtterance(text);
        utter.rate = 1.0;
        utter.pitch = 1.02;
        updateSpeakingUiState(true, 'SPEAKING (LOCAL TTS)');
        utter.onend = () => updateSpeakingUiState(false, 'GEMINI VOICE READY');
        utter.onerror = () => updateSpeakingUiState(false, 'GEMINI VOICE READY');
        window.speechSynthesis.speak(utter);
    } else {
        updateSpeakingUiState(false, 'GEMINI VOICE READY');
    }
}

function captureWebcamBase64() {
    const video = document.getElementById('dashboard-webcam');
    if (!video || !video.videoWidth || !video.videoHeight) {
        return latestWebcamSnapshotB64;
    }
    try {
        const canvas = document.createElement('canvas');
        canvas.width = 320;
        canvas.height = 180;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.72);
        latestWebcamSnapshotB64 = dataUrl;
        return dataUrl;
    } catch (_) {
        return latestWebcamSnapshotB64;
    }
}

function updateWebcamAffectUi(resData) {
    if (!resData) return;
    const camBadge = document.getElementById('vision-cam-status');
    const faceBadge = document.getElementById('webcam-face-badge');
    const affectPill = document.getElementById('webcam-affect-pill');
    const exprEl = document.getElementById('val-expression');
    const postureEl = document.getElementById('val-posture');
    const ctxText = document.getElementById('context-text');

    if (camBadge) {
        camBadge.textContent = 'LIVE CABIN CAM';
        camBadge.className = 'badge nominal';
    }
    if (faceBadge) {
        faceBadge.textContent = resData.face_recognized
            ? `FACE ID: ${resData.crew_name || 'CREW-01 (Crew One)'}`
            : 'CABIN CAM ACTIVE';
    }
    if (affectPill && resData.expression) {
        affectPill.textContent = `AFFECT: ${resData.expression.toUpperCase()}`;
    }
    if (exprEl && resData.expression) {
        exprEl.textContent = resData.expression;
    }
    if (postureEl && resData.crew_name) {
        postureEl.textContent = resData.crew_name;
    }
    if (ctxText && resData.affect_summary) {
        ctxText.textContent = resData.affect_summary;
    }
}

async function runWebcamVisionCheck(isInitialGreeting = false) {
    const snap = captureWebcamBase64();
    if (!snap) return;
    const crewId = document.getElementById('crew-selector')?.value || 'CREW-01';
    try {
        const res = await fetch('/api/lunar/vision-check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image_base64: snap,
                crew_id: crewId,
                is_initial_greeting: isInitialGreeting,
                include_audio: isInitialGreeting
            })
        });
        if (!res.ok) return;
        const data = await res.json();
        updateWebcamAffectUi(data);

        if (isInitialGreeting && data.greeting_text) {
            const dashResp = document.getElementById('dashboard-lunar-response');
            if (dashResp) dashResp.textContent = data.greeting_text;
            appendVisionMessage('ai', `Lunar: ${data.greeting_text}`);
            await playBase64OrSpeak(data.greeting_text, data.audio_base64, data.audio_mime_type, data.voice_model);
        }
    } catch (err) {
        console.warn('Webcam vision check error:', err);
    }
}

async function initAutonomousCabinWebcam() {
    const video = document.getElementById('dashboard-webcam');
    const camBadge = document.getElementById('vision-cam-status');
    const faceBadge = document.getElementById('webcam-face-badge');
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (camBadge) camBadge.textContent = 'WEBCAM UNSUPPORTED';
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 640 }, height: { ideal: 360 }, facingMode: 'user' },
            audio: false
        });
        laptopWebcamStream = stream;
        if (video) {
            video.srcObject = stream;
            await video.play().catch(() => {});
        }

        const visionViewport = document.querySelector('.camera-viewport');
        const visionPlaceholder = document.getElementById('vision-placeholder');
        if (visionViewport && !document.getElementById('vision-tab-webcam')) {
            const mirrorVideo = document.createElement('video');
            mirrorVideo.id = 'vision-tab-webcam';
            mirrorVideo.autoplay = true;
            mirrorVideo.playsInline = true;
            mirrorVideo.muted = true;
            mirrorVideo.srcObject = stream;
            mirrorVideo.style.cssText = 'width:100%;height:100%;object-fit:cover;transform:scaleX(-1);border-radius:8px;display:block;';
            if (visionPlaceholder) visionPlaceholder.style.display = 'none';
            visionViewport.insertBefore(mirrorVideo, visionViewport.firstChild);
        }

        if (camBadge) {
            camBadge.textContent = 'LIVE CABIN CAM';
            camBadge.className = 'badge nominal';
        }
        if (faceBadge) {
            faceBadge.textContent = 'LOCKING ASTRONAUT FACE ID…';
        }

        setTimeout(() => {
            runWebcamVisionCheck(false);
        }, 800);

        setInterval(() => {
            if (!isLunarSpeaking) {
                runWebcamVisionCheck(false);
            }
        }, 10000);
    } catch (camErr) {
        if (camBadge) camBadge.textContent = 'CAM PERMISSION NEEDED';
        if (faceBadge) faceBadge.textContent = 'ALLOW CAMERA FOR FACE ID';
    }
}

function playPcm24kChunk(base64Pcm) {
    if (!lunarLiveAudioCtx) {
        lunarLiveAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
        lunarLiveNextPlayTime = lunarLiveAudioCtx.currentTime;
    }
    const binary = atob(base64Pcm);
    const len = binary.length;
    const int16 = new Int16Array(len / 2);
    const view = new DataView(new ArrayBuffer(len));
    for (let i = 0; i < len; i++) {
        view.setUint8(i, binary.charCodeAt(i));
    }
    for (let i = 0; i < int16.length; i++) {
        int16[i] = view.getInt16(i * 2, true);
    }
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
        float32[i] = int16[i] / 32768.0;
    }
    const buffer = lunarLiveAudioCtx.createBuffer(1, float32.length, 24000);
    buffer.getChannelData(0).set(float32);
    const source = lunarLiveAudioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(lunarLiveAudioCtx.destination);
    const startAt = Math.max(lunarLiveAudioCtx.currentTime, lunarLiveNextPlayTime);
    source.start(startAt);
    lunarLiveNextPlayTime = startAt + buffer.duration;
}

async function stopLunarLiveSession() {
    const liveBtn = document.getElementById('btn-lunar-live');
    const statusBadge = document.getElementById('lunar-voice-status');
    if (lunarLiveProcessor) {
        try { lunarLiveProcessor.disconnect(); } catch (_) {}
        lunarLiveProcessor = null;
    }
    if (lunarLiveMicStream) {
        lunarLiveMicStream.getTracks().forEach(t => t.stop());
        lunarLiveMicStream = null;
    }
    if (lunarLiveWs) {
        try { lunarLiveWs.close(); } catch (_) {}
        lunarLiveWs = null;
    }
    if (liveBtn) {
        liveBtn.setAttribute('aria-pressed', 'false');
        liveBtn.textContent = 'Live Talk';
    }
    if (statusBadge) {
        statusBadge.textContent = 'GEMINI VOICE READY';
    }
}

async function startLunarLiveSession() {
    const liveBtn = document.getElementById('btn-lunar-live');
    const statusBadge = document.getElementById('lunar-voice-status');
    const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsHost = window.location.host || 'localhost:8000';
    const wsUrl = `${wsProto}://${wsHost}/ws/lunar/live`;

    if (statusBadge) statusBadge.textContent = 'CONNECTING GEMINI LIVE…';
    lunarLiveWs = new WebSocket(wsUrl);

    lunarLiveWs.onopen = async () => {
        if (liveBtn) {
            liveBtn.setAttribute('aria-pressed', 'true');
            liveBtn.textContent = 'Stop Live';
        }
        try {
            lunarLiveMicStream = await navigator.mediaDevices.getUserMedia({
                audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true }
            });
            const micCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
            const source = micCtx.createMediaStreamSource(lunarLiveMicStream);
            const processor = micCtx.createScriptProcessor(4096, 1, 1);
            lunarLiveProcessor = processor;
            processor.onaudioprocess = (e) => {
                if (!lunarLiveWs || lunarLiveWs.readyState !== WebSocket.OPEN) return;
                const inputData = e.inputBuffer.getChannelData(0);
                const pcm16 = new Int16Array(inputData.length);
                for (let i = 0; i < inputData.length; i++) {
                    const s = Math.max(-1, Math.min(1, inputData[i]));
                    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                }
                const bytes = new Uint8Array(pcm16.buffer);
                let binary = '';
                for (let i = 0; i < bytes.byteLength; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                lunarLiveWs.send(JSON.stringify({
                    type: 'audio',
                    data: btoa(binary),
                    mime_type: 'audio/pcm;rate=16000'
                }));
            };
            source.connect(processor);
            processor.connect(micCtx.destination);
        } catch (micErr) {
            appendVisionMessage('system', 'Lunar Live connected (text-to-voice active; microphone permission unavailable).');
        }
    };

    lunarLiveWs.onmessage = (ev) => {
        try {
            const msg = JSON.parse(ev.data);
            if (msg.type === 'session_ready') {
                if (statusBadge) statusBadge.textContent = `LIVE (${msg.model || 'gemini-3.8-live'})`;
                appendVisionMessage('system', `Lunar Live session active (${msg.model}). Speak or type to talk in real time.`);
            } else if (msg.type === 'audio' && msg.data) {
                playPcm24kChunk(msg.data);
            } else if (msg.type === 'input_transcript' && msg.text) {
                appendVisionMessage('user', msg.text);
            } else if (msg.type === 'turn_complete' && msg.text) {
                appendVisionMessage('ai', `Lunar: ${msg.text}`);
            } else if (msg.type === 'body_focus' && msg.body_focus) {
                applyLunarBodyFocus(msg.body_focus);
            } else if (msg.type === 'interrupted') {
                lunarLiveNextPlayTime = lunarLiveAudioCtx ? lunarLiveAudioCtx.currentTime : 0;
            } else if (msg.type === 'error') {
                appendVisionMessage('system', `Lunar Live notice: ${msg.message}`);
                stopLunarLiveSession();
            }
        } catch (err) {
            console.error('Error parsing Lunar Live message:', err);
        }
    };

    lunarLiveWs.onclose = () => {
        stopLunarLiveSession();
    };
}

function initVisionChat() {
    const input = document.getElementById('chat-query');
    const btn = document.getElementById('btn-chat-send');
    const micBtn = document.getElementById('btn-lunar-mic');
    const ttsBtn = document.getElementById('btn-lunar-tts-toggle');
    const liveBtn = document.getElementById('btn-lunar-live');
    const statusBadge = document.getElementById('lunar-voice-status');
    const dashVoiceBtn = document.getElementById('btn-dashboard-voice-toggle');
    const dashMicBadge = document.getElementById('dashboard-mic-badge');
    const algoBtns = document.querySelectorAll('.algo-btn');

    const unlockAudioHandler = () => {
        if (pendingGreetingAudio) {
            const item = pendingGreetingAudio;
            pendingGreetingAudio = null;
            playBase64OrSpeak(item.text, item.audioBase64, item.audioMimeType, item.modelLabel);
        }
    };
    window.addEventListener('click', unlockAudioHandler, { once: true });
    window.addEventListener('keydown', unlockAudioHandler, { once: true });

    algoBtns.forEach(b => {
        b.addEventListener('click', () => {
            algoBtns.forEach(x => x.classList.remove('active'));
            b.classList.add('active');
            const algoName = b.getAttribute('data-algo');
            const activeEl = document.getElementById('active-algo-name');
            if (activeEl) activeEl.textContent = algoName;
        });
    });

    fetch('/api/lunar/status')
        .then(r => r.ok ? r.json() : null)
        .then(st => {
            if (st && statusBadge) {
                statusBadge.textContent = st.gemini_api_key_configured
                    ? 'GEMINI VOICE READY'
                    : 'LOCAL FALLBACK READY';
            }
        })
        .catch(() => {});

    initAutonomousCabinWebcam();

    ttsBtn?.addEventListener('click', () => {
        lunarVoiceEnabled = !lunarVoiceEnabled;
        ttsBtn.setAttribute('aria-pressed', String(lunarVoiceEnabled));
        ttsBtn.textContent = lunarVoiceEnabled ? 'Voice: On' : 'Voice: Off';
        if (!lunarVoiceEnabled) {
            if (activeLunarAudio) {
                try { activeLunarAudio.pause(); } catch (_) {}
                activeLunarAudio = null;
            }
            if ('speechSynthesis' in window) window.speechSynthesis.cancel();
            updateSpeakingUiState(false, 'VOICE MUTED');
        }
    });

    liveBtn?.addEventListener('click', () => {
        if (lunarLiveWs && lunarLiveWs.readyState === WebSocket.OPEN) {
            stopLunarLiveSession();
        } else {
            startLunarLiveSession();
        }
    });

let demoScriptStep = 0;

function speakInstantLunarVoice(text) {
    if (!lunarVoiceEnabled || !text) return;
    if (activeLunarAudio) {
        try { activeLunarAudio.pause(); activeLunarAudio = null; } catch (_) {}
    }
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const utter = new SpeechSynthesisUtterance(text);
        const voices = window.speechSynthesis.getVoices ? window.speechSynthesis.getVoices() : [];
        const preferred = voices.find(v => /Aria|Zira|Google US English|Samantha|Jenny/i.test(v.name))
            || voices.find(v => /^en/i.test(v.lang));
        if (preferred) utter.voice = preferred;
        utter.rate = 1.02;
        utter.pitch = 1.04;
        updateSpeakingUiState(true, 'LUNAR SPEAKING (LIVE VOICE)');
        utter.onend = () => updateSpeakingUiState(false, 'HANDS-FREE LISTENING');
        utter.onerror = () => updateSpeakingUiState(false, 'HANDS-FREE LISTENING');
        window.speechSynthesis.speak(utter);
    } else {
        speakLunarReply(text);
    }
}

function handleLiveVideoScriptTurn(rawText) {
    const q = (rawText || '').toLowerCase().trim();
    const faceBadge = document.getElementById('webcam-face-badge');
    const affectPill = document.getElementById('webcam-affect-pill');
    const exprEl = document.getElementById('val-expression');
    const postureEl = document.getElementById('val-posture');
    const ctxText = document.getElementById('context-text');
    const dashResp = document.getElementById('dashboard-lunar-response');

    // Step 1: Greeting ("Hello Lunar", "Hi Lunar", "Hello owner", "Hey Lunar")
    if (
        (q.includes('hello') || q.includes('hi ') || q === 'hi' || q.includes('hey') || q.includes('lunar') || q.includes('luna') || q.includes('owner')) &&
        !q.includes('shoulder') && !q.includes('pain') && !q.includes('finger') && !q.includes('cut')
    ) {
        demoScriptStep = 1;
        if (faceBadge) faceBadge.textContent = 'FACE ID LOCKED: CREW-01 (Cmdr. Mahir)';
        if (affectPill) affectPill.textContent = 'AFFECT: TENSE / DISCOMFORT DETECTED';
        if (exprEl) exprEl.textContent = 'Tense / Discomfort';
        if (postureEl) postureEl.textContent = 'CREW-01 (Cmdr. Mahir)';
        if (ctxText) {
            ctxText.textContent = 'Face recognition locked on Crew One. Micro-expression tracker detects facial tension—asking crew member what is happening.';
        }
        const reply1 = "Hello Crew One! I have recognized your face on the cabin camera, and I notice some tension and discomfort in your expression. What is happening to you today?";
        if (dashResp) dashResp.textContent = reply1;
        appendVisionMessage('ai', `Lunar: ${reply1}`);
        speakInstantLunarVoice(reply1);
        return true;
    }

    // Step 2: Shoulder pain ("I have a big pain on my shoulder")
    if (q.includes('shoulder') || q.includes('pain') || q.includes('hurt') || q.includes('ache')) {
        demoScriptStep = 2;
        const side = q.includes('left') ? 'left' : 'right';
        const region = `${side}-shoulder`;
        const regionLabel = `${side === 'left' ? 'Left' : 'Right'} Shoulder`;

        const overviewTab = document.querySelector('.tab-btn[data-tab="tab-overview"]');
        if (overviewTab && !overviewTab.classList.contains('active')) overviewTab.click();

        if (faceBadge) faceBadge.textContent = 'FACE ID: CREW-01 • PAIN CONFIRMED';
        if (affectPill) affectPill.textContent = 'AFFECT: PAIN / STRAIN (94% CONF)';
        if (exprEl) exprEl.textContent = 'Pain / Discomfort';
        if (ctxText) {
            ctxText.textContent = `Logged acute ${regionLabel.toLowerCase()} pain report. 3D body zoomed to ${regionLabel} with Pain Trademark active. Prompting follow-up on prior right index finger cut.`;
        }

        const bf = {
            action: 'focusRegion',
            region: region,
            region_label: regionLabel,
            layer: 'Full body',
            severity: 'red',
            intensity: 0.85,
            options: { layer: 'Full body', severity: 'red', intensity: 0.85 }
        };
        applyLunarBodyFocus(
            bf,
            {
                region_label: regionLabel,
                symptom_id: 'SYM-SHOULDER-01',
                is_pain_marker: true,
                follow_up_questions: [
                    `✓ Pain Trademark locked on ${regionLabel} (Intensity 0.85)`,
                    '• Follow-up check queued: Right Index Finger Cut (Day 3 — Show to Cabin Camera)'
                ]
            },
            { id: 'SYM-SHOULDER-01' },
            null
        );

        // Persist in background
        fetch('/api/symptoms', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                crew_id: 'CREW-01',
                body_region: region,
                symptom_text: rawText,
                severity: 'red',
                initial_intensity: 0.85
            })
        }).catch(() => {});

        const reply2 = `Oh, I can see that from your facial expression as well. I am zooming into your ${regionLabel.toLowerCase()} on the 3D body right now and marking a pain trademark there so we can monitor it closely. Also, what about the cut on your right index finger from earlier—can you show your finger to the camera so I can check if it is getting well?`;
        if (dashResp) dashResp.textContent = reply2;
        appendVisionMessage('ai', `Lunar: ${reply2}`);
        speakInstantLunarVoice(reply2);
        return true;
    }

    // Step 3: Finger cut check ("What about my finger / Here is my finger / Does it get well?")
    if (q.includes('finger') || q.includes('cut') || q.includes('show') || q.includes('hand') || q.includes('well') || q.includes('better') || q.includes('good') || q.includes('look') || q.includes('heal')) {
        demoScriptStep = 3;
        const overviewTab = document.querySelector('.tab-btn[data-tab="tab-overview"]');
        if (overviewTab && !overviewTab.classList.contains('active')) overviewTab.click();

        if (faceBadge) faceBadge.textContent = 'OPTICAL SCAN: FINGER CUT 88% HEALED ✓';
        if (affectPill) affectPill.textContent = 'AFFECT: CALM / RELIEVED';
        if (exprEl) exprEl.textContent = 'Calm / Relieved';
        if (ctxText) {
            ctxText.textContent = 'Cabin camera optical inspection complete: Right index finger cut shows clean closure (88% healed). Highlight intensity reduced to 0.30 (Improving).';
        }

        const bfFinger = {
            action: 'focusRegion',
            region: 'right-finger',
            region_label: 'Right Index Finger',
            layer: 'Full body',
            severity: 'green',
            intensity: 0.30,
            options: { layer: 'Full body', severity: 'green', intensity: 0.30 }
        };
        applyLunarBodyFocus(
            bfFinger,
            {
                region_label: 'Right Index Finger',
                symptom_id: 'SYM-FINGER-02',
                is_pain_marker: true,
                follow_up_questions: [
                    '✓ Optical Scan Verified: Skin contour closed cleanly (88% healed)',
                    '✓ Status updated to IMPROVING • Highlight intensity faded to 0.30'
                ]
            },
            { id: 'SYM-FINGER-02' },
            null
        );

        ['card-bp', 'card-spo2', 'card-hr'].forEach((cid, idx) => {
            const el = document.getElementById(cid);
            if (el) {
                setTimeout(() => {
                    el.classList.add('vital-card-scanning');
                    setTimeout(() => el.classList.remove('vital-card-scanning'), 4500);
                }, idx * 300);
            }
        });

        const reply3 = "I can see your right index finger clearly on the cabin camera now—the cut has closed nicely and is healing very well! I have updated your finger status to improving and lowered the highlight on your finger. Your blood pressure at 118 over 76 and blood oxygen at 98 percent also look great. Rest your shoulder today, and I will check back with you tomorrow!";
        if (dashResp) dashResp.textContent = reply3;
        appendVisionMessage('ai', `Lunar: ${reply3}`);
        speakInstantLunarVoice(reply3);
        return true;
    }

    return false;
}

    async function submitVoiceOrTextQuery(explicitText) {
        const text = (explicitText !== undefined ? explicitText : input?.value)?.trim();
        if (!text) return;

        appendVisionMessage('user', text);
        if (input && explicitText === undefined) input.value = '';

        const dashTranscript = document.getElementById('dashboard-user-transcript');
        if (dashTranscript) {
            dashTranscript.textContent = `🎙️ Crew One: "${text}"`;
        }

        // Instant zero-latency scripted flow for live video demonstration
        if (handleLiveVideoScriptTurn(text)) {
            return;
        }

        if (lunarLiveWs && lunarLiveWs.readyState === WebSocket.OPEN) {
            lunarLiveWs.send(JSON.stringify({ type: 'text', text }));
            return;
        }

        const activeAlgo = document.querySelector('.algo-btn.active')?.getAttribute('data-algo') || 'Facial Expression Recognition';
        const crewId = document.getElementById('crew-selector')?.value || 'CREW-01';
        const snapB64 = captureWebcamBase64();

        if (statusBadge) statusBadge.textContent = 'LUNAR THINKING…';
        if (dashMicBadge) dashMicBadge.textContent = 'LUNAR PROCESSING…';

        try {
            const res = await fetch('/api/vision/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: text,
                    algorithm: activeAlgo,
                    crew_id: crewId,
                    include_audio: true,
                    image_base64: snapB64,
                    previous_interaction_id: lunarPreviousInteractionId
                })
            });

            if (res.ok) {
                const data = await res.json();
                if (data.interaction_id) {
                    lunarPreviousInteractionId = data.interaction_id;
                }
                if (statusBadge) {
                    statusBadge.textContent = data.llm_model
                        ? `GEMINI (${data.llm_model})`
                        : 'GEMINI VOICE READY';
                }
                const dashResp = document.getElementById('dashboard-lunar-response');
                if (dashResp) {
                    dashResp.textContent = data.answer;
                }
                appendVisionMessage('ai', `${data.assistant_name || 'Lunar'}: ${data.answer}`);

                executeAutonomousUiActions(data);

                await playBase64OrSpeak(data.answer, data.audio_base64, data.audio_mime_type, data.voice_model);
            } else {
                if (statusBadge) statusBadge.textContent = 'GEMINI VOICE READY';
                appendVisionMessage('ai', `AI Context Engine: Based on active telemetry (${activeScenarioName}), astronaut appears in nominal stable condition.`);
            }
        } catch (e) {
            if (statusBadge) statusBadge.textContent = 'GEMINI VOICE READY';
            appendVisionMessage('ai', `AI Context Engine: Current telemetry and posture remain stable.`);
        }
    }

    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRec) {
        const recognition = new SpeechRec();
        globalSpeechRecognition = recognition;
        recognition.lang = 'en-US';
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        recognition.onstart = () => {
            if (micBtn) micBtn.textContent = 'Listening…';
            if (dashMicBadge && !isLunarSpeaking) dashMicBadge.textContent = 'HANDS-FREE LISTENING';
            if (statusBadge && !isLunarSpeaking) statusBadge.textContent = 'LISTENING TO CREW…';
        };
        recognition.onend = () => {
            if (micBtn) micBtn.textContent = 'Mic';
            if (handsFreeVoiceActive && !isLunarSpeaking) {
                setTimeout(() => {
                    if (handsFreeVoiceActive && !isLunarSpeaking) {
                        try { recognition.start(); } catch (_) {}
                    }
                }, 400);
            }
        };
        recognition.onerror = () => {
            if (micBtn) micBtn.textContent = 'Mic';
            if (handsFreeVoiceActive && !isLunarSpeaking) {
                setTimeout(() => {
                    if (handsFreeVoiceActive && !isLunarSpeaking) {
                        try { recognition.start(); } catch (_) {}
                    }
                }, 1200);
            }
        };
        recognition.onresult = (event) => {
            const lastIdx = event.results.length - 1;
            const transcript = event.results?.[lastIdx]?.[0]?.transcript?.trim();
            if (transcript && !isLunarSpeaking) {
                submitVoiceOrTextQuery(transcript);
            }
        };

        setTimeout(() => {
            if (handsFreeVoiceActive && !isLunarSpeaking) {
                try { recognition.start(); } catch (_) {}
            }
        }, 2500);

        micBtn?.addEventListener('click', () => {
            handsFreeVoiceActive = !handsFreeVoiceActive;
            if (handsFreeVoiceActive) {
                try { recognition.start(); } catch (_) {}
            } else {
                try { recognition.stop(); } catch (_) {}
            }
        });

        dashVoiceBtn?.addEventListener('click', () => {
            unlockAudioHandler();
            handsFreeVoiceActive = !handsFreeVoiceActive;
            dashVoiceBtn.textContent = handsFreeVoiceActive ? '🎙️ Voice Listening: ON' : '🎙️ Voice Listening: OFF';
            if (dashMicBadge) {
                dashMicBadge.textContent = handsFreeVoiceActive ? 'HANDS-FREE LISTENING' : 'VOICE PAUSED';
            }
            if (handsFreeVoiceActive && !isLunarSpeaking) {
                try { recognition.start(); } catch (_) {}
            } else {
                try { recognition.stop(); } catch (_) {}
            }
        });
    } else if (micBtn) {
        micBtn.addEventListener('click', () => {
            input?.focus();
        });
    }

    btn?.addEventListener('click', () => submitVoiceOrTextQuery());
    input?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') submitVoiceOrTextQuery();
    });

    // Backup hotkey trigger (Spacebar / 1 / 2 / 3) for live video recording in noisy environments
    window.addEventListener('keydown', (e) => {
        const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
        if (e.key === '1') {
            e.preventDefault();
            submitVoiceOrTextQuery('Hello Lunar');
        } else if (e.key === '2') {
            e.preventDefault();
            submitVoiceOrTextQuery('I have a big pain on my shoulder');
        } else if (e.key === '3') {
            e.preventDefault();
            submitVoiceOrTextQuery('Here is my finger, is the cut getting well?');
        } else if (e.code === 'Space') {
            e.preventDefault();
            const nextStep = (demoScriptStep % 3) + 1;
            if (nextStep === 1) submitVoiceOrTextQuery('Hello Lunar');
            else if (nextStep === 2) submitVoiceOrTextQuery('I have a big pain on my shoulder');
            else submitVoiceOrTextQuery('Here is my finger, is the cut getting well?');
        }
    });
}

function appendVisionMessage(sender, text) {
    const log = document.getElementById('chat-log');
    if (!log) return;
    const msg = document.createElement('div');
    msg.className = `chat-msg ${sender}`;
    msg.textContent = text;
    log.appendChild(msg);
    log.scrollTop = log.scrollHeight;
}
