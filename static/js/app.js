/**
 * INvest - Stock Analysis Dashboard Frontend
 * Probability-based analysis, NOT investment recommendations.
 */

let backtestData = null;
let charts = {};

const HEBREW_MONTHS = {
    '01': 'ינואר', '02': 'פברואר', '03': 'מרץ', '04': 'אפריל',
    '05': 'מאי', '06': 'יוני', '07': 'יולי', '08': 'אוגוסט',
    '09': 'ספטמבר', '10': 'אוקטובר', '11': 'נובמבר', '12': 'דצמבר'
};

function formatMonth(yearMonth) {
    const [year, month] = yearMonth.split('-');
    return `${HEBREW_MONTHS[month]} ${year}`;
}

function formatPercent(val) {
    if (val === null || val === undefined) return '-';
    const sign = val >= 0 ? '+' : '';
    return `${sign}${val.toFixed(1)}%`;
}

function formatProbability(val) {
    if (val === null || val === undefined) return '-';
    return `${(val * 100).toFixed(0)}%`;
}

function getReturnClass(val) {
    if (val === null || val === undefined) return '';
    return val >= 0 ? 'positive-val' : 'negative-val';
}

function getProbClass(val) {
    if (val >= 0.65) return 'positive-val';
    if (val <= 0.45) return 'negative-val';
    return '';
}

async function runBacktest() {
    const monthsBack = parseInt(document.getElementById('months-back').value);
    const topN = parseInt(document.getElementById('top-n').value);
    const btn = document.getElementById('run-backtest');
    const loading = document.getElementById('loading');

    btn.disabled = true;
    loading.classList.remove('hidden');

    try {
        const response = await fetch('/api/run-backtest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ months_back: monthsBack, top_n: topN })
        });

        backtestData = await response.json();
        renderResults();
        loadEvents();
    } catch (error) {
        alert('שגיאה בהרצת הניתוח: ' + error.message);
    } finally {
        btn.disabled = false;
        loading.classList.add('hidden');
    }
}

function renderResults() {
    if (!backtestData) return;

    const { statistics, monthly_results } = backtestData;

    // Show sections
    ['stats-section', 'prob-section', 'charts-section', 'events-section', 'monthly-section', 'honest-section'].forEach(id => {
        document.getElementById(id).classList.remove('hidden');
    });

    renderStatistics(statistics);
    renderProbabilityAccuracy(statistics);
    renderCharts(statistics, monthly_results);
    renderMonthlyDetails(monthly_results);
}

function renderStatistics(stats) {
    document.getElementById('stat-total-recs').textContent = stats.total_analyses;
    document.getElementById('stat-avg-return').textContent = formatPercent(stats.avg_return_per_recommendation);
    document.getElementById('stat-hit-rate').textContent = `${stats.hit_rate}%`;
    document.getElementById('stat-cumulative').textContent = formatPercent(stats.cumulative_return);
    document.getElementById('stat-best').textContent = formatPercent(stats.best_pick);
    document.getElementById('stat-worst').textContent = formatPercent(stats.worst_pick);
    document.getElementById('stat-positive-months').textContent = `${stats.positive_months}/${stats.months_analyzed}`;
    document.getElementById('stat-std').textContent = `${stats.std_deviation}%`;

    const avgEl = document.getElementById('stat-avg-return');
    avgEl.style.color = stats.avg_return_per_recommendation >= 0
        ? 'var(--accent-green)' : 'var(--accent-red)';

    const cumEl = document.getElementById('stat-cumulative');
    cumEl.style.color = stats.cumulative_return >= 0
        ? 'var(--accent-green)' : 'var(--accent-red)';
}

function renderProbabilityAccuracy(stats) {
    const grid = document.getElementById('prob-grid');
    const probAcc = stats.probability_accuracy || {};

    const bucketLabels = {
        high: { name: 'הסתברות גבוהה (65%+)', desc: 'מניות שהמודל העריך סיכוי עלייה גבוה' },
        medium: { name: 'הסתברות בינונית (50-65%)', desc: 'מניות עם סיכוי עלייה מתון' },
        low: { name: 'הסתברות נמוכה (<50%)', desc: 'מניות שהמודל העריך סיכוי עלייה נמוך' },
    };

    let html = '';
    for (const [bucket, info] of Object.entries(bucketLabels)) {
        const data = probAcc[bucket];
        if (data) {
            const accuracy = data.predicted_direction_correct;
            const colorClass = accuracy >= 60 ? 'positive' : accuracy >= 50 ? '' : 'negative';
            html += `
                <div class="stat-card ${colorClass}">
                    <div class="stat-value">${accuracy}%</div>
                    <div class="stat-label">${info.name}</div>
                    <div class="stat-sublabel">${data.sample_size} מניות נבדקו</div>
                </div>
            `;
        }
    }

    if (!html) {
        html = '<p class="no-data">אין מספיק נתונים לחישוב דיוק הסתברויות</p>';
    }

    grid.innerHTML = html;
}

function renderCharts(stats, monthlyResults) {
    Object.values(charts).forEach(c => c.destroy());
    charts = {};

    Chart.defaults.color = '#9ca3af';
    Chart.defaults.borderColor = '#1f2937';

    renderCumulativeChart(stats);
    renderMonthlyChart(monthlyResults);
    renderSectorChart(stats);
    renderSectorHitChart(stats);
}

function renderCumulativeChart(stats) {
    const ctx = document.getElementById('cumulative-chart').getContext('2d');
    const progression = stats.monthly_progression;

    charts.cumulative = new Chart(ctx, {
        type: 'line',
        data: {
            labels: progression.map(p => formatMonth(p.month)),
            datasets: [{
                label: 'תשואה מצטברת (%)',
                data: progression.map(p => p.cumulative_return),
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                fill: true,
                tension: 0.3,
                pointBackgroundColor: progression.map(p =>
                    p.cumulative_return >= 0 ? '#10b981' : '#ef4444'
                ),
                pointRadius: 5,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `תשואה מצטברת: ${formatPercent(ctx.parsed.y)}`
                    }
                }
            },
            scales: {
                y: {
                    ticks: { callback: v => v + '%' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                x: { grid: { display: false } }
            }
        }
    });
}

function renderMonthlyChart(monthlyResults) {
    const ctx = document.getElementById('monthly-chart').getContext('2d');

    charts.monthly = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: monthlyResults.map(m => formatMonth(m.month)),
            datasets: [{
                label: 'תשואה ממוצעת (%)',
                data: monthlyResults.map(m => m.avg_return),
                backgroundColor: monthlyResults.map(m =>
                    m.avg_return >= 0 ? 'rgba(16, 185, 129, 0.7)' : 'rgba(239, 68, 68, 0.7)'
                ),
                borderColor: monthlyResults.map(m =>
                    m.avg_return >= 0 ? '#10b981' : '#ef4444'
                ),
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `תשואה: ${formatPercent(ctx.parsed.y)}`
                    }
                }
            },
            scales: {
                y: {
                    ticks: { callback: v => v + '%' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                x: { grid: { display: false } }
            }
        }
    });
}

function renderSectorChart(stats) {
    const ctx = document.getElementById('sector-chart').getContext('2d');
    const sectors = stats.sector_performance;
    const sectorNames = Object.keys(sectors);

    const colors = [
        '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
        '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'
    ];

    charts.sector = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: sectorNames,
            datasets: [{
                label: 'תשואה ממוצעת (%)',
                data: sectorNames.map(s => sectors[s].avg_return),
                backgroundColor: sectorNames.map((_, i) => colors[i % colors.length] + 'b3'),
                borderColor: sectorNames.map((_, i) => colors[i % colors.length]),
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            indexAxis: 'y',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `תשואה: ${formatPercent(ctx.parsed.x)} (${sectors[sectorNames[ctx.dataIndex]].count} ניתוחים)`
                    }
                }
            },
            scales: {
                x: {
                    ticks: { callback: v => v + '%' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y: { grid: { display: false } }
            }
        }
    });
}

function renderSectorHitChart(stats) {
    const ctx = document.getElementById('sector-hit-chart').getContext('2d');
    const sectors = stats.sector_performance;
    const sectorNames = Object.keys(sectors);

    const colors = [
        '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
        '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'
    ];

    charts.sectorHit = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: sectorNames.map(s => `${s} (${sectors[s].hit_rate}% דיוק)`),
            datasets: [{
                data: sectorNames.map(s => sectors[s].count),
                backgroundColor: sectorNames.map((_, i) => colors[i % colors.length] + 'b3'),
                borderColor: '#0a0e17',
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { padding: 15 }
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const name = sectorNames[ctx.dataIndex];
                            return `${name}: ${sectors[name].hit_rate}% דיוק, ${sectors[name].count} ניתוחים`;
                        }
                    }
                }
            }
        }
    });
}

async function loadEvents() {
    try {
        const response = await fetch('/api/events');
        const data = await response.json();
        renderTimeline(data.events);
    } catch (error) {
        console.error('Error loading events:', error);
    }
}

function renderTimeline(events) {
    const container = document.getElementById('events-timeline');
    container.innerHTML = events.map(event => `
        <div class="event-item ${event.impact}">
            <div class="event-card">
                <div class="event-date">${event.date}</div>
                <div class="event-title">
                    <span class="severity-badge severity-${event.severity}">${event.severity}</span>
                    ${event.title}
                </div>
                <div class="event-description">${event.description}</div>
                <div class="event-sectors">
                    ${event.sectors_affected.map(s => `<span class="sector-tag">${s}</span>`).join('')}
                </div>
            </div>
        </div>
    `).join('');
}

function renderMonthlyDetails(monthlyResults) {
    const container = document.getElementById('monthly-details');

    container.innerHTML = monthlyResults.map((month, idx) => {
        const returnClass = getReturnClass(month.avg_return);
        const expanded = idx === 0 ? '' : 'hidden';

        return `
        <div class="month-block">
            <div class="month-header" onclick="toggleMonth(this)">
                <h3>${formatMonth(month.month)}</h3>
                <div class="month-summary">
                    <div class="month-stat">
                        <div class="value ${returnClass}">${formatPercent(month.avg_return)}</div>
                        <div class="label">תשואה בפועל</div>
                    </div>
                    <div class="month-stat">
                        <div class="value">${month.positive_rate}%</div>
                        <div class="label">דיוק כיוון</div>
                    </div>
                    <div class="month-stat">
                        <div class="value">${month.total_picks}</div>
                        <div class="label">מניות</div>
                    </div>
                </div>
            </div>
            <div class="month-details ${expanded}">
                <table class="rec-table">
                    <thead>
                        <tr>
                            <th>מניה</th>
                            <th>סקטור</th>
                            <th>ציון</th>
                            <th>הסתברות עלייה</th>
                            <th>ביטחון</th>
                            <th>מחיר בניתוח</th>
                            <th>מחיר אחרי חודש</th>
                            <th>תשואה בפועל</th>
                            <th>RSI</th>
                            <th>תנודתיות</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${month.analysis.map(rec => `
                            <tr>
                                <td class="ticker-cell">${rec.ticker}</td>
                                <td>${rec.sector}</td>
                                <td>${rec.score}</td>
                                <td class="${getProbClass(rec.up_probability)}">${formatProbability(rec.up_probability)}</td>
                                <td>${rec.signals_aligned}/${rec.total_signals}</td>
                                <td>$${rec.price_at_analysis}</td>
                                <td>${rec.end_price ? '$' + rec.end_price : '-'}</td>
                                <td class="${getReturnClass(rec.return_pct)}">${formatPercent(rec.return_pct)}</td>
                                <td>${rec.rsi}</td>
                                <td>${rec.volatility}%</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
        `;
    }).join('');
}

function toggleMonth(header) {
    const details = header.nextElementSibling;
    details.classList.toggle('hidden');
}
