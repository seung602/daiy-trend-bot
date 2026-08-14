const state = {
  lang: localStorage.getItem('kbeauty_lang') || 'ko',
  topStatus: 'ALL',
  topDays: 30,
  detailDays: 30,
  topTrends: [],
  currentKeyword: null,
  currentPlatformData: null,
  selectedPlatforms: new Set(),
  selectedSignalPlatform: '',
  charts: {}
};

const I18N = {
  ko: {
    eyebrow:'K-BEAUTY DATA INTELLIGENCE', title:'K-Beauty Trend Intelligence', keywords:'키워드', avgScore:'평균 점수', rising:'급상승', signals:'원본 신호', topTrends:'오늘의 TOP 트렌드', clickHint:'키워드를 클릭하면 상세 분석을 볼 수 있습니다.', refresh:'새로고침', topHistory:'TOP 키워드 추이', historyHint:'선택한 기간의 점수 흐름입니다.', back:'뒤로', keywordDetail:'KEYWORD DETAIL', trendScore:'트렌드 점수', scoreHistory:'Trend Score History', platformTrend:'플랫폼별 추이', regions:'지역별 신호', signalsDetail:'원본 신호', readOnly:'Read-only analytics dashboard · SQLite source', noData:'데이터가 없습니다.', noSignals:'일치하는 원본 신호가 없습니다.', all:'전체', risingStatus:'급상승', stableStatus:'안정', emergingStatus:'신흥', decliningStatus:'하락', volume:'Volume', velocity:'Velocity', persistence:'Persistence', crossPlatform:'Cross Platform', regional:'Regional', platformNormalized:'Platform Normalized', loading:'불러오는 중…', error:'데이터를 불러오지 못했습니다.', analysisPeriod:'분석 기간', whyTrending:'왜 이 키워드가 뜨고 있나?', whyHint:'현재 DB의 점수와 신호를 바탕으로 자동 요약합니다.', signalHint:'실제 수집된 원본을 확인합니다.', scoreUp:'점수 상승', scoreDown:'점수 하락', scoreFlat:'점수 변화 거의 없음', topPlatform:'가장 강한 플랫폼', topRegion:'가장 강한 지역', platformCount:'감지 플랫폼 수', strongestMetric:'가장 강한 지표', noHistory:'비교할 이전 날짜가 없어 변화율을 계산할 수 없습니다.', insightRising:'Velocity가 높아 최근 관심 증가가 강하게 나타납니다.', insightCross:'여러 플랫폼에서 동시에 신호가 확인되어 교차 플랫폼 확산이 강합니다.', insightPersistence:'지속성 점수가 높아 단기 유행보다 지속되는 흐름에 가깝습니다.', insightVolume:'현재 언급량이 주요 기여 요인입니다.', recent:'최근', mentions:'언급량', allPlatforms:'전체 플랫폼'
  },
  en: {
    eyebrow:'K-BEAUTY DATA INTELLIGENCE', title:'K-Beauty Trend Intelligence', keywords:'Keywords', avgScore:'Avg. Score', rising:'Rising', signals:'Raw Signals', topTrends:"Today's Top Trends", clickHint:'Click a keyword for detailed analysis.', refresh:'Refresh', topHistory:'Top Keyword History', historyHint:'Score movement over the selected period.', back:'Back', keywordDetail:'KEYWORD DETAIL', trendScore:'Trend Score', scoreHistory:'Trend Score History', platformTrend:'Platform Trend', regions:'Regional Signals', signalsDetail:'Raw Signals', readOnly:'Read-only analytics dashboard · SQLite source', noData:'No data.', noSignals:'No matching raw signals.', all:'ALL', risingStatus:'RISING', stableStatus:'ESTABLISHED', emergingStatus:'EMERGING', decliningStatus:'DECLINING', volume:'Volume', velocity:'Velocity', persistence:'Persistence', crossPlatform:'Cross Platform', regional:'Regional', platformNormalized:'Platform Normalized', loading:'Loading…', error:'Could not load data.', analysisPeriod:'Analysis period', whyTrending:'Why is this keyword trending?', whyHint:'Automatic summary based on the current DB scores and signals.', signalHint:'Review the actual collected source signals.', scoreUp:'Score increased', scoreDown:'Score decreased', scoreFlat:'Little score movement', topPlatform:'Top platform', topRegion:'Top region', platformCount:'Platforms detected', strongestMetric:'Strongest metric', noHistory:'There is not enough history to calculate a change.', insightRising:'High velocity indicates a strong recent increase in attention.', insightCross:'Signals are appearing across multiple platforms, indicating cross-platform spread.', insightPersistence:'A high persistence score suggests a sustained trend rather than a short spike.', insightVolume:'Current mention volume is the main contributing factor.', recent:'Recent', mentions:'Mentions', allPlatforms:'All platforms'
  },
  ar: {
    eyebrow:'ذكاء بيانات K-BEAUTY', title:'ذكاء اتجاهات K-Beauty', keywords:'الكلمات المفتاحية', avgScore:'متوسط الدرجة', rising:'صاعد', signals:'الإشارات الأصلية', topTrends:'أهم اتجاهات اليوم', clickHint:'اضغط على كلمة مفتاحية لعرض التحليل التفصيلي.', refresh:'تحديث', topHistory:'تاريخ الكلمات الرائجة', historyHint:'حركة الدرجة خلال الفترة المحددة.', back:'رجوع', keywordDetail:'تفاصيل الكلمة المفتاحية', trendScore:'درجة الاتجاه', scoreHistory:'تاريخ درجة الاتجاه', platformTrend:'الاتجاه حسب المنصة', regions:'الإشارات حسب المنطقة', signalsDetail:'الإشارات الأصلية', readOnly:'لوحة تحليل للقراءة فقط · مصدر SQLite', noData:'لا توجد بيانات.', noSignals:'لا توجد إشارات أصلية مطابقة.', all:'الكل', risingStatus:'صاعد', stableStatus:'مستقر', emergingStatus:'ناشئ', decliningStatus:'هابط', volume:'الحجم', velocity:'السرعة', persistence:'الاستمرارية', crossPlatform:'عبر المنصات', regional:'إقليمي', platformNormalized:'تطبيع المنصة', loading:'جارٍ التحميل…', error:'تعذر تحميل البيانات.', analysisPeriod:'فترة التحليل', whyTrending:'لماذا يتجه هذا المصطلح إلى الصعود؟', whyHint:'ملخص تلقائي مبني على درجات وإشارات قاعدة البيانات الحالية.', signalHint:'راجع الإشارات المصدرية التي تم جمعها فعلياً.', scoreUp:'ارتفعت الدرجة', scoreDown:'انخفضت الدرجة', scoreFlat:'تغير طفيف في الدرجة', topPlatform:'أقوى منصة', topRegion:'أقوى منطقة', platformCount:'عدد المنصات', strongestMetric:'أقوى مؤشر', noHistory:'لا توجد بيانات تاريخية كافية لحساب التغير.', insightRising:'تشير السرعة المرتفعة إلى زيادة قوية في الاهتمام مؤخراً.', insightCross:'تظهر الإشارات عبر عدة منصات، مما يدل على انتشار متعدد المنصات.', insightPersistence:'تشير الاستمرارية المرتفعة إلى اتجاه مستمر وليس ارتفاعاً قصيراً.', insightVolume:'حجم الإشارات الحالي هو العامل الرئيسي المساهم.', recent:'الأحدث', mentions:'الإشارات', allPlatforms:'كل المنصات'
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
  if (state.currentKeyword) {
    document.getElementById('platformHint').textContent = state.lang === 'ko' ? `최근 ${state.detailDays}일 언급량` : state.lang === 'en' ? `Mentions over the last ${state.detailDays} days` : `الإشارات خلال آخر ${state.detailDays} يوماً`;
  }
}

async function getJSON(path) {
  const res = await fetch(api(path));
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

function destroyChart(name) { if (state.charts[name]) { state.charts[name].destroy(); delete state.charts[name]; } }
function baseChartOptions() { return { responsive:true, maintainAspectRatio:false, interaction:{mode:'index',intersect:false}, plugins:{legend:{position:'bottom'}}, scales:{y:{beginAtZero:true}} }; }

async function loadDashboard() {
  try {
    const [summary, today] = await Promise.all([getJSON('/dashboard/summary'), getJSON(`/dashboard/trends?limit=10&status=${state.topStatus}`)]);
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

function statusLabel(status) {
  return ({RISING:t('risingStatus'),EMERGING:t('emergingStatus'),ESTABLISHED:t('stableStatus'),DECLINING:t('decliningStatus')})[status] || status;
}
function renderTrendList() {
  const list = document.getElementById('trendList');
  if (!state.topTrends.length) { list.innerHTML = `<div class="muted">${esc(t('noData'))}</div>`; return; }
  list.innerHTML = state.topTrends.map((x,i) => {
    const score = Number(x.trend_score || 0);
    return `<button class="trend-row" data-keyword="${esc(x.keyword)}" type="button">
      <span class="trend-name">${i+1}. ${esc(x.keyword)}</span><span class="bar-bg"><span class="bar" style="--width:${Math.min(100,Math.max(0,score))}%"></span></span><strong class="trend-score">${score.toFixed(1)}</strong><span class="status-badge">${esc(statusLabel(x.status))}</span>
    </button>`;
  }).join('');
  list.querySelectorAll('.trend-row').forEach(row => row.addEventListener('click', () => openDetail(row.dataset.keyword)));
}

async function renderTopHistory() {
  destroyChart('top');
  const top = state.topTrends.slice(0,5);
  const datasets=[];
  for (const x of top) {
    try {
      const data = await getJSON(`/keywords/${encodeURIComponent(x.keyword)}?days=${state.topDays}`);
      datasets.push({label:x.keyword,data:data.history.map(r=>({x:r.signal_date,y:Number(r.trend_score||0)})),tension:.25,pointRadius:2});
    } catch (_) {}
  }
  state.charts.top = new Chart(document.getElementById('topChart'),{type:'line',data:{datasets},options:baseChartOptions()});
}

async function openDetail(keyword) {
  state.currentKeyword=keyword;
  state.selectedPlatforms=new Set();
  state.selectedSignalPlatform='';
  document.getElementById('dashboardView').classList.add('hidden');
  document.getElementById('detailView').classList.remove('hidden');
  window.scrollTo({top:0,behavior:'smooth'});
  document.getElementById('detailKeyword').textContent=keyword;
  await loadDetail();
}

async function loadDetail() {
  const keyword=state.currentKeyword;
  if(!keyword) return;
  try {
    const [detail,platforms,regions,signals,insight]=await Promise.all([
      getJSON(`/keywords/${encodeURIComponent(keyword)}?days=${state.detailDays}`),
      getJSON(`/keywords/${encodeURIComponent(keyword)}/platforms?days=${state.detailDays}`),
      getJSON(`/keywords/${encodeURIComponent(keyword)}/regions?days=${state.detailDays}`),
      getJSON(`/keywords/${encodeURIComponent(keyword)}/signals?limit=60${state.selectedSignalPlatform?`&platform=${encodeURIComponent(state.selectedSignalPlatform)}`:''}`),
      getJSON(`/keywords/${encodeURIComponent(keyword)}/insight`)
    ]);
    renderDetail(detail); renderInsight(insight); renderPlatformChart(platforms); renderRegions(regions); renderSignals(signals);
  } catch(e) { document.getElementById('signalList').innerHTML=`<div class="muted">${esc(t('error'))}</div>`; }
}

function renderDetail(data) {
  const latest=data.latest;
  document.getElementById('detailScore').textContent=Number(latest.trend_score||0).toFixed(1);
  document.getElementById('detailStatus').textContent=statusLabel(latest.status);
  document.getElementById('detailStatus').className=`status-badge status-${String(latest.status||'').toLowerCase().replaceAll(' ','-')}`;
  const metrics=[['volume_score','volume'],['velocity_score','velocity'],['persistence_score','persistence'],['cross_platform_score','crossPlatform'],['regional_score','regional'],['platform_normalized_score','platformNormalized']];
  document.getElementById('breakdownGrid').innerHTML=metrics.map(([field,label])=>{const v=Number(latest[field]||0);return `<div class="metric"><div class="metric-head"><span>${esc(t(label))}</span><strong>${v.toFixed(1)}</strong></div><div class="bar-bg"><div class="bar" style="--width:${Math.min(100,Math.max(0,v))}%"></div></div></div>`;}).join('');
  destroyChart('score');
  state.charts.score=new Chart(document.getElementById('scoreChart'),{type:'line',data:{labels:data.history.map(x=>x.signal_date),datasets:[{label:t('trendScore'),data:data.history.map(x=>Number(x.trend_score||0)),tension:.25,pointRadius:3}]},options:baseChartOptions()});
}

function renderInsight(x) {
  const delta=x.score_delta;
  const deltaText=delta===null?t('noHistory'):delta>0?`${t('scoreUp')}: +${delta.toFixed(1)}`:delta<0?`${t('scoreDown')}: ${delta.toFixed(1)}`:t('scoreFlat');
  const key=x.insight_key;
  const text=key==='rising_velocity'?t('insightRising'):key==='cross_platform'?t('insightCross'):key==='persistence'?t('insightPersistence'):t('insightVolume');
  const metricMap={volume:t('volume'),velocity:t('velocity'),persistence:t('persistence'),cross_platform:t('crossPlatform'),regional:t('regional'),platform_normalized:t('platformNormalized')};
  document.getElementById('insightBody').innerHTML=`<div class="insight-main"><span class="insight-status">${esc(statusLabel(x.status))}</span><p>${esc(text)}</p></div><div class="insight-facts"><div><span>${esc(t('recent'))}</span><strong>${esc(deltaText)}</strong></div><div><span>${esc(t('topPlatform'))}</span><strong>${esc(x.top_platform?.platform || '—')}</strong></div><div><span>${esc(t('topRegion'))}</span><strong>${esc(x.top_region?.region || '—')}</strong></div><div><span>${esc(t('platformCount'))}</span><strong>${x.platform_count}</strong></div><div><span>${esc(t('strongestMetric'))}</span><strong>${esc(metricMap[x.strongest_metric]||x.strongest_metric)} · ${Number(x.strongest_metric_score).toFixed(1)}</strong></div></div>`;
}

function renderPlatformChart(data) {
  state.currentPlatformData=data.data||[];
  const rows=state.currentPlatformData;
  const dates=[...new Set(rows.map(r=>r.signal_date))];
  const platforms=[...new Set(rows.map(r=>r.platform))];
  if(!state.selectedPlatforms.size) platforms.forEach(p=>state.selectedPlatforms.add(p));
  renderPlatformFilters(platforms);
  const visible=platforms.filter(p=>state.selectedPlatforms.has(p));
  destroyChart('platform');
  const datasets=visible.map(p=>({label:p,data:dates.map(d=>Number(rows.find(r=>r.signal_date===d&&r.platform===p)?.mentions||0)),tension:.25}));
  state.charts.platform=new Chart(document.getElementById('platformChart'),{type:'line',data:{labels:dates,datasets},options:baseChartOptions()});
}
function renderPlatformFilters(platforms){
  document.getElementById('platformFilters').innerHTML=platforms.map(p=>`<label class="check-pill"><input type="checkbox" value="${esc(p)}" ${state.selectedPlatforms.has(p)?'checked':''}><span>${esc(p)}</span></label>`).join('');
  document.querySelectorAll('#platformFilters input').forEach(input=>input.addEventListener('change',()=>{if(input.checked)state.selectedPlatforms.add(input.value);else state.selectedPlatforms.delete(input.value);renderPlatformChart({data:state.currentPlatformData});}));
}

function renderRegions(data){
  const rows=data.data||[]; const max=Math.max(1,...rows.map(r=>Number(r.mentions||0)));
  document.getElementById('regionList').innerHTML=rows.length?rows.slice(0,12).map(r=>{const v=Number(r.mentions||0);return `<div class="region-row"><span class="region-name">${esc(r.region)}</span><span class="bar-bg"><span class="bar" style="--width:${v/max*100}%"></span></span><strong class="region-value">${v}</strong></div>`;}).join(''):`<div class="muted">${esc(t('noData'))}</div>`;
}

function renderSignals(data){
  const rows=data.signals||[]; const platforms=[...new Set(rows.map(s=>s.platform).filter(Boolean))];
  document.getElementById('signalFilters').innerHTML=`<button class="mini-filter ${!state.selectedSignalPlatform?'active':''}" data-platform="">${esc(t('allPlatforms'))}</button>`+platforms.map(p=>`<button class="mini-filter ${state.selectedSignalPlatform===p?'active':''}" data-platform="${esc(p)}">${esc(p)}</button>`).join('');
  document.querySelectorAll('#signalFilters .mini-filter').forEach(b=>b.addEventListener('click',()=>{state.selectedSignalPlatform=b.dataset.platform;loadDetail();}));
  document.getElementById('signalList').innerHTML=rows.length?rows.map(s=>`<article class="signal"><div class="signal-meta"><strong>${esc(s.platform)}</strong><span>${esc(s.region)}</span><span>${esc(s.signal_date)}</span><span>${esc(s.query||s.tag||'')}</span></div><div class="signal-text">${esc(s.text)}</div></article>`).join(''):`<div class="muted">${esc(t('noSignals'))}</div>`;
}

function bindFilters(){
  document.querySelectorAll('#statusFilters button').forEach(b=>b.addEventListener('click',()=>{state.topStatus=b.dataset.status;document.querySelectorAll('#statusFilters button').forEach(x=>x.classList.remove('active'));b.classList.add('active');loadDashboard();}));
  document.querySelectorAll('#topPeriodFilters button').forEach(b=>b.addEventListener('click',()=>{state.topDays=Number(b.dataset.days);document.querySelectorAll('#topPeriodFilters button').forEach(x=>x.classList.remove('active'));b.classList.add('active');renderTopHistory();}));
  document.querySelectorAll('#detailPeriodFilters button').forEach(b=>b.addEventListener('click',()=>{state.detailDays=Number(b.dataset.days);document.querySelectorAll('#detailPeriodFilters button').forEach(x=>x.classList.remove('active'));b.classList.add('active');loadDetail();}));
}

document.getElementById('language').addEventListener('change',e=>{state.lang=e.target.value;localStorage.setItem('kbeauty_lang',state.lang);applyLanguage();loadDashboard();if(state.currentKeyword)loadDetail();});
document.getElementById('refreshBtn').addEventListener('click',loadDashboard);
document.getElementById('backBtn').addEventListener('click',()=>{state.currentKeyword=null;document.getElementById('detailView').classList.add('hidden');document.getElementById('dashboardView').classList.remove('hidden');window.scrollTo({top:0,behavior:'smooth'});});

applyLanguage(); bindFilters(); loadDashboard();
