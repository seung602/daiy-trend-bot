const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];

const state = {
    lang: 'ko', kind: 'overall', page: 0, q: '', category: '',
    products: [], currentPeriod: 'daily', hasMore: false,
    initialLoad: 80, loadMoreStep: 50
};
let SUGGESTIONS = [];

const T = {
    ko: {
        navTrend: '트렌드', navProducts: '상품',
        eyebrow: 'K-BEAUTY MARKET SIGNALS', trendTitle: '오늘의 K-Beauty 트렌드',
        trendSub: '검색·소셜·지역 신호를 기반으로 시장의 흐름을 봅니다.',
        rising: '🔥 상승 트렌드', trendMatrix: '📈 트렌드 점수 매트릭스',
        themeRollup: '🧩 테마별 트렌드', daily: '일간', weekly: '주간', monthly: '월간',
        weeklyChanges: '🔄 이번 주 핵심 변화', weeklyTop: '🏆 주간 TOP 트렌드',
        monthlyChanges: '🔄 이번 달 핵심 변화', monthlyTop: '🏆 월간 TOP 트렌드',
        newEntries: '🆕 신규 진입', risingRank: '📈 상승', fallingRank: '📉 하락',
        changeTitle: '▲▼ 랭킹 변동', changeSub: '어제 대비 랭킹 변화를 확인합니다',
        productTitle: '상품 랭킹 & 전체 카탈로그',
        productSub: '올리브영·다이소·자체 종합점수로 상품의 시장 위치를 비교합니다.',
        overall: '종합랭킹', olive: '올리브영', daiso: '다이소', change: '▲▼ 변동',
        scoreDesc: '(올리브영 순위 + 트렌드 + 리뷰 종합 점수 기준)',
        catalog: '🛍️ 전체 상품 카탈로그', catalogSub: '카테고리·성분·키워드로 전체 상품을 탐색합니다.',
        searchPh: '상품명·브랜드·성분 검색 (예: 레티놀 세럼)', allCategories: '전체 카테고리',
        loadMore: '더 보기 (50)',
        rank: '랭크', source: '채널', details: '상품 상세',
        ingredients: '성분', product_type: '제품 유형', keywords: '키워드',
        skin_type: '피부 타입', concerns: '고민', texture: '제형',
        key_ingredients: '주요 성분', claims: '클레임',
        noData: '데이터 없음', scoreNone: '데이터 부족',
        mallOlive: '올리브영', mallDaiso: '다이소',
        trendRising: '상승세', trendFalling: '하락세', trendFlat: '보합', trendNew: '신규'
    },
    en: {
        navTrend: 'Trends', navProducts: 'Products',
        eyebrow: 'K-BEAUTY MARKET SIGNALS', trendTitle: "Today's K-Beauty Trends",
        trendSub: 'Read market flow from search, social and regional signals.',
        rising: '🔥 Rising Trends', trendMatrix: '📈 Trend Score Matrix',
        themeRollup: '🧩 Theme Rollup', daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly',
        weeklyChanges: '🔄 Key Changes This Week', weeklyTop: '🏆 Weekly TOP Trends',
        monthlyChanges: '🔄 Key Changes This Month', monthlyTop: '🏆 Monthly TOP Trends',
        newEntries: '🆕 New Entries', risingRank: '📈 Rising', fallingRank: '📉 Falling',
        changeTitle: '▲▼ Rank Changes', changeSub: 'Compare with yesterday\'s ranking',
        productTitle: 'Product Rankings & Full Catalog',
        productSub: 'Compare market position using Olive Young, Daiso and a unified score.',
        overall: 'Overall', olive: 'Olive Young', daiso: 'Daiso', change: '▲▼ Changes',
        scoreDesc: '(Composite score: Rank + Trend + Reviews)',
        catalog: '🛍️ Full Product Catalog', catalogSub: 'Explore products by category, ingredients and keywords.',
        searchPh: 'Search (e.g., Retinol Serum)', allCategories: 'All categories',
        loadMore: 'Load more (50)',
        rank: 'Rank', source: 'Channel', details: 'Product Details',
        ingredients: 'Ingredients', product_type: 'Product Type', keywords: 'Keywords',
        skin_type: 'Skin Type', concerns: 'Concerns', texture: 'Texture',
        key_ingredients: 'Key Ingredients', claims: 'Claims',
        noData: 'No data', scoreNone: 'Not enough data',
        mallOlive: 'Olive Young', mallDaiso: 'Daiso',
        trendRising: 'Rising', trendFalling: 'Falling', trendFlat: 'Flat', trendNew: 'New'
    },
    ar: {
        navTrend: 'الاتجاهات', navProducts: 'المنتجات',
        eyebrow: 'إشارات سوق K-BEAUTY', trendTitle: 'اتجاهات K-Beauty اليوم',
        trendSub: 'اقرأ حركة السوق من إشارات البحث والتواصل والمناطق.',
        rising: '🔥 الاتجاهات الصاعدة', trendMatrix: '📈 مصفوفة الدرجات',
        themeRollup: '🧩 ملخص الثيمات', daily: 'يومي', weekly: 'أسبوعي', monthly: 'شهري',
        weeklyChanges: '🔄 أهم التغييرات هذا الأسبوع', weeklyTop: '🏆 أفضل اتجاهات الأسبوع',
        monthlyChanges: '🔄 أهم التغييرات هذا الشهر', monthlyTop: '🏆 أفضل اتجاهات الشهر',
        newEntries: '🆕 جديد', risingRank: '📈 صاعد', fallingRank: '📉 هابط',
        changeTitle: '▲▼ تغييرات الترتيب', changeSub: 'مقارنة مع ترتيب الأمس',
        productTitle: 'ترتيب المنتجات والكتالوج الكامل',
        productSub: 'قارن موقع المنتج باستخدام Olive Young وDaiso والدرجة الموحدة.',
        overall: 'الترتيب العام', olive: 'Olive Young', daiso: 'Daiso', change: '▲▼ تغييرات',
        scoreDesc: '(درجة مركبة: الترتيب + الاتجاه + المراجعات)',
        catalog: '🛍️ كتالوج المنتجات', catalogSub: 'استكشف المنتجات حسب الفئة والمكونات.',
        searchPh: 'ابحث (مثال: سيروم الريتينول)', allCategories: 'كل الفئات',
        loadMore: 'عرض المزيد (50)',
        rank: 'الترتيب', source: 'القناة', details: 'تفاصيل المنتج',
        ingredients: 'المكونات', product_type: 'نوع المنتج', keywords: 'كلمات مفتاحية',
        skin_type: 'نوع البشرة', concerns: 'المشاكل', texture: 'القوام',
        key_ingredients: 'المكونات الرئيسية', claims: 'الادعاءات',
        noData: 'لا توجد بيانات', scoreNone: 'بيانات غير كافية',
        mallOlive: 'Olive Young', mallDaiso: 'Daiso',
        trendRising: 'صاعد', trendFalling: 'هابط', trendFlat: 'مستقر', trendNew: 'جديد'
    }
};

const THEME_T = {
    ko: { barrier_soothing: '장벽·진정', sun_protection: '자외선 차단', acne_pore: '여드름·모공', brightening_pigment: ' 미백·색소', antiaging_regeneration: '안티에이징·재생', hydration: '수분·보습', other: '기타' },
    en: { barrier_soothing: 'Barrier·Soothing', sun_protection: 'Sun Protection', acne_pore: 'Acne·Pore', brightening_pigment: 'Brightening·Pigment', antiaging_regeneration: 'Anti-aging·Regeneration', hydration: 'Hydration', other: 'Other' },
    ar: { barrier_soothing: 'حاجز·تهدئة', sun_protection: 'حماية الشمس', acne_pore: 'حب الشباب·المسام', brightening_pigment: 'تفتيح·تصبغات', antiaging_regeneration: 'مكافحة الشيخوخة', hydration: 'ترطيب', other: 'أخرى' }
};

function tr(k) { return T[state.lang][k] || T.en[k] || k; }
function themeT(key) { return (THEME_T[state.lang] || {})[key] || THEME_T.en[key] || key; }
function esc(x) { return String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function arr(v) { if (!v) return []; if (Array.isArray(v)) return v; try { const x = JSON.parse(v); if (Array.isArray(x)) return x; } catch {} return String(v).split(/[,|;\n]+/).map(x => x.trim()).filter(Boolean); }
async function api(u) { const r = await fetch(u); if (!r.ok) throw Error(r.status); return r.json(); }

function applyLang() {
    document.documentElement.lang = state.lang;
    document.body.classList.toggle('rtl', state.lang === 'ar');
    $$('[data-t]').forEach(e => e.textContent = tr(e.dataset.t));
    $$('[data-ph]').forEach(e => e.placeholder = tr(e.dataset.ph));
    renderAll();
}

// ========== Navigation / Tabs / Toggles ==========
$$('.langs button').forEach(b => b.onclick = () => { state.lang = b.dataset.lang; applyLang(); });
$$('.nav').forEach(b => b.onclick = () => {
    const p = b.dataset.page;
    $$('.nav').forEach(x => x.classList.toggle('active', x === b));
    $$('.page').forEach(x => x.classList.remove('active'));
    $('#' + p + 'Page').classList.add('active');
    if (p === 'products' && !state.products.length) loadProducts();
});
$$('.periodTab').forEach(b => b.onclick = () => {
    state.currentPeriod = b.dataset.period;
    $$('.periodTab').forEach(x => x.classList.toggle('active', x === b));
    $$('.periodContent').forEach(x => x.classList.remove('active'));
    $('#' + state.currentPeriod + 'Content').classList.add('active');
    loadPeriodData();
});
$$('.toggleHead').forEach(head => head.addEventListener('click', () => head.closest('.panel').classList.toggle('collapsed')));

// ========== Trend Renders ==========
function getTrendStatus(velocity) {
    if (velocity >= 0.10) return `<span style="color:var(--success)">📈 ${tr('trendRising')}</span>`;
    if (velocity <= -0.10) return `<span style="color:var(--fall)">📉 ${tr('trendFalling')}</span>`;
    if (velocity === 0) return `<span style="color:var(--text-muted)">➖ ${tr('trendFlat')}</span>`;
    return `<span style="color:var(--warning)">✨ ${tr('trendNew')}</span>`;
 }

function renderTrends(a) {
    $('#trendList').innerHTML = a.length ? a.map((x, i) => `
        <div class="trendRow">
            <div class="rankNo">${i + 1}</div>
            <div style="flex:1">
                <div class="trendName">${esc(x.keyword)}</div>
                <div class="trendMeta">
                    <span class="metaChip">${esc(themeT(x.theme))}</span>
                    ${getTrendStatus(x.velocity)}
                    <span class="metaChip">플랫폼: ${Math.round(x.cross_platform_score / 33.3)}개</span>
                </div>
            </div>
            <div class="grow">${x.trend_score.toFixed(1)}</div>
        </div>`).join('') : `<p class="muted">${tr('noData')}</p>`;
}

function renderMatrix(a) {
    $('#trendMatrix').innerHTML = a.map(x => `
        <div class="trendRow">
            <div style="width:150px"><b>${esc(x.keyword)}</b></div>
            <div style="flex:1">
                <div class="meta">
                    ${getTrendStatus(x.velocity)} · 
                    지속일: ${Math.round(x.persistence_score * 0.07)}일 · 
                    플랫폼: ${Math.round(x.cross_platform_score / 33.3)}개
                </div>
            </div>
            <b>${x.trend_score.toFixed(1)}</b>
        </div>`).join('');
}

function renderThemes(themes) {
    $('#themeGrid').innerHTML = themes.map((t, i) => {
        const rankClass = i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : 'normal';
        const rankLabel = state.lang === 'ko' ? `${i+1}위` : state.lang === 'ar' ? `المركز ${i+1}` : `#${i+1}`;
        return `
        <div class="themeCard" style="border-color:${t.color}44">
            <div class="themeHeader">
                <span class="themeRank ${rankClass}">${rankLabel}</span>
                <span class="themeIcon">${t.icon}</span>
                <span class="themeName">${esc(themeT(t.theme))}</span>
            </div>
            <div class="meta">${t.keyword_count} keywords</div>
            <div class="themeKeywords">${(t.top_keywords || []).slice(0, 5).map(k => `<span class="chip">${esc(k.keyword)}</span>`).join('')}</div>
        </div>`;
    }).join('');
}

// ========== Product Renders ==========
function rankCard(p, i) {
    const score = state.kind === 'overall' ? p.overall_score : state.kind === 'olive' ? p.olive_rank : p.daiso_score;
    const right = state.kind === 'olive' ? (score ? `# ${score}` : '—') : (Number(score) > 0 ? score.toFixed(1) : `<span class="noData">—</span>`);
    return `
    <div class="rankRow">
        <div class="rankNo">${i}</div>
        <div style="flex:1">
            <a href="${esc(p.product_url)}" target="_blank" rel="noopener noreferrer" class="prodNameLink">${esc(p.product_name)}</a>
            <div class="meta">${esc(p.brand || '')} · ${esc(p.category || '')}</div>
        </div>
        <div class="grow">${right}</div>
    </div>`;
}

function renderProducts() {
    const a = state.products;
    $('#products').innerHTML = a.map(p => `
        <div class="productCard" data-id="${esc(p.product_id)}">
            <div class="source">${esc(p.source || '')}</div>
            <a href="${esc(p.product_url)}" target="_blank" rel="noopener noreferrer" class="prodNameLink">${esc(p.product_name)}</a>
            <div class="meta">${esc(p.brand || '')} · ${esc(p.category || '')}</div>
            <div class="chips">${arr(p.keywords).slice(0, 4).map(x => `<span class="chip">${esc(x)}</span>`).join('')}</div>
        </div>`).join('');
    
    // 상품 카드 전체 클릭 시 링크 이동
    $$('.productCard').forEach(card => {
        card.onclick = () => {
            const url = a.find(p => p.product_id === card.dataset.id)?.product_url;
            if (url) window.open(url, '_blank');
        };
    });
    $('#loadMore').style.display = state.hasMore ? 'block' : 'none';
}

async function loadProducts(reset = true) {
    if (reset) { state.page = 0; state.products = []; }
    const q = encodeURIComponent(state.q), cat = encodeURIComponent(state.category);
    const limit = reset ? state.initialLoad : state.loadMoreStep;
    const d = await api(`/api/products?q=${q}&category=${cat}&limit=${limit}&offset=${state.page * state.loadMoreStep}`);
    state.products = reset ? d.items : state.products.concat(d.items);
    state.hasMore = d.has_more;
    $('#productDate').textContent = d.latest_date || $('#productDate').textContent;
    renderProducts();
}

async function loadRanking() {
    try {
        const d = await api('/api/rankings?kind=' + state.kind + '&limit=50');
        $('#productDate').textContent = d.latest_date || '';
        $('#rankTitle').textContent = tr(state.kind);
        $('#rankingList').innerHTML = d.items.map((p, i) => rankCard(p, i + 1)).join('');
    } catch (e) { $('#rankingList').innerHTML = '<p>' + tr('noData') + '</p>'; }
}

async function loadChangeData() {
    try {
        const d = await api('/api/rankings/change');
        const renderList = (items, type, elId) => {
            const el = $(elId);
            if (!items || !items.length) { el.innerHTML = `<li>${tr('noData')}</li>`; return; }
            el.innerHTML = items.slice(0, 15).map(item => {
                const mall = item.source === 'oliveyoung' ? tr('mallOlive') : tr('mallDaiso');
                let badge = '';
                if (type === 'new') badge = `<span class="changeBadge new">🆕</span>`;
                else if (type === 'rise') badge = `<span class="changeBadge rise">▲ +${item.diff}</span>`;
                else if (type === 'fall') badge = `<span class="changeBadge fall">▼ ${item.diff}</span>`;
                return `<li><a href="${esc(item.product_url || '#')}" target="_blank" class="prodNameLink">${esc(item.product_name)}</a> <span class="mallBadge">${mall}</span> ${badge}</li>`;
            }).join('');
        };
        renderList(d.new, 'new', '#changeNew');
        renderList(d.rising, 'rise', '#changeRise');
        renderList(d.falling, 'fall', '#changeFall');
    } catch (e) { console.error('Change data error:', e); }
}

async function loadCategories() {
    const d = await api('/api/categories');
    $('#category').innerHTML = '<option value="">' + tr('allCategories') + '</option>' + d.items.map(x => `<option value="${esc(x.category)}">${esc(x.category)} (${x.count})</option>`).join('');
}

// ========== Search autocomplete ==========
async function loadSuggestions() {
    try { const d = await api('/api/suggestions'); SUGGESTIONS = d.items || []; } catch (e) { SUGGESTIONS = []; }
}
function renderSuggestions() {
    const q = state.q.trim().toLowerCase();
    const list = SUGGESTIONS.filter(k => !q || k.toLowerCase().includes(q)).slice(0, 18);
    const box = $('#suggestBox');
    if (!list.length) { box.classList.remove('show'); return; }
    box.innerHTML = list.map(k => `<span class="chip" data-k="${esc(k)}">${esc(k)}</span>`).join('');
    box.classList.add('show');
    $$('#suggestBox .chip').forEach(ch => ch.onclick = () => {
        $('#search').value = ch.dataset.k; state.q = ch.dataset.k;
        box.classList.remove('show'); loadProducts();
    });
}

let timer;
$('#search').addEventListener('input', e => {
    state.q = e.target.value; renderSuggestions();
    clearTimeout(timer); timer = setTimeout(() => loadProducts(), 350);
});
$('#search').addEventListener('focus', renderSuggestions);
document.addEventListener('click', e => { if (!e.target.closest('.searchWrap')) $('#suggestBox').classList.remove('show'); });
$('#category').addEventListener('change', e => { state.category = e.target.value; loadProducts(); });
$('#loadMore').onclick = () => { state.page++; loadProducts(false); };

$$('.rankTab').forEach(b => b.onclick = () => {
    state.kind = b.dataset.kind;
    $$('.rankTab').forEach(x => x.classList.toggle('active', x === b));
    if (state.kind === 'change') {
        $('#rankPanel').style.display = 'none';
        $('#changePanel').style.display = 'block';
        loadChangeData();
    } else {
        $('#rankPanel').style.display = 'block';
        $('#changePanel').style.display = 'none';
        loadRanking();
    }
});

// ========== Data loading ==========
async function loadDailyData() {
    try {
        const d = await api('/api/trends/daily');
        $('#catalogDate').textContent = d.date || '';
        renderTrends(d.trends || []);
        renderMatrix(d.trends || []);
        const t = await api('/api/trends/themes');
        renderThemes(t.themes || []);
    } catch (e) { console.error('Daily trend load error:', e); }
}
async function loadWeeklyData() {
    try { const d = await api('/api/trends/weekly'); renderPeriodList(d.trends || [], '#weeklyList', 5); renderDelta(d.delta || {}, '#weeklyDelta'); } catch (e) { console.error(e); }
}
async function loadMonthlyData() {
    try { const d = await api('/api/trends/monthly'); renderPeriodList(d.trends || [], '#monthlyList', 30); renderDelta(d.delta || {}, '#monthlyDelta'); } catch (e) { console.error(e); }
}
function loadPeriodData() {
    if (state.currentPeriod === 'daily') loadDailyData();
    else if (state.currentPeriod === 'weekly') loadWeeklyData();
    else loadMonthlyData();
}

function renderPeriodList(a, sel, total) {
    $(sel).innerHTML = (a && a.length) ? a.map((x, i) => `
        <div class="trendRow">
            <div class="rankNo">${i + 1}</div>
            <div style="flex:1">
                <div class="trendName">${esc(x.keyword)}</div>
                <div class="trendMeta">
                    <span class="metaChip">${esc(themeT(x.theme))}</span>
                    <span class="metaChip">지속일: ${x.active_days}/${total}</span>
                </div>
            </div>
            <div class="grow">${x.total_score.toFixed(1)}</div>
        </div>`).join('') : `<p class="muted">${tr('noData')}</p>`;
}

function renderDelta(delta, sel) {
    const box = $(sel);
    if (!box) return;
    const li = (list, f) => (list && list.length ? list.slice(0, 10).map(f).join('') : `<li>${tr('noData')}</li>`);
    box.innerHTML = `
        <div class="deltaCard"><h3 class="new">${tr('newEntries')}</h3><ul class="deltaList">${li(delta.new, x => `<li>${esc(x.keyword)} <b>${x.score.toFixed(1)}</b></li>`)}</ul></div>
        <div class="deltaCard"><h3 class="rising">${tr('risingRank')}</h3><ul class="deltaList">${li(delta.rising, x => `<li>${esc(x.keyword)} <b>${x.prev_score.toFixed(1)} → ${x.curr_score.toFixed(1)}</b></li>`)}</ul></div>
        <div class="deltaCard"><h3 class="falling">${tr('fallingRank')}</h3><ul class="deltaList">${li(delta.cooling, x => `<li>${esc(x.keyword)} <b>${x.prev_score.toFixed(1)}${x.curr_score ? ' → ' + x.curr_score.toFixed(1) : ''}</b></li>`)}</ul></div>`;
}

function renderAll() {
    if ($('#trendPage').classList.contains('active')) loadPeriodData();
    if ($('#productsPage').classList.contains('active')) {
        if (state.kind === 'change') loadChangeData();
        else loadRanking();
        renderProducts();
    }
}

// ========== Init ==========
applyLang();
loadDailyData(); // 트렌드 섹션 정상 작동 보장
loadRanking();
loadCategories();
loadSuggestions();
