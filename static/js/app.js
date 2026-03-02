/**
 * INvest - Stock Analysis Dashboard Frontend
 * Probability-based analysis + calibrated forward prediction.
 * NOT investment recommendations.
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
    const sector = document.getElementById('sector-filter').value;
    const tickers = document.getElementById('ticker-filter').value.trim();
    const btn = document.getElementById('run-backtest');
    const loading = document.getElementById('loading');

    btn.disabled = true;
    loading.classList.remove('hidden');

    try {
        const body = { months_back: monthsBack, top_n: topN };
        if (sector) body.sector = sector;
        if (tickers) body.tickers = tickers;

        const response = await fetch('/api/run-backtest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        backtestData = await response.json();
        console.log('Backtest response:', backtestData);
        renderResults();
        loadEvents();
    } catch (error) {
        console.error('Backtest error:', error);
        alert('שגיאה בהרצת הניתוח: ' + error.message);
    } finally {
        btn.disabled = false;
        loading.classList.add('hidden');
    }
}

function renderResults() {
    if (!backtestData) return;

    const { statistics, monthly_results, calibration, forward_prediction } = backtestData;

    // Show sections
    ['forward-section', 'calibration-section', 'stats-section', 'prob-section',
     'charts-section', 'events-section', 'monthly-section', 'honest-section'].forEach(id => {
        document.getElementById(id).classList.remove('hidden');
    });

    // Check for backend errors
    if (statistics && statistics.error) {
        alert('שגיאה מהשרת: ' + statistics.error);
        return;
    }

    try { renderStatistics(statistics); } catch(e) { console.error('renderStatistics:', e); }
    try { renderProbabilityAccuracy(statistics); } catch(e) { console.error('renderProbabilityAccuracy:', e); }
    try { renderCharts(statistics, monthly_results); } catch(e) { console.error('renderCharts:', e); }
    try { renderMonthlyDetails(monthly_results); } catch(e) { console.error('renderMonthlyDetails:', e); }
    try { renderForwardPrediction(forward_prediction, calibration); } catch(e) { console.error('renderForwardPrediction:', e); }
    try { renderCalibration(calibration); } catch(e) { console.error('renderCalibration:', e); }
}

/* ========== Forward Prediction ========== */

function renderForwardPrediction(forward, calibration) {
    if (!forward || !forward.bottom_line) {
        console.warn('No forward prediction data');
        return;
    }
    const bl = forward.bottom_line;
    if (bl.error) {
        document.getElementById('bottom-line').innerHTML = `<p class="no-data">${bl.error}</p>`;
        return;
    }
    const container = document.getElementById('bottom-line');
    const picksContainer = document.getElementById('forward-picks');

    // Bottom line card
    const calProb = bl.avg_calibrated_probability || 0;
    const expReturn = bl.expected_monthly_return || 0;
    const modelConf = bl.model_confidence || 0;
    const probColor = calProb >= 0.55 ? 'positive-val' : calProb <= 0.45 ? 'negative-val' : '';
    const returnColor = expReturn >= 0 ? 'positive-val' : 'negative-val';

    container.innerHTML = `
        <div class="bottom-line-grid">
            <div class="bl-main">
                <div class="bl-title">שורה תחתונה - חיזוי לחודש הבא</div>
                <div class="bl-recommendation">${bl.recommendation || '-'}</div>
                <div class="bl-date">תאריך ניתוח: ${forward.analysis_date || '-'}</div>
            </div>
            <div class="bl-stats">
                <div class="bl-stat">
                    <div class="bl-value ${probColor}">${formatProbability(calProb)}</div>
                    <div class="bl-label">הסתברות עלייה (מכוילת)</div>
                </div>
                <div class="bl-stat">
                    <div class="bl-value ${returnColor}">${formatPercent(expReturn)}</div>
                    <div class="bl-label">תשואה חודשית צפויה</div>
                </div>
                <div class="bl-stat">
                    <div class="bl-value">${(modelConf * 100).toFixed(1)}%</div>
                    <div class="bl-label">R² - מדד דיוק המודל</div>
                </div>
                <div class="bl-stat">
                    <div class="bl-value">${formatProbability(bl.avg_raw_probability)}</div>
                    <div class="bl-label">הסתברות גולמית (לפני כיול)</div>
                </div>
            </div>
        </div>
    `;

    // Top picks table
    const picks = forward.top_picks;
    if (picks && picks.length > 0) {
        picksContainer.innerHTML = `
            <h3>מניות מובילות - חיזוי קדימה</h3>
            <table class="rec-table forward-table">
                <thead>
                    <tr>
                        <th>מניה</th>
                        <th>סקטור</th>
                        <th>ציון</th>
                        <th>הסתברות גולמית</th>
                        <th>הסתברות מכוילת</th>
                        <th>ביטחון</th>
                        <th>מחיר נוכחי</th>
                        <th>RSI</th>
                        <th>תנודתיות</th>
                        <th>מומנטום 1 חודש</th>
                    </tr>
                </thead>
                <tbody>
                    ${picks.map(p => `
                        <tr>
                            <td class="ticker-cell">${p.ticker}</td>
                            <td>${p.sector}</td>
                            <td>${p.score}</td>
                            <td class="${getProbClass(p.up_probability)}">${formatProbability(p.up_probability)}</td>
                            <td class="${getProbClass(p.calibrated_probability)}"><strong>${formatProbability(p.calibrated_probability)}</strong></td>
                            <td>${p.signals_aligned}/${p.total_signals}</td>
                            <td>$${p.price_at_analysis}</td>
                            <td>${p.rsi}</td>
                            <td>${p.volatility}%</td>
                            <td class="${getReturnClass(p.momentum_1m)}">${formatPercent(p.momentum_1m)}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    }
}

/* ========== Calibration ========== */

function renderCalibration(cal) {
    const grid = document.getElementById('calibration-grid');

    if (cal.error) {
        grid.innerHTML = `<p class="no-data">${cal.error}</p>`;
        return;
    }

    const biasClass = cal.model_bias >= 0 ? 'positive-val' : 'negative-val';
    const biasText = cal.model_bias >= 0 ? 'אופטימי' : 'פסימי';

    let html = `
        <div class="stat-card highlight">
            <div class="stat-value">${(cal.r_squared * 100).toFixed(1)}%</div>
            <div class="stat-label">R² - מדד התאמת הרגרסיה</div>
            <div class="stat-sublabel">כמה טוב המודל מכויל</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${(cal.actual_success_rate * 100).toFixed(1)}%</div>
            <div class="stat-label">שיעור הצלחה בפועל</div>
            <div class="stat-sublabel">מתוך ${cal.total_pairs} ניתוחים</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${(cal.avg_predicted_prob * 100).toFixed(1)}%</div>
            <div class="stat-label">הסתברות ממוצעת שחושבה</div>
        </div>
        <div class="stat-card ${cal.model_bias >= 0 ? 'positive' : 'negative'}">
            <div class="stat-value ${biasClass}">${(cal.model_bias * 100).toFixed(1)}%</div>
            <div class="stat-label">הטיית המודל</div>
            <div class="stat-sublabel">המודל ${Math.abs(cal.model_bias) < 0.02 ? 'מכויל היטב' : biasText + ' מדי'}</div>
        </div>
    `;

    // Bucket details
    if (cal.buckets) {
        for (const [name, b] of Object.entries(cal.buckets)) {
            const bucketNames = { high: 'גבוהה', medium: 'בינונית', low: 'נמוכה' };
            const ratio = b.calibration_ratio;
            const ratioClass = ratio >= 0.9 && ratio <= 1.1 ? 'positive-val' : 'negative-val';
            html += `
                <div class="stat-card">
                    <div class="stat-value ${ratioClass}">${ratio.toFixed(2)}x</div>
                    <div class="stat-label">יחס כיול - הסתברות ${bucketNames[name]}</div>
                    <div class="stat-sublabel">חזה ${(b.avg_predicted_prob * 100).toFixed(0)}%, בפועל ${(b.actual_success_rate * 100).toFixed(0)}% (${b.count} מניות)</div>
                </div>
            `;
        }
    }

    grid.innerHTML = html;
}

/* ========== Statistics ========== */

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

/* ========== Charts ========== */

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

/* ========== Events ========== */

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

/* ========== Monthly Details ========== */

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
