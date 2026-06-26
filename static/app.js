const API_URL = '/api/stats';
let winRateChart = null;

function formatMoney(amount) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(amount);
}

async function toggleBot() {
    try {
        await fetch('/api/toggle', { method: 'POST' });
        fetchStats(); // Forzar actualización visual inmediata
    } catch (e) {
        console.error("Error toggling bot", e);
    }
}

async function togglePar(par) {
    try {
        await fetch('/api/toggle_par', { 
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ par: par })
        });
        fetchStats();
    } catch (e) {
        console.error("Error toggling par", e);
    }
}

function processChartData(historial, timeframe) {
    const groups = {};
    
    historial.forEach(op => {
        const date = new Date(op.timestamp * 1000);
        let key = '';
        
        if (timeframe === 'daily') {
            key = date.toISOString().split('T')[0]; // YYYY-MM-DD
        } else if (timeframe === 'monthly') {
            key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`; // YYYY-MM
        } else if (timeframe === 'weekly') {
            // Aproximación simple: Año + Semana del año
            const firstDay = new Date(date.getFullYear(), 0, 1);
            const pastDays = (date - firstDay) / 86400000;
            const weekNum = Math.ceil((pastDays + firstDay.getDay() + 1) / 7);
            key = `${date.getFullYear()}-W${weekNum}`;
        }

        if (!groups[key]) {
            groups[key] = { total: 0, ganadoras: 0 };
        }
        groups[key].total += 1;
        if (op.ganadora) {
            groups[key].ganadoras += 1;
        }
    });

    const labels = Object.keys(groups).sort();
    const dataPoints = labels.map(label => {
        const g = groups[label];
        return g.total === 0 ? 0 : (g.ganadoras / g.total) * 100;
    });

    return { labels, dataPoints };
}

function renderChart(historial) {
    const timeframe = document.getElementById('chart-timeframe').value;
    const chartData = processChartData(historial, timeframe);
    
    const ctx = document.getElementById('winRateChart').getContext('2d');
    
    if (winRateChart) {
        winRateChart.destroy();
    }
    
    // Gradient styling
    const gradient = ctx.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(59, 130, 246, 0.5)');
    gradient.addColorStop(1, 'rgba(59, 130, 246, 0.0)');

    Chart.defaults.color = '#94a3b8';
    Chart.defaults.font.family = "'Inter', sans-serif";

    winRateChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartData.labels,
            datasets: [{
                label: 'Win Rate (%)',
                data: chartData.dataPoints,
                borderColor: '#3b82f6',
                backgroundColor: gradient,
                borderWidth: 3,
                pointBackgroundColor: '#10b981',
                pointBorderColor: '#fff',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleFont: { size: 13 },
                    bodyFont: { size: 14, weight: 'bold' },
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        label: function(context) {
                            return `Win Rate: ${context.parsed.y.toFixed(1)}%`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                x: {
                    grid: { display: false }
                }
            }
        }
    });
}

// Re-render chart when dropdown changes
document.getElementById('chart-timeframe').addEventListener('change', () => {
    if (window.lastHistorial) {
        renderChart(window.lastHistorial);
    }
});

function updateDashboard(data) {
    // Actualizar Estado
    const statusDot = document.getElementById('status-dot');
    const botStatus = document.getElementById('bot-status');
    
    if (data.control.bot_activo) {
        statusDot.classList.add('active');
        botStatus.textContent = 'ONLINE (Click para Pausar)';
        botStatus.className = 'status-badge online';
    } else {
        statusDot.classList.remove('active');
        botStatus.textContent = 'PAUSADO (Click para Iniciar)';
        botStatus.className = 'status-badge offline';
    }

    // Actualizar Tarjetas Principales
    document.getElementById('saldo-total').textContent = formatMoney(data.sesion.saldo);
    
    const rent = ((data.sesion.saldo - data.sesion.saldo_inicial) / data.sesion.saldo_inicial) * 100;
    const rentBadge = document.getElementById('rentabilidad');
    rentBadge.textContent = `${rent >= 0 ? '+' : ''}${rent.toFixed(2)}%`;
    rentBadge.className = `badge ${rent >= 0 ? 'positive' : 'negative'}`;

    let totales = data.sesion.operaciones_totales;
    let winRate = 0;
    if (totales > 0) {
        let ganadoras = 0;
        for (const par in data.sesion.por_par) {
            ganadoras += data.sesion.por_par[par].ganadoras;
        }
        winRate = (ganadoras / totales) * 100;
    }
    document.getElementById('win-rate').textContent = `${winRate.toFixed(1)}%`;
    document.getElementById('ops-totales').textContent = totales;

    document.getElementById('pnl-total').textContent = formatMoney(data.sesion.ganancia_total);
    document.getElementById('racha').textContent = data.sesion.racha_actual;

    // Actualizar Tarjetas de Mercado
    const container = document.getElementById('markets-container');
    container.innerHTML = ''; 

    for (const [par, pos] of Object.entries(data.posiciones)) {
        const card = document.createElement('div');
        card.className = 'glass-card market-card';

        let badgeClass = 'pos-none';
        let badgeText = 'Buscando Señal';
        let pnlHtml = '';
        
        // Obtener si el par está activo en la config del bot
        const par_activo = data.control.pares_activos && data.control.pares_activos[par] !== false;

        if (pos.abierta) {
            badgeClass = pos.direccion === 'long' ? 'pos-long' : 'pos-short';
            badgeText = pos.direccion.toUpperCase();

            let pnlPct = 0;
            if (pos.direccion === 'long') {
                pnlPct = ((pos.ultimo_precio - pos.precio_entrada) / pos.precio_entrada) * 100 * 5; 
            } else {
                pnlPct = ((pos.precio_entrada - pos.ultimo_precio) / pos.precio_entrada) * 100 * 5;
            }

            const pnlColorClass = pnlPct >= 0 ? 'green' : 'red';
            pnlHtml = `
                <div class="market-pnl">
                    <span class="data-label">PnL Estimado</span>
                    <span class="pnl-value ${pnlColorClass}">${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%</span>
                </div>
            `;
        }

        card.innerHTML = `
            <div class="market-header">
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <h3>${par}</h3>
                    <button class="par-toggle ${par_activo ? 'active' : ''}" onclick="togglePar('${par}')">${par_activo ? 'ON' : 'OFF'}</button>
                </div>
                <span class="pos-badge ${badgeClass}">${badgeText}</span>
            </div>
            <div class="market-data">
                <span class="data-label">Precio Act:</span>
                <span class="data-value">${pos.ultimo_precio.toFixed(4)}</span>
                
                <span class="data-label">RSI 3m:</span>
                <span class="data-value">${pos.ultimo_rsi.toFixed(1)}</span>
                
                <span class="data-label">Tend 5m:</span>
                <span class="data-value">${pos.tend_5m}</span>
                
                ${pos.abierta ? `
                <span class="data-label">Entrada:</span>
                <span class="data-value">${pos.precio_entrada.toFixed(4)}</span>
                
                <span class="data-label">Stop Loss:</span>
                <span class="data-value">${pos.stop_loss.toFixed(4)}</span>
                ` : ''}
            </div>
            ${pnlHtml}
        `;
        container.appendChild(card);
    }
    
    // Actualizar gráfico si hay historial
    if (data.historial && data.historial.length > 0) {
        window.lastHistorial = data.historial;
        if (!winRateChart) {
            renderChart(data.historial);
        } else {
            // Actualizar datos sin destruir
            const timeframe = document.getElementById('chart-timeframe').value;
            const chartData = processChartData(data.historial, timeframe);
            winRateChart.data.labels = chartData.labels;
            winRateChart.data.datasets[0].data = chartData.dataPoints;
            winRateChart.update();
        }
    }

    // Renderizar Logs
    function renderLogs(containerId, logs) {
        const container = document.getElementById(containerId);
        if (!logs || logs.length === 0) {
            container.innerHTML = '<div style="text-align:center; padding: 2rem 0; opacity: 0.5;">Sin registros aún...</div>';
            return;
        }

        let html = '';
        logs.forEach(log => {
            const timeStr = new Date(log.timestamp * 1000).toLocaleTimeString();
            const msgHtml = log.mensaje.replace(/\n/g, '<br>');
            html += `
                <div class="log-entry">
                    <span class="log-time">[${timeStr}]</span>
                    <span>${msgHtml}</span>
                </div>
            `;
        });
        
        // Solo actualizar si el contenido cambió para no arruinar el scroll si el usuario está leyendo
        if (container.dataset.lastCount !== logs.length.toString()) {
            container.innerHTML = html;
            container.scrollTop = container.scrollHeight; // Auto-scroll al fondo
            container.dataset.lastCount = logs.length.toString();
        }
    }

    renderLogs('logs-entradas', data.logs_entradas);
    renderLogs('logs-generales', data.logs_generales);
}

async function fetchStats() {
    try {
        const response = await fetch(API_URL);
        const data = await response.json();
        updateDashboard(data);
    } catch (error) {
        console.error("Error fetching stats:", error);
    }
}

setInterval(fetchStats, 5000);
fetchStats();
