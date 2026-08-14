const state = {
  lang: localStorage.getItem('kbeauty_lang') || 'ko',
  topTrends: [],
  charts: {},
};

const I18N = {
  ko: {
    eyebrow: 'K-BEAUTY DATA INTELLIGENCE', title: 'K-Beauty Trend Intelligence', keywords: '키워드', avgScore: '평균 점수', rising: '급상승', signals: '원본 신호', topTrends: '오늘의 TOP 트렌드', clickHint: '키워드를 클릭하면 상세 분석을 볼 수 있습니다.', refresh: '새로고침', topHistory: 'TOP 키워드 추이', back: '뒤로', keywordDetail: 'KEYWORD DETAIL', trendScore: '트렌드 점수', scoreHistory: 'Trend Score History', platformTrend: '플랫폼별 추이', platformHint: '최근 30일 언급량', regions: '지역별 신호', signalsDetail: '원본 신호', readOnly: 'Read-only analytics dashboard · SQLite source', noData: '데이터가 없습니다.', noSignals: '일치하는 원본 신호가 없습니다.', risingStatus: '급상승', stableStatus: '안정', emergingStatus: '신흥', decliningStatus: '하락', volume: 'Volume', velocity: 'Velocity', persistence: 'Persistence', crossPlatform: 'Cross Platform', regional: 'Regional', platformNormalized: 'Platform Normalized', mentions: '언급량', loading: '불러오는 중…', error: '데이터를 불러오지 못했습니다.'
  },
  en: {
    eyebrow: 'K-BEAUTY DATA INTELLIGENCE', title: 'K-Beauty Trend Intelligence', keywords: 'Keywords', avgScore: 'Avg. Score', rising: 'Rising', signals: 'Raw Signals', topTrends: "Today's Top Trends", clickHint: 'Click a keyword for detailed analysis.', refresh: 'Refresh', topHistory: 'Top Keyword History', back: 'Back', keywordDetail: 'KEYWORD DETAIL', trendScore: 'Trend Score', scoreHistory: 'Trend Score History', platformTrend: 'Platform Trend', platformHint: 'Mentions over the last 30 days', regions: 'Regional Signals', signalsDetail: 'Raw Signals', readOnly: 'Read-only analytics dashboard · SQLite source', noData: 'No data.', noSignals: 'No matching raw signals.', risingStatus: 'RISING', stableStatus: 'ESTABLISHED', emergingStatus: 'EMERGING', decliningStatus: 'DECLINING', volume: 'Volume', velocity: 'Velocity', persistence: 'Persistence', crossPlatform: 'Cross Platform', regional: 'Regional', platformNormalized: 'Platform Normalized', mentions: 'Mentions', loading: 'Loading…', error: 'Could not load data.'
  },
  ar: {
    eyebrow: 'ذكاء بيانات K-BEAUTY', title: 'ذكاء اتجاهات K-Beauty', keywords: 'الكلمات المفتاحية', avgScore: 'متوسط الدرجة', rising: 'صاعد', signals: 'الإشارات الأصلية', topTrends: 'أهم اتجاهات اليوم', clickHint: 'اضغط على كلمة مفتاحية لعرض التحليل التفصيلي.', refresh: 'تحديث', topHistory: 'تاريخ الكلمات الرائجة', back: 'رجوع', keywordDetail: 'تفاصيل الكلمة المفتاحية', trendScore: 'درجة الاتجاه', scoreHistory: 'تاريخ درجة الاتجاه', platformTrend: 'الاتجاه حسب المنصة', platformHint: 'الإشارات خلال آخر 30 يوماً', regions: 'الإشارات حسب المنطقة', signalsDetail: 'الإشارات الأصلية', readOnly: 'لوحة تحليل للقراءة فقط · مصدر SQLite', noData: 'لا توجد بيانات.', noSignals: 'لا توجد إشارات أصلية مطابقة.', risingStatus: 'صاعد', stableStatus: 'مستقر', emergingStatus: 'ناشئ', decliningStatus: 'هابط', volume: 'الحجم', velocity: 'السرعة', persistence: 'الاستمرارية', crossPlatform: 'عبر المنصات', regional: 'إقليمي', platformNormalized: 'تطبيع المنصة', mentions: 'الإشارات', loading: 'جارٍ التحميل…', error: 'تعذر تحميل البيانات.'
  }
};

const t = key => I18N[state.lang][key] || I18N.en[key] || key;
const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const api = path => `/api${path}`;

function applyLanguage() {
  document.documentElement.lang = state.lang;
  document.documentElement.dir = state.lang === 'ar' ? 'rtl' : 'ltr';
  document.querySelectorAll('[data-i18n]').forEach(el => el.textContent = t(el.dataset.i18n));
  document.getElementById('language').value = state.lang;
}

async function getJSON(path) {
  const res = await fetch(api(path));
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

function destroyChart(name) {
  if (state.charts[name]) { state.charts[name].destroy(); delete state.charts[name]; }
}

function baseChartOptions() {
  return { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true } } };
}

async function loadDashboard() {
  try {
    const [summary, today] = await Promise.all([
      getJSON('/dashboard/summary'),
      getJSON('/dashboard/today?limit=10')
    ]);
    document.getElementById('dateLabel').textContent = summary.date || '—';
    document.getElementById('kpiKeywords').textContent = summary.keyword_count ?? '—';
    document.getElementById('kpiAvg').textContent = summary.avg_score ?? '—';
    document.getElementById('kpiRising').textContent = summary.rising_count ?? '—';
    document.getElementById('kpiSignals').textContent = Number(summary.raw_signal_count || 0).toLocaleString();
    state.topTrends = today.trends || [];
    renderTrendList();
    await renderTopHistory();
  } catch (e) {
    document.getElementById('trendList').innerHTML = `<div class="muted">${esc(t('error'))}</div>`;
  }
}

function renderTrendList() {
  const list = document.getElementById('trendList');
  if (!state.topTrends.length) { list.innerHTML = `<div class="muted">${esc(t('noData'))}</div>`; return; }
  list.innerHTML = state.topTrends.map((x, i) => {
    const score = Number(x.trend_score || 0);
    const status = Number(x.velocity_score || 0) >= 70 ? t('risingStatus') : t('stableStatus');
    return `<div class="trend-row" data-keyword="${esc(x.keyword)}">
      <div class="trend-name">${i + 1}. ${esc(x.keyword)}</div>
      <div class="bar-bg"><div class="bar" style="--width:${Math.min(100, Math.max(0, score))}%"></div></div>
      <div class="trend-score">${score.toFixed(1)}</div>
      <div class="status-badge">${esc(status)}</div>
    </div>`;
  }).join('');
  list.querySelectorAll('.trend-row').forEach(row => row.addEventListener('click', () => openDetail(row.dataset.keyword)));
}

async function renderTopHistory() {
  destroyChart('top');
  const top = state.topTrends.slice(0, 5);
  const datasets = [];
  for (const x of top) {
    try {
      const data = await getJSON(`/trends/${encodeURIComponent(x.keyword)}/history`);
      datasets.push({ label: x.keyword, data: data.history.map(r => ({x: r.signal_date, y: Number(r.trend_score || 0)})), tension: .3, pointRadius: 2 });
    } catch (_) {}
  }
  state.charts.top = new Chart(document.getElementById('topChart'), { type: 'line', data: { datasets }, options: baseChartOptions() });
}

async function openDetail(keyword) {
  document.getElementById('dashboardView').classList.add('hidden');
  document.getElementById('detailView').classList.remove('hidden');
  window.scrollTo({top: 0, behavior: 'smooth'});
  document.getElementById('detailKeyword').textContent = keyword;
  try {
    const [detail, platforms, regions, signals] = await Promise.all([
      getJSON(`/keywords/${encodeURIComponent(keyword)}`),
      getJSON(`/keywords/${encodeURIComponent(keyword)}/platforms?days=30`),
      getJSON(`/keywords/${encodeURIComponent(keyword)}/regions?days=30`),
      getJSON(`/keywords/${encodeURIComponent(keyword)}/signals?limit=40`)
    ]);
    renderDetail(detail);
    renderPlatformChart(platforms);
    renderRegions(regions);
    renderSignals(signals);
  } catch (e) {
    document.getElementById('signalList').innerHTML = `<div class="muted">${esc(t('error'))}</div>`;
  }
}

function renderDetail(data) {
  const latest = data.latest;
  document.getElementById('detailScore').textContent = Number(latest.trend_score || 0).toFixed(1);
  document.getElementById('detailStatus').textContent = Number(latest.velocity_score || 0) >= 70 ? t('risingStatus') : t('stableStatus');
  const metrics = [
    ['volume_score','volume'], ['velocity_score','velocity'], ['persistence_score','persistence'],
    ['cross_platform_score','crossPlatform'], ['regional_score','regional'], ['platform_normalized_score','platformNormalized']
  ];
  document.getElementById('breakdownGrid').innerHTML = metrics.map(([field,label]) => {
    const value = Number(latest[field] || 0);
    return `<div class="metric"><div class="metric-head"><span>${esc(t(label))}</span><strong>${value.toFixed(1)}</strong></div><div class="bar-bg"><div class="bar" style="--width:${Math.min(100, Math.max(0, value))}%"></div></div></div>`;
  }).join('');
  destroyChart('score');
  state.charts.score = new Chart(document.getElementById('scoreChart'), {
    type: 'line', data: { labels: data.history.map(x => x.signal_date), datasets: [
      { label: t('trendScore'), data: data.history.map(x => Number(x.trend_score || 0)), tension: .3, pointRadius: 3 }
    ]}, options: baseChartOptions()
  });
}

function renderPlatformChart(data) {
  destroyChart('platform');
  const rows = data.data || [];
  const dates = [...new Set(rows.map(r => r.signal_date))];
  const platforms = [...new Set(rows.map(r => r.platform))];
  const datasets = platforms.map(platform => ({ label: platform, data: dates.map(date => Number(rows.find(r => r.signal_date === date && r.platform === platform)?.mentions || 0)), tension: .25 }));
  state.charts.platform = new Chart(document.getElementById('platformChart'), { type: 'line', data: { labels: dates, datasets }, options: baseChartOptions() });
}

function renderRegions(data) {
  const rows = data.data || [];
  const max = Math.max(1, ...rows.map(r => Number(r.mentions || 0)));
  document.getElementById('regionList').innerHTML = rows.length ? rows.slice(0, 12).map(r => {
    const v = Number(r.mentions || 0);
    return `<div class="region-row"><div class="region-name">${esc(r.region)}</div><div class="bar-bg"><div class="bar" style="--width:${v/max*100}%"></div></div><div class="region-value">${v}</div></div>`;
  }).join('') : `<div class="muted">${esc(t('noData'))}</div>`;
}

function renderSignals(data) {
  const rows = data.signals || [];
  document.getElementById('signalList').innerHTML = rows.length ? rows.map(s => `<article class="signal">
    <div class="signal-meta"><strong>${esc(s.platform)}</strong><span>${esc(s.region)}</span><span>${esc(s.signal_date)}</span><span>${esc(s.query || s.tag || '')}</span></div>
    <div class="signal-text">${esc(s.text)}</div>
  </article>`).join('') : `<div class="muted">${esc(t('noSignals'))}</div>`;
}

document.getElementById('language').addEventListener('change', e => {
  state.lang = e.target.value;
  localStorage.setItem('kbeauty_lang', state.lang);
  applyLanguage();
  loadDashboard();
});
document.getElementById('refreshBtn').addEventListener('click', loadDashboard);
document.getElementById('backBtn').addEventListener('click', () => {
  document.getElementById('detailView').classList.add('hidden');
  document.getElementById('dashboardView').classList.remove('hidden');
  window.scrollTo({top: 0, behavior: 'smooth'});
});

applyLanguage();
loadDashboard();
