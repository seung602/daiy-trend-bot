#!/usr/bin/env python3
"""
Western Europe Cosmetics & Skincare Trend Bot — V4 Final
AI Auto Filter + Flow Engine + Theme Rollup + Lifecycle
"""

import os, sys, re, json, sqlite3, logging, datetime, calendar, math, hashlib, time
import xml.etree.ElementTree as ET
from collections import Counter
from typing import List, Dict, Tuple, Optional
from zoneinfo import ZoneInfo
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================
# 0. Gemini 모델 설정 (3.7 최신 → 3.6 fallback)
# ============================================================
GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "gemini-3.7-flash").strip()
GEMINI_FALLBACK_MODEL = "gemini-3.6-flash"

# ============================================================
# 1. 플랫폼 가중치 + 라이프사이클 라벨
# ============================================================
PLATFORM_WEIGHTS = {
    "tiktok": 1.5,
    "instagram": 1.2,
    "youtube": 1.0,
    "amazon": 0.9,
    "google": 0.8,
}

def _platform_weight(platform: str) -> float:
    p = (platform or "").lower()
    for key, w in PLATFORM_WEIGHTS.items():
        if key in p:
            return w
    return 1.0

LIFECYCLE_LABELS = {
    "DORMANT": "no recent signal",
    "NOISE_CANDIDATE": "possible noise",
    "SEED": "early signal",
    "WATCH": "watch",
    "EMERGING": "rising",
    "SCALING": "spreading",
    "ESTABLISHED": "steady",
    "COOLING": "cooling",
}

def lifecycle_label(status: str) -> str:
    return LIFECYCLE_LABELS.get((status or "").strip().upper(),
                                (status or "unknown").lower().replace("_", " "))

# ============================================================
# 2. 기본 설정
# ============================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

MARKET_TZ = ZoneInfo("Europe/Amsterdam")
DB_PATH = os.getenv("TREND_DB_PATH", "beauty_trends.db")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

TIKTOK_DAILY_LIMIT = 9
TIKTOK_QUERY_COUNT = 50

APIFY_INSTAGRAM_ENABLED = True
APIFY_INSTAGRAM_MONTHLY_RESULT_LIMIT = 1800
APIFY_INSTAGRAM_DAILY_RESULT_LIMIT = 60
APIFY_INSTAGRAM_ACTOR = "apify/instagram-scraper"

AMAZON_DAILY_LIMIT = 3
AMAZON_QUERY_COUNT = 50

YOUTUBE_SEARCH_CALLS_PER_DAY = 96
YOUTUBE_VIDEO_STATS_CALLS_PER_DAY = 6
YOUTUBE_SEARCH_RESULTS_PER_CALL = 50
YOUTUBE_VIDEO_STATS_BATCH_SIZE = 50
YOUTUBE_LOOKBACK_DAYS = 7

# AI Auto Filter 설정
AI_FILTER_ENABLED = os.getenv("AI_FILTER_ENABLED", "1").strip().lower() not in ("0", "false", "no")
AI_FILTER_MAX_SAMPLES = int(os.getenv("AI_FILTER_MAX_SAMPLES_PER_DAY", "700"))
AI_FILTER_BATCH_SIZE = int(os.getenv("AI_FILTER_BATCH_SIZE", "35"))
AI_FILTER_MIN_TEXT_LEN = 12
AI_FILTER_KEEP_QUALITIES = {"high", "medium"}

AI_FILTER_THEMES = [
    "barrier_soothing", "sun_protection", "acne_pore",
    "brightening_pigment", "antiaging_regeneration", "hydration", "other",
]
AI_FILTER_INTENTS = ["discovery", "informational", "review", "commercial"]

# ============================================================
# 3. 테마 규칙
# ============================================================
THEME_RULES = [
    ("barrier_soothing", ["ceramide","centella","cica","panthenol","ectoin","barrier","sensitive skin","redness","rosacea","soothing"]),
    ("sun_protection", ["sunscreen","sun stick","sunstick","spf","sun care"]),
    ("acne_pore", ["salicylic","azelaic","acne","pore","blemish","bha","aha"]),
    ("brightening_pigment", ["vitamin c","niacinamide","tranexamic","kojic","dark spot","hyperpigmentation","brightening","glow"]),
    ("antiaging_regeneration", ["retinol","retinal","bakuchiol","peptide","collagen","exosome","pdrn","polynucleotide","antiaging","anti-aging","firming","reedle","spicule","volufiline"]),
    ("hydration", ["hyaluronic","hydrat","dry skin","dehydrated","snail","propolis","squalane","urea"]),
]

def keyword_theme(keyword: str) -> str:
    kw = (keyword or "").lower()
    for theme, terms in THEME_RULES:
        if any(t in kw for t in terms):
            return theme
    return "other"

# ============================================================
# 4. 태그 로테이션 (trailing space 제거, 짧은 키워드召回)
# ============================================================
CORE_SEARCH_TAGS = [
    "skincare","skincare routine","beauty skincare","skincare trends",
    "viral skincare","trending skincare","skincare hacks","skincare ingredient",
    "viral ingredient","beauty ingredient","serum","viral serum","best serum",
    "face serum","skin barrier","barrier repair","sensitive skin",
    "retinol","retinal","anti aging","pdrn","polynucleotide","exosome",
    "peptide","collagen","firming","niacinamide","vitamin c","brightening",
    "acne","blemish","pore care","hyperpigmentation","dark spot",
    "dry skin","dehydrated skin","hydrating skincare","sunscreen",
    "sun stick","spf skincare","cica","centella","snail mucin",
    "spicule","azelaic acid","glass skin","skin flooding","skin cycling",
]

TIKTOK_QUERY_ROTATION = CORE_SEARCH_TAGS + [
    "skincare europe","skincare germany","beauty trends europe","beauty germany",
    "new skincare","skin booster","aha bha skincare","slugging skincare",
    "skinimalism","glowy skin","viral beauty","trending beauty",
]

YOUTUBE_QUERY_ROTATION = CORE_SEARCH_TAGS[:]

INSTAGRAM_ROTATION = [
    "skincare","skincareroutine","beautyskincare","skincaretrends",
    "viralskincare","trendingskincare","skincarehacks","skincareingredient",
    "viralingredient","beautyingredient","serum","viralserum","bestserum",
    "faceserum","skinbarrier","barrierrepair","sensitiveskin","retinol",
    "retinal","antiaging","pdrn","polynucleotide","exosome","peptide",
    "collagen","firming","niacinamide","vitaminc","brightening","acne",
    "blemish","porecare","hyperpigmentation","darkspot","dryskin",
    "dehydratedskin","hydratingskincare","sunscreen","sunstick","spf",
    "cica","centella","snailmucin","spicule","azelaicacid","glassskin",
    "skinflooding","skinscycling",
]

AMAZON_QUERY_ROTATION = [
    ["skincare","facial skincare","skincare set"],
    ["face serum","ampoule","essence"],
    ["moisturizer","face cream","barrier cream"],
    ["cleanser","toner","face mask"],
    ["sunscreen","sun stick","spf 50"],
    ["eye cream","anti aging cream","brightening cream"],
    ["retinol serum","retinal serum","bakuchiol serum"],
    ["niacinamide serum","vitamin c serum","tranexamic serum"],
    ["pdrn serum","pdrn cream","polynucleotide serum"],
    ["peptide serum","collagen serum","exosome serum"],
    ["ceramide cream","ectoin cream","barrier serum"],
    ["azelaic acid","salicylic serum","snail mucin"],
    ["propolis serum","centella serum","spicule serum"],
    ["hyaluronic serum","panthenol cream","fermented skincare"],
    ["acne skincare","blemish serum","pore serum"],
    ["dark spot serum","brightening serum","hyperpigmentation"],
    ["sensitive skin","redness cream","rosacea skincare"],
    ["dry skin","dehydrated skin","hydrating serum"],
    ["anti aging","fine lines","firming serum"],
    ["glass skin","skin barrier","barrier repair"],
    ["skin cycling","skin flooding","slugging"],
    ["viral skincare","trending skincare","best skincare"],
    ["best serum","best moisturizer","best sunscreen"],
    ["skincare gift set","trending products","viral serum"],
    ["skincare germany","sunscreen germany","skincare trends"],
    ["skincare europe","anti aging europe","beauty trends"],
]

GOOGLE_SEED_GROUPS = {
    "category": ["skincare","skin care","trending skincare","viral skincare","cosmetics","face serum","moisturizer","cleanser","sunscreen","facial skincare","anti aging"],
    "ingredient": ["pdrn","retinol","retinal","niacinamide","peptide","exosome","azelaic acid","ceramide","ectoin","bakuchiol","spicule","snail mucin","propolis","panthenol","tranexamic acid","vitamin c","salicylic acid","hyaluronic acid"],
    "problem": ["acne","dark spots","hyperpigmentation","skin barrier","barrier repair","redness","dry skin","aging skin","brightening","dehydrated skin","sensitive skin"],
    "product": ["serum","ampoule","essence","toner","moisturizer","face cream","sunscreen","sun stick","sheet mask","eye cream","cleanser","peeling"],
}

INGREDIENTS_VOCAB = [
    "pdrn","polynucleotide","retinol","retinal","bakuchiol","cica","centella",
    "niacinamide","spicule","reedle","reedle shot","peptide","copper peptide",
    "exosome","exosomes","azelaic","azelaic acid","salicylic","panthenol",
    "hyaluronic","collagen","ceramide","sunscreen","sunstick","sun stick",
    "glass skin","barrier","dark spot","dark spots","hyperpigmentation",
    "cleanser","toner","serum","moisturizer","moisturiser","essence",
    "ampoule","mask","vitamin c","tranexamic","tranexamic acid","kojic",
    "urea","squalane","snail","snail mucin","propolis","fermented",
    "fermentation","volufiline","peeling","aha","bha","pha","spf",
    "sun care","skin barrier","barrier repair","acne","antiaging","anti-aging",
    "hydration","hydrating","brightening","glow","slugging","skin cycling",
    "skin flooding","ectoin","pore","redness","rosacea","dry skin",
    "dehydrated skin","sensitive skin",
]

COMMERCIAL_WORDS = {"best","review","reviews","price","buy","where to buy","shop","product","products","serum","cream","ampoule","toner","sunscreen","moisturizer","cleanser","mask"}
INFORMATIONAL_WORDS = {"what","what is","benefits","benefit","how","why","meaning","side effects","before after"}

DYNAMIC_POOL_RATIO = 0.30
DYNAMIC_POOL_MAX_SIZE = 40
DYNAMIC_CANDIDATE_MIN_TIMES_SEEN = 2
DYNAMIC_CANDIDATE_LOOKBACK_DAYS = 14

# ============================================================
# 5. HTTP Session
# ============================================================
def get_robust_session() -> requests.Session:
    retries = Retry(total=2, backoff_factor=1, status_forcelist=[500,502,503,504], allowed_methods=["GET","POST"], raise_on_status=False)
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

session = get_robust_session()
apify_session = requests.Session()

# ============================================================
# 6. 날짜 / 유틸
# ============================================================
def get_market_now() -> datetime.datetime:
    return datetime.datetime.now(MARKET_TZ)

def get_today_iso() -> str:
    return get_market_now().date().isoformat()

def rotation_index(length: int) -> int:
    if length <= 0: return 0
    return (get_market_now().date() - datetime.date(2026,1,1)).days % length

def _clean_text(v: str) -> str:
    return re.sub(r"\s+", " ", (v or "")).strip()

def _clean_instagram_tag(v: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", (v or "").lower().replace(" ", ""))

def _dedupe(seq: List[str]) -> List[str]:
    seen, out = set(), []
    for v in seq:
        v = (v or "").strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out

def _normalize_entity(e: str) -> str:
    v = re.sub(r"[^\w\s-]", " ", (e or "").lower())
    return re.sub(r"\s+", " ", v).strip()[:45]

def _sha256(t: str) -> str:
    return hashlib.sha256((t or "").encode("utf-8")).hexdigest()

def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def normalize_keyword(kw: str) -> str:
    return kw.lower().strip()

# ============================================================
# 7. SQLite
# ============================================================
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS raw_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, collected_at TEXT NOT NULL,
        signal_date TEXT NOT NULL, platform TEXT NOT NULL, query TEXT,
        tag TEXT, region TEXT, text TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS keyword_daily (
        id INTEGER PRIMARY KEY AUTOINCREMENT, signal_date TEXT NOT NULL,
        keyword TEXT NOT NULL, platform TEXT NOT NULL, region TEXT NOT NULL,
        mentions INTEGER NOT NULL DEFAULT 0,
        UNIQUE(signal_date, keyword, platform, region))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS trend_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT, signal_date TEXT NOT NULL,
        keyword TEXT NOT NULL, volume_score REAL NOT NULL,
        velocity_score REAL NOT NULL, persistence_score REAL NOT NULL,
        cross_platform_score REAL NOT NULL, regional_score REAL NOT NULL,
        platform_normalized_score REAL NOT NULL DEFAULT 0,
        trend_score REAL NOT NULL, flow_score REAL NOT NULL DEFAULT 0,
        z_score REAL NOT NULL DEFAULT 0, active_days_14 INTEGER NOT NULL DEFAULT 0,
        validation_score REAL NOT NULL DEFAULT 0, lifecycle TEXT NOT NULL DEFAULT '',
        UNIQUE(signal_date, keyword))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS google_trends (
        id INTEGER PRIMARY KEY AUTOINCREMENT, signal_date TEXT NOT NULL,
        region TEXT NOT NULL, rank INTEGER NOT NULL, term TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS google_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, signal_date TEXT NOT NULL,
        collected_at TEXT NOT NULL, region TEXT NOT NULL, seed_keyword TEXT,
        keyword TEXT NOT NULL, query_type TEXT NOT NULL, intent TEXT NOT NULL,
        interest_score REAL, rising_score REAL, comparison_group TEXT,
        source TEXT NOT NULL,
        UNIQUE(signal_date, region, seed_keyword, keyword, query_type, source))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS google_keyword_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, signal_date TEXT NOT NULL,
        region TEXT NOT NULL, keyword TEXT NOT NULL, interest_score REAL,
        source TEXT NOT NULL, UNIQUE(signal_date, region, keyword, source))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS google_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT, first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL, keyword TEXT NOT NULL UNIQUE,
        source TEXT NOT NULL, times_seen INTEGER NOT NULL DEFAULT 1)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS api_usage (
        usage_month TEXT NOT NULL, provider TEXT NOT NULL, endpoint TEXT NOT NULL,
        calls INTEGER NOT NULL DEFAULT 0, last_called_at TEXT,
        PRIMARY KEY(usage_month, provider, endpoint))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS weekly_dynamic_pool (
        week_id TEXT PRIMARY KEY, keywords_json TEXT NOT NULL, created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_filter_state (
        key TEXT PRIMARY KEY, last_raw_id INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_filtered_signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, raw_id INTEGER NOT NULL,
        signal_date TEXT NOT NULL, platform TEXT NOT NULL, region TEXT,
        query TEXT, tag TEXT, text_hash TEXT NOT NULL, text TEXT,
        keep INTEGER NOT NULL DEFAULT 0, quality TEXT, theme TEXT,
        intent TEXT, ai_reason TEXT, confidence REAL, filtered_at TEXT NOT NULL,
        UNIQUE(signal_date, platform, text_hash))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS ai_entity_daily (
        id INTEGER PRIMARY KEY AUTOINCREMENT, signal_date TEXT NOT NULL,
        keyword TEXT NOT NULL, platform TEXT NOT NULL, region TEXT NOT NULL,
        theme TEXT NOT NULL DEFAULT 'other', quality TEXT NOT NULL DEFAULT 'medium',
        intent TEXT NOT NULL DEFAULT 'discovery', mentions INTEGER NOT NULL DEFAULT 0,
        UNIQUE(signal_date, keyword, platform, region, theme, quality, intent))""")

    for col, typ in [("platform_normalized_score","REAL NOT NULL DEFAULT 0"),
                     ("flow_score","REAL NOT NULL DEFAULT 0"),
                     ("z_score","REAL NOT NULL DEFAULT 0"),
                     ("active_days_14","INTEGER NOT NULL DEFAULT 0"),
                     ("validation_score","REAL NOT NULL DEFAULT 0"),
                     ("lifecycle","TEXT NOT NULL DEFAULT ''")]:
        try: conn.execute(f"ALTER TABLE trend_scores ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError: pass

    conn.commit(); conn.close()
    logging.info("SQLite initialized: %s", DB_PATH)

# ============================================================
# 8. Telegram
# ============================================================
def send_telegram_error(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        session.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                     json={"chat_id": TELEGRAM_CHAT_ID, "text": "🚨 Error\n\n"+msg}, timeout=10)
    except Exception as e:
        logging.error("Telegram error notification failed: %s", e)

def send_telegram_message(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chunk in [message[i:i+4000] for i in range(0, len(message), 4000)]:
        try:
            res = session.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk}, timeout=15)
            if res.status_code != 200:
                logging.warning("Telegram HTTP %s: %s", res.status_code, res.text[:200])
        except Exception as e:
            logging.error("Telegram send failed: %s", e)

# ============================================================
# 9. Google RSS + Autocomplete
# ============================================================
def fetch_google_daily_rss(geo: str, count: int = 15) -> List[str]:
    try:
        res = session.get(f"https://trends.google.com/trending/rss?geo={geo}",
                          headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if res.status_code != 200: return []
        root = ET.fromstring(res.content)
        return [i.text.strip() for i in root.findall(".//item/title") if i.text][:count]
    except: return []

def save_google_daily_rss(signal_date: str, region: str, terms: List[str]):
    if not terms: return
    conn = get_db()
    for rank, term in enumerate(terms, 1):
        conn.execute("INSERT INTO google_trends (signal_date,region,rank,term) VALUES (?,?,?,?)",
                     (signal_date, region, rank, term))
    conn.commit(); conn.close()

def fetch_google_autocomplete(seed: str, geo: str) -> List[str]:
    try:
        res = session.get("https://suggestqueries.google.com/complete/search",
                          params={"client":"firefox","q":seed,"hl":"en","gl":geo.lower()}, timeout=10)
        if res.status_code != 200: return []
        data = res.json()
        if not isinstance(data, list) or len(data) < 2: return []
        return [s.strip() for s in data[1] if isinstance(s,str) and s.strip().lower()!=seed.lower()][:10]
    except: return []

def classify_intent(keyword: str) -> str:
    t = keyword.lower()
    c = sum(1 for w in COMMERCIAL_WORDS if re.search(r"(?<!\w)"+re.escape(w)+r"(?!\w)", t))
    i = sum(1 for w in INFORMATIONAL_WORDS if w in t)
    if c > i and c > 0: return "commercial"
    if i > c and i > 0: return "informational"
    return "product_or_category"

def is_beauty_relevant(text: str) -> bool:
    t = text.lower()
    terms = ["skin","skincare","beauty","cosmetic","serum","cream","retinol","retinal",
             "pdrn","niacinamide","peptide","exosome","sunscreen","spf","acne","barrier",
             "toner","ampoule","essence","cleanser","mask","moisturizer","moisturiser",
             "hyperpigmentation","dark spot","kbeauty","cica","centella","ceramide",
             "ectoin","spicule","snail","propolis","bakuchiol","azelaic","salicylic"]
    return any(x in t for x in terms)

def save_google_signal(signal_date, region, seed, keyword, query_type, source,
                       interest_score=None, rising_score=None):
    conn = get_db()
    now = get_market_now().isoformat()
    intent = classify_intent(keyword)
    conn.execute("""INSERT INTO google_signals (signal_date,collected_at,region,seed_keyword,
        keyword,query_type,intent,interest_score,rising_score,comparison_group,source)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(signal_date,region,seed_keyword,keyword,query_type,source)
        DO UPDATE SET interest_score=excluded.interest_score, rising_score=excluded.rising_score""",
        (signal_date,now,region,seed,keyword,query_type,intent,interest_score,rising_score,seed,source))
    conn.execute("""INSERT INTO google_candidates (first_seen,last_seen,keyword,source,times_seen)
        VALUES (?,?,?,?,1) ON CONFLICT(keyword) DO UPDATE SET
        last_seen=excluded.last_seen, times_seen=google_candidates.times_seen+1""",
        (signal_date,signal_date,keyword,source))
    if interest_score is not None:
        conn.execute("""INSERT INTO google_keyword_history (signal_date,region,keyword,interest_score,source)
            VALUES (?,?,?,?,?) ON CONFLICT(signal_date,region,keyword,source)
            DO UPDATE SET interest_score=excluded.interest_score""",
            (signal_date,region,keyword,interest_score,source))
    conn.commit(); conn.close()

def collect_google_independent_signals(signal_date: str, regions: List[str]) -> Dict[str, List[Dict]]:
    output = {r: [] for r in regions}
    all_seeds = []
    for g in GOOGLE_SEED_GROUPS.values():
        all_seeds.extend([_clean_text(s) for s in g])
    unique = _dedupe(all_seeds)
    if not unique: return output
    start = rotation_index(len(unique))
    seeds = [unique[(start+i)%len(unique)] for i in range(min(12, len(unique)))]
    jobs = [(s, regions[i%len(regions)]) for i, s in enumerate(seeds)]
    logging.info("Google autocomplete jobs=%d (cap=12)", len(jobs))
    for seed, region in jobs:
        if is_beauty_relevant(seed):
            save_google_signal(signal_date, region, seed, seed, "seed", "google_seed")
        for sug in fetch_google_autocomplete(seed, region):
            if not is_beauty_relevant(sug): continue
            save_google_signal(signal_date, region, seed, sug, "related_candidate", "google_autocomplete")
            output[region].append({"keyword":sug,"seed":seed,"intent":classify_intent(sug),
                                   "source":"google_autocomplete","interest_score":None,"rising_score":None})
        time.sleep(1.2)
    return output

# ============================================================
# 10. TikTok
# ============================================================
def get_iso_week_id() -> str:
    y, w, _ = get_market_now().date().isocalendar()
    return f"{y}-W{w:02d}"

def build_dynamic_keyword_pool(limit: int = DYNAMIC_POOL_MAX_SIZE) -> List[str]:
    conn = get_db()
    lb = (get_market_now().date() - datetime.timedelta(days=DYNAMIC_CANDIDATE_LOOKBACK_DAYS)).isoformat()
    flow_rows = conn.execute("""SELECT keyword, COUNT(DISTINCT signal_date) AS days,
        COUNT(DISTINCT platform) AS plats FROM keyword_daily
        WHERE signal_date >= ? AND mentions > 0 GROUP BY keyword
        HAVING days >= 3 AND plats >= 2 ORDER BY days DESC, plats DESC LIMIT ?""",
        (lb, limit*2)).fetchall()
    trend_rows = conn.execute("""SELECT keyword, MAX(velocity_score) AS pv FROM trend_scores
        WHERE signal_date >= ? GROUP BY keyword HAVING pv >= 0.10 ORDER BY pv DESC LIMIT ?""",
        (lb, limit*2)).fetchall()
    cand_rows = conn.execute("""SELECT keyword, times_seen FROM google_candidates
        WHERE times_seen >= ? ORDER BY times_seen DESC, last_seen DESC LIMIT ?""",
        (DYNAMIC_CANDIDATE_MIN_TIMES_SEEN, limit*2)).fetchall()
    conn.close()
    pool, seen = [], set()
    for row in list(flow_rows)+list(trend_rows)+list(cand_rows):
        kw = (row["keyword"] or "").strip()
        if not kw or len(kw)<3 or kw.lower() in seen: continue
        if not is_beauty_relevant(kw): continue
        seen.add(kw.lower()); pool.append(kw)
        if len(pool)>=limit: break
    return pool

def get_weekly_dynamic_pool(limit: int = DYNAMIC_POOL_MAX_SIZE) -> List[str]:
    wid = get_iso_week_id()
    conn = get_db()
    row = conn.execute("SELECT keywords_json FROM weekly_dynamic_pool WHERE week_id=?", (wid,)).fetchone()
    if row:
        conn.close()
        try: return json.loads(row["keywords_json"])
        except: return []
    pool = build_dynamic_keyword_pool(limit)
    conn.execute("INSERT INTO weekly_dynamic_pool (week_id,keywords_json,created_at) VALUES (?,?,?) ON CONFLICT(week_id) DO NOTHING",
                 (wid, json.dumps(pool), get_market_now().isoformat()))
    conn.commit(); conn.close()
    return pool

def interleave_hybrid_expand(fixed, dynamic, ratio=DYNAMIC_POOL_RATIO):
    fl = {f.lower() for f in fixed}
    df = [d for d in dynamic if d.lower() not in fl]
    if not df or not fixed: return list(fixed)
    cnt = max(1, round(len(fixed)*ratio/(1-ratio)))
    sel = df[:cnt]
    sp = max(1, round(len(fixed)/len(sel)))
    res, di = [], 0
    for i, kw in enumerate(fixed):
        res.append(kw)
        if di < len(sel) and (i+1)%sp == 0:
            res.append(sel[di]); di += 1
    res.extend(sel[di:])
    return res

def replace_hybrid_fixed_size(fixed, dynamic, ratio=DYNAMIC_POOL_RATIO):
    fl = {f.lower() for f in fixed}
    df = [d for d in dynamic if d.lower() not in fl]
    if not df or not fixed: return list(fixed)
    rc = min(len(df), max(1, round(len(fixed)*ratio)))
    res = list(fixed)
    sp = max(1, len(res)//rc)
    for i in range(rc):
        res[min((i+1)*sp-1, len(res)-1)] = df[i]
    return res

def get_today_tiktok_queries() -> List[str]:
    pool = _dedupe([_clean_text(q) for q in interleave_hybrid_expand(TIKTOK_QUERY_ROTATION, get_weekly_dynamic_pool())])
    if not pool: return []
    s = rotation_index(len(pool))
    return [pool[(s+i)%len(pool)] for i in range(min(TIKTOK_DAILY_LIMIT, len(pool)))]

def fetch_tiktok_captions() -> List[Dict]:
    if not RAPIDAPI_KEY: return []
    url = "https://tiktok-scraper7.p.rapidapi.com/feed/search"
    hdr = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "tiktok-scraper7.p.rapidapi.com"}
    queries = get_today_tiktok_queries()[:TIKTOK_DAILY_LIMIT]
    results = []
    for qi, q in enumerate(queries):
        try:
            res = session.get(url, headers=hdr, params={"keywords":q,"region":"us","count":str(TIKTOK_QUERY_COUNT),"cursor":"0","publish_time":"0","sort_type":"0"}, timeout=15)
            if res.status_code != 200: continue
            data = res.json()
            if isinstance(data.get("code"), int) and data["code"] != 0: continue
            items = data.get("data",{}).get("videos",[]) if isinstance(data.get("data"),dict) else data.get("data",[])
            for item in (items or [])[:TIKTOK_QUERY_COUNT]:
                desc = str(item.get("title") or item.get("desc") or "").strip()
                if len(desc) <= 10: continue
                region = "DE" if "germany" in q.lower() else "EU"
                results.append({"platform":"tiktok","query":q,"tag":"","region":region,"text":desc.replace("\n"," ")[:180]})
        except Exception as e:
            logging.error("TikTok '%s' failed: %s", q, e)
        finally:
            if qi < len(queries)-1: time.sleep(0.5)
    logging.info("TikTok calls=%d/%d samples=%d", len(queries), TIKTOK_DAILY_LIMIT, len(results))
    return results

# ============================================================
# 11. Amazon
# ============================================================
def get_today_amazon_queries() -> List[str]:
    g = AMAZON_QUERY_ROTATION[rotation_index(len(AMAZON_QUERY_ROTATION))]
    return _dedupe([_clean_text(q) for q in g])[:AMAZON_DAILY_LIMIT]

def fetch_amazon_products() -> List[Dict]:
    if not RAPIDAPI_KEY: return []
    url = "https://real-time-amazon-data.p.rapidapi.com/search"
    hdr = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com"}
    results = []
    for qi, q in enumerate(get_today_amazon_queries()):
        try:
            res = session.get(url, headers=hdr, params={"query":q,"page":"1","country":"DE","sort_by":"RELEVANCE"}, timeout=15)
            if res.status_code != 200: continue
            prods = res.json().get("data",{}).get("products",[]) if isinstance(res.json().get("data"),dict) else []
            for item in prods[:AMAZON_QUERY_COUNT]:
                if not isinstance(item, dict): continue
                title = str(item.get("product_title") or "").strip()
                if len(title) <= 10: continue
                text = ("[BESTSELLER] " if item.get("is_best_seller") else "") + title
                results.append({"platform":"amazon","query":q,"tag":"","region":"DE","text":text.replace("\n"," ")[:180]})
        except Exception as e:
            logging.error("Amazon '%s' failed: %s", q, e)
        if qi < AMAZON_DAILY_LIMIT-1: time.sleep(0.5)
    logging.info("Amazon samples=%d", len(results))
    return results

# ============================================================
# 12. YouTube
# ============================================================
def _youtube_query_window() -> List[str]:
    pool = _dedupe([_clean_text(q) for q in replace_hybrid_fixed_size(YOUTUBE_QUERY_ROTATION, get_weekly_dynamic_pool())])
    target = len(YOUTUBE_QUERY_ROTATION)
    if len(pool) < target:
        for q in YOUTUBE_QUERY_ROTATION:
            if len(pool) >= target: break
            cq = _clean_text(q)
            if cq and cq not in pool: pool.append(cq)
    pool = pool[:target]
    s = rotation_index(len(pool))
    return [pool[(s+i)%len(pool)] for i in range(len(pool))]

def fetch_youtube_trends() -> List[Dict]:
    if not YOUTUBE_API_KEY: return []
    surl, vurl = "https://www.googleapis.com/youtube/v3/search", "https://www.googleapis.com/youtube/v3/videos"
    hdr = {"Accept": "application/json"}
    queries = _youtube_query_window()
    pa = (get_market_now()-datetime.timedelta(days=YOUTUBE_LOOKBACK_DAYS)).astimezone(datetime.timezone.utc).isoformat().replace("+00:00","Z")
    results, vids, seen, sc, vc, qe = [], [], set(), 0, 0, False
    for region in ["NL","DE"]:
        for q in queries:
            if sc >= YOUTUBE_SEARCH_CALLS_PER_DAY or qe: break
            try:
                res = session.get(surl, headers=hdr, params={"key":YOUTUBE_API_KEY,"part":"snippet","q":q,"type":"video",
                    "maxResults":str(YOUTUBE_SEARCH_RESULTS_PER_CALL),"order":"date","publishedAfter":pa,"regionCode":region,"safeSearch":"none"}, timeout=15)
                sc += 1
                if res.status_code != 200:
                    if res.status_code==403 and "quotaExceeded" in res.text: qe=True
                    continue
                for item in res.json().get("items",[]):
                    vid = str(item.get("id",{}).get("videoId") or "").strip()
                    sn = item.get("snippet",{}) or {}
                    title = str(sn.get("title") or "").strip()
                    desc = str(sn.get("description") or "").strip()
                    if not vid or not title or vid in seen: continue
                    if not is_beauty_relevant(title+" "+desc): continue
                    seen.add(vid); vids.append(vid)
                    results.append({"platform":"youtube","query":q,"tag":"","region":region,
                                    "text":title.replace("\n"," ")[:220],"video_id":vid,"published_at":sn.get("publishedAt")})
            except Exception as e:
                logging.error("YouTube '%s' [%s] failed: %s", q, region, e)
            time.sleep(0.15)
        if sc >= YOUTUBE_SEARCH_CALLS_PER_DAY or qe: break
    stats_ids = vids[:YOUTUBE_VIDEO_STATS_CALLS_PER_DAY*YOUTUBE_VIDEO_STATS_BATCH_SIZE]
    stats = {}
    for st in range(0, len(stats_ids), YOUTUBE_VIDEO_STATS_BATCH_SIZE):
        if vc >= YOUTUBE_VIDEO_STATS_CALLS_PER_DAY or qe: break
        batch = stats_ids[st:st+YOUTUBE_VIDEO_STATS_BATCH_SIZE]
        try:
            res = session.get(vurl, headers=hdr, params={"key":YOUTUBE_API_KEY,"part":"statistics,snippet","id":",".join(batch),
                "maxResults":str(YOUTUBE_VIDEO_STATS_BATCH_SIZE)}, timeout=15)
            vc += 1
            if res.status_code != 200:
                if res.status_code==403 and "quotaExceeded" in res.text: qe=True
                continue
            for item in res.json().get("items",[]):
                s = item.get("statistics",{}) or {}
                stats[item.get("id")] = {"views":s.get("viewCount"),"likes":s.get("likeCount"),"comments":s.get("commentCount")}
        except: pass
        time.sleep(0.15)
    for item in results:
        st = stats.get(item.get("video_id"),{})
        item["text"] = (item["text"]+f" [views={st.get('views','NA')}, likes={st.get('likes','NA')}, comments={st.get('comments','NA')}]")[:320]
    logging.info("YouTube search=%d/%d videos=%d/%d samples=%d", sc, YOUTUBE_SEARCH_CALLS_PER_DAY, vc, YOUTUBE_VIDEO_STATS_CALLS_PER_DAY, len(results))
    return results

# ============================================================
# 13. Instagram Apify
# ============================================================
APIFY_ACTOR_RUN_URL = "https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items"

def get_usage_month() -> str: return get_market_now().strftime("%Y-%m")
def get_api_calls(provider, endpoint, month=None):
    conn = get_db()
    r = conn.execute("SELECT calls FROM api_usage WHERE usage_month=? AND provider=? AND endpoint=?",
                     (month or get_usage_month(), provider, endpoint)).fetchone()
    conn.close()
    return int(r["calls"]) if r else 0

def get_apify_monthly_results():
    conn = get_db()
    r = conn.execute("SELECT COALESCE(SUM(calls),0) AS t FROM api_usage WHERE usage_month=? AND provider='apify_instagram'",
                     (get_usage_month(),)).fetchone()
    conn.close()
    return int(r["t"] or 0)

def get_apify_daily_results():
    return get_api_calls("apify_instagram", f"results:{get_today_iso()}", get_usage_month())

def add_apify_result_usage(count):
    if count <= 0: return
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""INSERT INTO api_usage(usage_month,provider,endpoint,calls,last_called_at)
            VALUES (?,'apify_instagram',?,?,?)
            ON CONFLICT(usage_month,provider,endpoint) DO UPDATE SET calls=calls+excluded.calls, last_called_at=excluded.last_called_at""",
            (get_usage_month(), f"results:{get_today_iso()}", count, get_market_now().isoformat()))
        conn.commit()
    except: conn.rollback(); raise
    finally: conn.close()

def get_today_apify_instagram_tags() -> List[str]:
    tags = _dedupe([_clean_instagram_tag(t) for t in INSTAGRAM_ROTATION if _clean_instagram_tag(t)])
    if not tags: return []
    idx = rotation_index(len(tags))
    return [tags[(idx+i)%len(tags)] for i in range(5)]

def fetch_instagram_apify() -> List[Dict]:
    if not APIFY_INSTAGRAM_ENABLED or not APIFY_TOKEN: return []
    used, used_today = get_apify_monthly_results(), get_apify_daily_results()
    remaining = min(APIFY_INSTAGRAM_MONTHLY_RESULT_LIMIT-used, APIFY_INSTAGRAM_DAILY_RESULT_LIMIT-used_today)
    if remaining <= 0: return []
    tags = get_today_apify_instagram_tags()
    rl = max(1, remaining // max(1, len(tags)))
    payload = {"directUrls":[f"https://www.instagram.com/explore/tags/{t}/" for t in tags],
               "resultsType":"posts","resultsLimit":rl,"onlyPostsNewerThan":"3 days","addParentData":True}
    hdr = {"Authorization":f"Bearer {APIFY_TOKEN}","Content-Type":"application/json"}
    try:
        res = apify_session.post(APIFY_ACTOR_RUN_URL, headers=hdr, json=payload, params={"token":APIFY_TOKEN}, timeout=120)
        if not (200 <= res.status_code < 300): return []
        data = res.json()
        if not isinstance(data, list): return []
        results, seen_ids = [], set()
        for item in data:
            if not isinstance(item, dict): continue
            sc = str(item.get("shortCode") or item.get("shortcode") or item.get("id") or "").strip()
            if sc and sc in seen_ids: continue
            if sc: seen_ids.add(sc)
            caption = str(item.get("caption") or "").strip()
            ht = item.get("hashtags") or []
            ht_text = " ".join("#"+str(x).lstrip("#") for x in ht if str(x).strip()) if isinstance(ht,list) else str(ht)
            text = (caption+(" "+ht_text if ht_text else "")).strip()
            if len(text) <= 10: continue
            owner = str(item.get("ownerUsername") or "").strip()
            likes, comments, views = item.get("likesCount"), item.get("commentsCount"), item.get("videoViewCount")
            m = []
            if likes is not None: m.append(f"likes={likes}")
            if comments is not None: m.append(f"comments={comments}")
            if views is not None: m.append(f"views={views}")
            if owner: text = f"@{owner}: "+text
            if m: text += " ["+", ".join(m)+"]"
            src_tag = ""
            parent = item.get("dataSource") or item.get("parentData")
            if isinstance(parent, dict): src_tag = str(parent.get("hashtag") or parent.get("tag") or "").strip().lstrip("#")
            if not src_tag and tags: src_tag = tags[0]
            results.append({"platform":"instagram","query":"","tag":src_tag,"region":"EU",
                            "text":text.replace("\n"," ")[:260],"likes":likes,"comments":comments,"views":views,"instagram_id":sc})
        add_apify_result_usage(len(data))
        logging.info("Instagram results=%d valid=%d quota=%d/%d", len(data), len(results), get_apify_monthly_results(), APIFY_INSTAGRAM_MONTHLY_RESULT_LIMIT)
        return results
    except requests.exceptions.Timeout: return []
    except Exception as e:
        logging.error("Instagram failed: %s", e); return []

# ============================================================
# 14. Raw signal 저장
# ============================================================
def save_raw_signals(signals: List[Dict]):
    if not signals: return
    conn = get_db()
    now, sd = get_market_now().isoformat(), get_today_iso()
    for s in signals:
        conn.execute("INSERT INTO raw_signals (collected_at,signal_date,platform,query,tag,region,text) VALUES (?,?,?,?,?,?,?)",
                     (now,sd,s.get("platform",""),s.get("query",""),s.get("tag",""),s.get("region",""),s.get("text","")))
    conn.commit(); conn.close()

# ============================================================
# 15. Gemini JSON 호출 (3.7 → 3.6 fallback)
# ============================================================
def _extract_json_array(text: str):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.DOTALL).strip()
    s, e = text.find("["), text.rfind("]")
    if s != -1 and e != -1 and e > s: text = text[s:e+1]
    return json.loads(text)

def call_gemini_json(prompt: str):
    if not GEMINI_API_KEY: raise RuntimeError("GEMINI_API_KEY missing")
    models = []
    for m in [GEMINI_MODEL, GEMINI_FALLBACK_MODEL]:
        if m and m not in models: models.append(m)
    hdr = {"Content-Type":"application/json","x-goog-api-key":GEMINI_API_KEY}
    last_err = "unknown"
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for use_mime in (True, False):
            gc = {"temperature":0.0,"maxOutputTokens":8192}
            if use_mime: gc["response_mime_type"] = "application/json"
            payload = {"contents":[{"parts":[{"text":prompt}]}],"generationConfig":gc}
            try:
                res = session.post(url, headers=hdr, json=payload, timeout=90)
            except Exception as e:
                last_err = str(e); continue
            if res.status_code == 404: last_err = f"{model} 404"; break
            if res.status_code == 400 and use_mime: continue
            if res.status_code != 200: raise RuntimeError(f"Gemini JSON HTTP {res.status_code}")
            data = res.json()
            cands = data.get("candidates",[])
            if not cands: last_err = f"{model} no candidates"; continue
            parts = cands[0].get("content",{}).get("parts",[])
            if not parts: last_err = f"{model} empty parts"; continue
            try: return _extract_json_array(parts[0].get("text",""))
            except Exception as e: last_err = f"{model} parse: {e}"
    raise RuntimeError(f"Gemini JSON failed: {last_err}")

def call_gemini_api(prompt: str) -> str:
    if not GEMINI_API_KEY: raise RuntimeError("GEMINI_API_KEY missing")
    models = []
    for m in [GEMINI_MODEL, GEMINI_FALLBACK_MODEL]:
        if m and m not in models: models.append(m)
    hdr = {"Content-Type":"application/json","x-goog-api-key":GEMINI_API_KEY}
    payload = {"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.2,"maxOutputTokens":8192}}
    last_err = "unknown"
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try: res = session.post(url, headers=hdr, json=payload, timeout=60)
        except Exception as e: last_err = str(e); continue
        if res.status_code == 404: last_err = f"{model} 404"; continue
        if res.status_code != 200: raise RuntimeError(f"Gemini HTTP {res.status_code}")
        data = res.json()
        cands = data.get("candidates",[])
        if not cands: last_err = f"{model} no candidates"; continue
        parts = cands[0].get("content",{}).get("parts",[])
        if not parts: last_err = f"{model} empty parts"; continue
        txt = parts[0].get("text","").strip()
        if not txt: last_err = f"{model} empty text"; continue
        return txt
    raise RuntimeError(f"Gemini failed: {last_err}")

# ============================================================
# 16. AI Auto Filter
# ============================================================
def _get_ai_last_raw_id() -> int:
    conn = get_db()
    r = conn.execute("SELECT last_raw_id FROM ai_filter_state WHERE key='raw_signals'").fetchone()
    conn.close()
    return int(r["last_raw_id"]) if r else 0

def _set_ai_last_raw_id(lid: int):
    conn = get_db()
    conn.execute("INSERT INTO ai_filter_state (key,last_raw_id,updated_at) VALUES ('raw_signals',?,?) ON CONFLICT(key) DO UPDATE SET last_raw_id=excluded.last_raw_id, updated_at=excluded.updated_at",
                 (lid, get_market_now().isoformat()))
    conn.commit(); conn.close()

def ai_local_prefilter(row) -> bool:
    text = (row["text"] or "").strip()
    if len(text) < AI_FILTER_MIN_TEXT_LEN: return False
    if not is_beauty_relevant(text): return False
    lower = text.lower()
    if any(m in lower for m in ["http://","https://","follow for more","giveaway","promo code","affiliate","ad link","discount code"]): return False
    return True

def build_ai_filter_prompt(batch_items):
    payload = [{"id":r["id"],"platform":r["platform"] or "","query":r["query"] or "","tag":r["tag"] or "",
                "region":r["region"] or "","text":(r["text"] or "")[:320]} for r, _ in batch_items]
    return f"""You are a cosmetics & skincare data-cleaning agent. Filter raw signals and extract beauty trend entities.

INPUT SIGNALS:
{json.dumps(payload, ensure_ascii=False)}

Return ONLY a valid JSON array. Each item:
{{"id":<same id>,"keep":true/false,"quality":"high"|"medium"|"low","theme":one of {json.dumps(AI_FILTER_THEMES)},"intent":one of {json.dumps(AI_FILTER_INTENTS)},"keywords":["kw1","kw2"],"confidence":0.0-1.0,"reason":"short"}}

RULES:
1. Keep only cosmetics/skincare/beauty signals. Discard unrelated content.
2. Keywords: short, canonical, lowercase, max 5. No brands unless trend signal. No hashtags/URLs.
3. If keep=false, keywords=[].
4. Prefer short recall-friendly terms but avoid meaningless generic words unless context is strong.
THEME GUIDE:
barrier_soothing: ceramide,centella,cica,panthenol,ectoin,sensitive skin,redness
sun_protection: sunscreen,spf,sun stick
acne_pore: acne,pore,salicylic,azelaic,bha,aha
brightening_pigment: vitamin c,niacinamide,dark spot,hyperpigmentation,brightening
antiaging_regeneration: retinol,retinal,peptide,collagen,pdrn,exosome,firming,anti-aging
hydration: hyaluronic,dry skin,snail mucin,propolis
other: beauty-related but not clearly above"""

def save_ai_filter_results(signal_date, batch_items, parsed):
    pmap = {}
    for item in parsed:
        if not isinstance(item, dict): continue
        try: pmap[int(item.get("id"))] = item
        except: pass
    conn = get_db()
    now = get_market_now().isoformat()
    saved = 0
    for row, thash in batch_items:
        ai = pmap.get(row["id"], {})
        keep = bool(ai.get("keep", False))
        quality = str(ai.get("quality","low")).lower().strip()
        if quality not in {"high","medium","low"}: quality = "low"
        theme = str(ai.get("theme","other")).lower().strip()
        if theme not in AI_FILTER_THEMES: theme = "other"
        intent = str(ai.get("intent","discovery")).lower().strip()
        if intent not in AI_FILTER_INTENTS: intent = "discovery"
        try: conf = max(0.0, min(1.0, float(ai.get("confidence",0))))
        except: conf = 0.0
        reason = str(ai.get("reason",""))[:220]
        raw_kws = ai.get("keywords") or ai.get("entities") or []
        if not isinstance(raw_kws, list): raw_kws = []
        kws = []
        for k in raw_kws:
            if isinstance(k, dict): k = k.get("name") or k.get("keyword") or k.get("entity") or ""
            k = _normalize_entity(str(k))
            if k and len(k)>=2 and len(k)<=45 and not re.fullmatch(r"\d+", k): kws.append(k)
        kws = list(dict.fromkeys(kws))[:5]
        cur = conn.execute("""INSERT OR IGNORE INTO ai_filtered_signals
            (raw_id,signal_date,platform,region,query,tag,text_hash,text,keep,quality,theme,intent,ai_reason,confidence,filtered_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row["id"],signal_date,row["platform"],row["region"] or "EU",row["query"] or "",row["tag"] or "",
             thash,row["text"] or "",1 if keep else 0,quality,theme,intent,reason,conf,now))
        if cur.rowcount == 0: continue
        if keep and quality in AI_FILTER_KEEP_QUALITIES and kws:
            for kw in kws:
                conn.execute("""INSERT INTO ai_entity_daily (signal_date,keyword,platform,region,theme,quality,intent,mentions)
                    VALUES (?,?,?,?,?,?,?,1)
                    ON CONFLICT(signal_date,keyword,platform,region,theme,quality,intent) DO UPDATE SET mentions=mentions+1""",
                    (signal_date,kw,row["platform"],row["region"] or "EU",theme,quality,intent))
                saved += 1
    conn.commit(); conn.close()
    return saved

def run_ai_filter(signal_date: str) -> int:
    if not AI_FILTER_ENABLED or not GEMINI_API_KEY: return 0
    last_id = _get_ai_last_raw_id()
    conn = get_db()
    rows = conn.execute("SELECT id,signal_date,platform,query,tag,region,text FROM raw_signals WHERE id > ? ORDER BY id ASC LIMIT ?",
                        (last_id, AI_FILTER_MAX_SAMPLES)).fetchall()
    conn.close()
    if not rows: return 0
    batch_items, seen = [], set()
    for row in rows:
        if not ai_local_prefilter(row): continue
        th = _sha256(f"{row['platform']}|{(row['text'] or '').strip().lower()}")
        if th in seen: continue
        seen.add(th); batch_items.append((row, th))
        if len(batch_items) >= AI_FILTER_MAX_SAMPLES: break
    total = 0
    for chunk in _chunks(batch_items, AI_FILTER_BATCH_SIZE):
        try:
            parsed = call_gemini_json(build_ai_filter_prompt(chunk))
            if not isinstance(parsed, list): parsed = []
            total += save_ai_filter_results(signal_date, chunk, parsed)
        except Exception as e:
            logging.error("AI filter batch failed: %s", e)
    if rows: _set_ai_last_raw_id(max(r["id"] for r in rows))
    logging.info("AI filter: candidates=%d entities=%d", len(batch_items), total)
    return total

# ============================================================
# 17. 키워드 추출 (로컬 폴백)
# ============================================================
def count_keywords_in_text(text: str) -> Counter:
    text = text.lower()
    counts = Counter()
    for kw in INGREDIENTS_VOCAB:
        kw = kw.strip().lower()
        if not kw: continue
        if re.search(r"(?<!\w)"+re.escape(kw)+r"(?!\w)", text):
            counts[normalize_keyword(kw)] = 1
    return counts

def build_daily_keyword_counts(signals: List[Dict]) -> Dict[Tuple[str,str,str],int]:
    counts = Counter()
    for s in signals:
        for kw in count_keywords_in_text(s["text"]):
            counts[(kw, s["platform"], s["region"])] += 1
    return counts

def build_daily_keyword_counts_from_ai(signal_date: str) -> Dict[Tuple[str,str,str],int]:
    conn = get_db()
    rows = conn.execute("""SELECT keyword,platform,region,SUM(mentions) AS m FROM ai_entity_daily
        WHERE signal_date=? AND quality IN ('high','medium') GROUP BY keyword,platform,region""",
        (signal_date,)).fetchall()
    conn.close()
    counts = Counter()
    for r in rows:
        kw = _normalize_entity(r["keyword"])
        if kw: counts[(kw, r["platform"], r["region"])] += int(r["m"])
    return counts

def clear_keyword_counts(signal_date: str):
    conn = get_db()
    conn.execute("DELETE FROM keyword_daily WHERE signal_date=?", (signal_date,))
    conn.commit(); conn.close()

def save_keyword_counts(signal_date: str, counts: Dict[Tuple[str,str,str],int]):
    if not counts: return
    conn = get_db()
    for (kw, plat, reg), m in counts.items():
        conn.execute("""INSERT INTO keyword_daily (signal_date,keyword,platform,region,mentions)
            VALUES (?,?,?,?,?) ON CONFLICT(signal_date,keyword,platform,region) DO UPDATE SET mentions=excluded.mentions""",
            (signal_date, kw, plat, reg, m))
    conn.commit(); conn.close()

# ============================================================
# 18. Flow Engine (EMA, Z-score, Momentum, Lifecycle)
# ============================================================
def _load_series_map(signal_date: str, days: int = 28) -> Dict[str, Dict[str,int]]:
    conn = get_db()
    rows = conn.execute("""SELECT keyword,signal_date,SUM(mentions) AS m FROM keyword_daily
        WHERE signal_date <= ? AND signal_date >= date(?,?) GROUP BY keyword,signal_date""",
        (signal_date, signal_date, f"-{days} day")).fetchall()
    conn.close()
    sm: Dict[str, Dict[str,int]] = {}
    for r in rows: sm.setdefault(r["keyword"],{})[r["signal_date"]] = r["m"]
    return sm

def _series_from_map(sm, kw, sd, days=28):
    bd = sm.get(kw, {})
    end = datetime.date.fromisoformat(sd)
    return [((end-datetime.timedelta(days=i)).isoformat(), bd.get((end-datetime.timedelta(days=i)).isoformat(),0)) for i in range(days-1,-1,-1)]

def _ema(vals, alpha):
    if not vals: return 0.0
    e = vals[0]
    for v in vals[1:]: e = alpha*v + (1-alpha)*e
    return e

def _flow_metrics(series):
    vals = [m for _,m in series]
    lv = [math.log1p(v) for v in vals]
    ema7 = _ema(lv[-7:], 0.35)
    ema28 = _ema(lv, 0.15)
    hist = lv[:-1]
    if hist:
        mean = sum(hist)/len(hist)
        var = sum((v-mean)**2 for v in hist)/len(hist)
        z = (lv[-1]-mean)/(math.sqrt(var)+1e-6)
    else: z = 0.0
    return {"today":vals[-1] if vals else 0, "ema7":ema7, "ema28":ema28, "momentum":ema7-ema28, "z":z,
            "a7":sum(1 for v in vals[-7:] if v>0), "a14":sum(1 for v in vals[-14:] if v>0), "a28":sum(1 for v in vals if v>0)}

def _validation_score(platforms: set, has_commercial: bool, a7: int) -> float:
    s = 0.0
    if "youtube" in platforms and "amazon" in platforms: s += 0.45
    elif "amazon" in platforms: s += 0.25
    elif "youtube" in platforms: s += 0.20
    if "tiktok" in platforms and ("instagram" in platforms or "youtube" in platforms): s += 0.20
    if has_commercial: s += 0.20
    if a7 >= 3: s += 0.15
    return min(s, 1.0)

def _observation_confidence(platforms: set, a14: int) -> float:
    if not platforms: return 1.0
    if a14 <= 1:
        if platforms == {"tiktok"}: return 0.70
        if len(platforms) == 1: return 0.85
    return 1.0

def _classify_lifecycle(fm, platforms, validation):
    if fm["today"] <= 0 and fm["a14"] == 0: return "DORMANT"
    if fm["a14"] <= 2:
        if platforms and platforms <= {"tiktok"} and fm["today"] > 0: return "NOISE_CANDIDATE"
        return "SEED"
    if fm["ema7"] < fm["ema28"]*0.75: return "COOLING"
    if validation >= 0.5 and fm["a14"] >= 4: return "SCALING"
    if fm["ema7"] > fm["ema28"]*1.15 and fm["a7"] >= 2: return "EMERGING"
    if fm["a14"] >= 8: return "ESTABLISHED"
    return "WATCH"

# ============================================================
# 19. Trend Scoring V3
# ============================================================
def get_keyword_daily_history(kw, end_date, days):
    conn = get_db()
    rows = conn.execute("""SELECT signal_date,SUM(mentions) AS tm FROM keyword_daily
        WHERE keyword=? AND signal_date<? AND signal_date>=date(?,?) GROUP BY signal_date ORDER BY signal_date""",
        (kw,end_date,end_date,f"-{days} day")).fetchall()
    conn.close()
    return [(r["signal_date"],r["tm"]) for r in rows]

def calculate_velocity(today, history):
    prev = [m for _,m in history if m > 0]
    if not prev: return 0.0, False
    avg = sum(prev)/len(prev)
    if avg <= 0: return 0.0, False
    return (today-avg)/avg, True

def calculate_persistence(history, window=7):
    if not history: return 0.0
    return min(sum(1 for _,m in history if m>0)/window, 1.0)

def calculate_cross_platform(kw, sd):
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT platform FROM keyword_daily WHERE keyword=? AND signal_date=? AND mentions>0",(kw,sd)).fetchall()
    conn.close()
    return min(len({r["platform"] for r in rows})/3.0, 1.0)

def calculate_regional_score(kw, sd):
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT region FROM keyword_daily WHERE keyword=? AND signal_date=? AND mentions>0",(kw,sd)).fetchall()
    conn.close()
    return min(len({r["region"] for r in rows})/2.0, 1.0)

def calculate_platform_normalized_score(kw, sd):
    conn = get_db()
    rows = conn.execute("""SELECT platform, SUM(CASE WHEN keyword=? THEN mentions ELSE 0 END) AS km,
        SUM(mentions) AS pm FROM keyword_daily WHERE signal_date=? GROUP BY platform""",(kw,sd)).fetchall()
    conn.close()
    rates = [min((r["km"] or 0)/(r["pm"] or 1),1.0) for r in rows if (r["pm"] or 0)>0]
    return sum(rates)/len(rates) if rates else 0.0

def calculate_generic_penalty(kw):
    generic = {"skincare","serum","cream","beauty","sunscreen","cleanser","toner","moisturizer","moisturiser","mask","cosmetics","kbeauty","skin barrier","glow","hydration","hydrating"}
    return 0.72 if (kw or "").lower().strip() in generic else 1.0

def calculate_weighted_volume_score(pm: Dict[str,int]) -> float:
    if not pm: return 0.0
    ws = sum(m*_platform_weight(p) for p,m in pm.items())
    tw = sum(_platform_weight(p) for p in pm)
    if tw <= 0: return 0.0
    return min(math.log1p(ws/tw)/math.log1p(30), 1.0)

def calculate_trend_scores(signal_date, daily_counts):
    keywords = {kw for kw,_,_ in daily_counts.keys()}
    sm = _load_series_map(signal_date, 28)
    conn = get_db()
    plat_rows = conn.execute("SELECT keyword,GROUP_CONCAT(DISTINCT platform) AS p FROM keyword_daily WHERE signal_date=? AND mentions>0 GROUP BY keyword",(signal_date,)).fetchall()
    kw_plats = {r["keyword"]: {x for x in r["p"].split(",") if x} for r in plat_rows}
    comm_rows = conn.execute("SELECT DISTINCT keyword FROM google_signals WHERE signal_date=? AND intent='commercial'",(signal_date,)).fetchall()
    conn.close()
    comm_kws = {r["keyword"] for r in comm_rows}
    pm_today: Dict[str, Dict[str,int]] = {}
    for (kw,plat,_),m in daily_counts.items():
        pm_today.setdefault(kw,{})[plat] = pm_today.get(kw,{}).get(plat,0)+m
    results = []
    for kw in keywords:
        today_m = sum(pm_today.get(kw,{}).values())
        hist = get_keyword_daily_history(kw, signal_date, 7)
        vel, has_hist = calculate_velocity(today_m, hist)
        pers = calculate_persistence(hist, 7)
        cross = calculate_cross_platform(kw, signal_date)
        regional = calculate_regional_score(kw, signal_date)
        plat_norm = calculate_platform_normalized_score(kw, signal_date)
        plats = kw_plats.get(kw, set())
        fm = _flow_metrics(_series_from_map(sm, kw, signal_date, 28))
        val = _validation_score(plats, kw in comm_kws, fm["a7"])
        obs_conf = _observation_confidence(plats, fm["a14"])
        vol = calculate_weighted_volume_score(pm_today.get(kw,{}))
        vel_score = (max(-1.0,min(vel,1.0))+1.0)/2.0 if has_hist else 0.5
        mom_score = max(0.0, min(1.0, 0.5+fm["momentum"]/2.0))
        pers14 = min(fm["a14"]/7.0, 1.0)
        base = (vol*0.15 + vel_score*0.20 + pers*0.10 + pers14*0.15 + cross*0.20 + regional*0.05 + plat_norm*0.10 + mom_score*0.05)*100
        trend = base * calculate_generic_penalty(kw) * obs_conf * (1.0+0.25*val)
        lifecycle = _classify_lifecycle(fm, plats, val)
        flow_sc = trend * (0.5+0.5*pers14)
        results.append({"keyword":kw,"today_mentions":today_m,"velocity":vel,"has_history":has_hist,
            "status":"RISING" if vel>=0.5 else "EMERGING" if vel>=0.1 else "DECLINING" if vel<=-0.3 else "ESTABLISHED" if pers>=0.4 else "EMERGING",
            "lifecycle":lifecycle,"z_score":fm["z"],"active_days_14":fm["a14"],"validation_score":val,
            "volume_score":vol*100,"velocity_score":vel_score*100,"persistence_score":pers*100,
            "cross_platform_score":cross*100,"regional_score":regional*100,"platform_normalized_score":plat_norm*100,
            "flow_score":flow_sc,"trend_score":trend})
    results.sort(key=lambda x: x["trend_score"], reverse=True)
    return results

def save_trend_scores(signal_date, scores):
    conn = get_db()
    for i in scores:
        conn.execute("""INSERT INTO trend_scores (signal_date,keyword,volume_score,velocity_score,persistence_score,
            cross_platform_score,regional_score,platform_normalized_score,trend_score,flow_score,z_score,
            active_days_14,validation_score,lifecycle) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(signal_date,keyword) DO UPDATE SET volume_score=excluded.volume_score,
            velocity_score=excluded.velocity_score,persistence_score=excluded.persistence_score,
            cross_platform_score=excluded.cross_platform_score,regional_score=excluded.regional_score,
            platform_normalized_score=excluded.platform_normalized_score,trend_score=excluded.trend_score,
            flow_score=excluded.flow_score,z_score=excluded.z_score,active_days_14=excluded.active_days_14,
            validation_score=excluded.validation_score,lifecycle=excluded.lifecycle""",
            (signal_date,i["keyword"],i["volume_score"],i["velocity_score"],i["persistence_score"],
             i["cross_platform_score"],i["regional_score"],i.get("platform_normalized_score",0),
             i["trend_score"],i.get("flow_score",0),i.get("z_score",0),i.get("active_days_14",0),
             i.get("validation_score",0),i.get("lifecycle","")))
    conn.commit(); conn.close()

# ============================================================
# 20. 테마 롤업 + Google 요약 + 트렌드 요약
# ============================================================
def build_theme_rollup(date_list):
    if not date_list: return "No theme data."
    conn = get_db()
    ph = ",".join("?" for _ in date_list)
    rows = conn.execute(f"""SELECT theme,keyword,SUM(mentions) AS m,COUNT(DISTINCT signal_date) AS d
        FROM ai_entity_daily WHERE signal_date IN ({ph}) AND quality IN ('high','medium') AND theme!='other'
        GROUP BY theme,keyword""", date_list).fetchall()
    conn.close()
    if rows:
        themes = {}
        for r in rows:
            agg = themes.setdefault(r["theme"],{"m":0,"kws":[]})
            agg["m"] += r["m"]; agg["kws"].append((r["keyword"],r["m"],r["d"]))
        lines = []
        for t,a in sorted(themes.items(), key=lambda x:-x[1]["m"]):
            top = sorted(a["kws"], key=lambda x:-x[1])[:5]
            lines.append(f"- {t}: 총 {a['m']} mentions | 대표: "+", ".join(f"{k}({m}회/{d}일)" for k,m,d in top))
        return "\n".join(lines) if lines else "No AI theme data."
    conn = get_db()
    rows = conn.execute(f"SELECT keyword,SUM(mentions) AS m,COUNT(DISTINCT signal_date) AS d FROM keyword_daily WHERE signal_date IN ({ph}) GROUP BY keyword", date_list).fetchall()
    conn.close()
    themes = {}
    for r in rows:
        t = keyword_theme(r["keyword"])
        if t == "other": continue
        agg = themes.setdefault(t,{"m":0,"kws":[]})
        agg["m"] += r["m"]; agg["kws"].append((r["keyword"],r["m"],r["d"]))
    lines = []
    for t,a in sorted(themes.items(), key=lambda x:-x[1]["m"]):
        top = sorted(a["kws"], key=lambda x:-x[1])[:5]
        lines.append(f"- {t}: 총 {a['m']} | 대표: "+", ".join(f"{k}({m}/{d}d)" for k,m,d in top))
    return "\n".join(lines) if lines else "No theme data."

def get_google_summary(signal_date, regions):
    conn = get_db()
    lines = []
    for region in regions:
        rows = conn.execute("""SELECT keyword,intent,interest_score,rising_score,source FROM google_signals
            WHERE signal_date=? AND region=? AND (query_type='related_candidate' OR query_type='interest')
            ORDER BY CASE WHEN rising_score IS NULL THEN -999999 ELSE rising_score END DESC,
            CASE WHEN interest_score IS NULL THEN -999999 ELSE interest_score END DESC LIMIT 20""",
            (signal_date, region)).fetchall()
        lines.append(f"[Google {region}]")
        if not rows: lines.append("No Google beauty discovery data today."); continue
        seen = set()
        for r in rows:
            if r["keyword"] in seen: continue
            seen.add(r["keyword"])
            i = f"{r['interest_score']:.0f}" if r["interest_score"] is not None else "NA"
            ri = f"{r['rising_score']:+.1f}%" if r["rising_score"] is not None else "NA"
            lines.append(f"- {r['keyword']} | intent={r['intent']} | interest={i} | rising={ri} | source={r['source']}")
    conn.close()
    return "\n".join(lines)

def get_google_candidate_list(signal_date, limit=30):
    conn = get_db()
    rows = conn.execute("""SELECT keyword FROM google_signals WHERE signal_date=?
        ORDER BY CASE WHEN rising_score IS NULL THEN 0 ELSE rising_score END DESC,
        CASE WHEN interest_score IS NULL THEN 0 ELSE interest_score END DESC LIMIT ?""",
        (signal_date, limit)).fetchall()
    conn.close()
    out, seen = [], set()
    for r in rows:
        if r["keyword"] not in seen: seen.add(r["keyword"]); out.append(r["keyword"])
    return out

def get_keyword_platforms(kw, sd):
    conn = get_db()
    rows = conn.execute("SELECT platform,SUM(mentions) AS m FROM keyword_daily WHERE keyword=? AND signal_date=? AND mentions>0 GROUP BY platform ORDER BY m DESC",(kw,sd)).fetchall()
    conn.close()
    return ", ".join(f"{r['platform']}({r['m']})" for r in rows) if rows else "none"

def build_trend_summary(scores, signal_date=None):
    if not scores: return "No quantitative social trend score available today."
    lines = []
    for rank, item in enumerate(scores[:10], 1):
        vel_txt = f"{item['velocity']*100:+.1f}%" if item["has_history"] else "INSUFFICIENT_HISTORY"
        plats = get_keyword_platforms(item["keyword"], signal_date) if signal_date else "unknown"
        lc = lifecycle_label(item.get("lifecycle",""))
        lines.append(f"{rank}. {item['keyword']} | lifecycle={lc} | mentions={item['today_mentions']} | "
                     f"platforms=[{plats}] | velocity={vel_txt} | active14={item.get('active_days_14',0)}d | "
                     f"validation={item.get('validation_score',0):.2f} | z={item.get('z_score',0):+.1f} | "
                     f"cross={item['cross_platform_score']:.0f}/100 | TREND_SCORE={item['trend_score']:.1f}/100")
    return "\n".join(lines)

# ============================================================
# 21. Gemini 리포트 (Daily / Weekly / Monthly)
# ============================================================
LIFECYCLE_GLOSSARY = """
INTUITIVE LIFECYCLE GLOSSARY (use these simple terms, not internal codes):
early signal = 초기 신호 = إشارة مبكرة
rising = 상승 = صاعد
spreading = 확산 = منتشر
steady = 꾸준함 = مستقر
cooling = 둔화 = يتراجع
possible noise = 노이즈 가능성 = ضوضاء محتملة
no recent signal = 최근 신호 없음 = لا توجد إشارة حديثة
SHORT KEYWORD RULE: Short keywords have broader recall. If a short keyword appears only on one platform with no confirmation, treat it as "possible noise" or "watch".
When describing lifecycle, prefer intuitive words. Do not output raw internal codes such as NOISE_CANDIDATE or SCALING."""

def generate_gemini_report(google_summary, google_candidates, social_data, freq_summary, trend_summary):
    social_lines = []
    for item in social_data:
        src = item.get("platform","")
        if item.get("query"): src += f"/{item['query']}"
        if item.get("tag"): src += f"/#{item['tag']}"
        social_lines.append(f"[{src} | {item.get('region','')}] {item.get('text','')}")
    social_text = "\n".join(social_lines)
    gc_text = ", ".join(google_candidates) if google_candidates else "NONE"
    if len(social_data)==0 and not google_summary.strip():
        data_status = "CRITICAL DATA STATUS: No live data today. Do not fabricate rankings."
    else:
        data_status = f"DATA STATUS: Valid social samples: {len(social_data)}. Google discovery is independent. Do not turn autocomplete into volume claims."
    prompt = f"""You are a market-intelligence analyst tracking cosmetics/skincare consumer interest in Western Europe (Netherlands, Germany, Belgium, Arab/Middle-Eastern communities). NOT a K-Beauty angle. Track ingredients, formats, skin concerns regardless of origin.
Generate a DAILY WESTERN-EUROPE COSMETICS & SKINCARE TREND REPORT.
{data_status}
IMPORTANT DATA MODEL:
TikTok=early viral. Instagram=secondary confirmation. Amazon=purchase-stage. Google=search discovery. YouTube=review/sustained interest.
Single-platform weak signals are not confirmed trends. Google Autocomplete candidates are NOT volume scores.
{LIFECYCLE_GLOSSARY}
GOOGLE INDEPENDENT DISCOVERY:
{google_summary}
GOOGLE CANDIDATES: {gc_text}
SOCIAL QUANTITATIVE TREND SCORES:
{trend_summary}
KNOWN VOCABULARY FREQUENCY:
{freq_summary}
LIVE SOCIAL SAMPLES:
{social_text}
ANALYSIS TASK: Grade signals ★★★(cross-platform+Google/Amazon), ★★(one strong source), ★(weak). Every TOP signal must name platforms. Keep language SIMPLE. No jargon like "velocity". Describe speed/duration naturally.
STRICT: THREE sections separated by ===SPLIT_SECTION===. Order: KOREAN, ARABIC, ENGLISH. No Dutch/German. No shelf/display concepts. Keep short.
--- SECTION 1 ---
🌐 글로벌 화장품 & 스킨케어 시장 데일리 트렌드 리포트
📊 오늘의 데이터 분석 (TOP 5): Title+star, plain-language platform/source analysis.
🔇 노이즈 구분
📌 짧은 시사점 (2-3문장)
===SPLIT_SECTION===
--- SECTION 2 ---
🌐 التقرير اليومي العالمي لاتجاهات مستحضرات التجميل والعناية بالبشرة
📊 تحليل بيانات اليوم (أفضل 5)
🔇 تمييز الضوضاء
📌 ملاحظات قصيرة
===SPLIT_SECTION===
--- SECTION 3 ---
🌐 GLOBAL COSMETICS & SKINCARE MARKET DAILY TREND REPORT
📊 TODAY'S DATA ANALYSIS (TOP 5)
🔇 NOISE CHECK
📌 SHORT IMPLICATIONS"""
    return call_gemini_api(prompt)

WEEKLY_SUMMARY_WEEKDAY = 5
FORCE_ROLLUPS = os.getenv("FORCE_ROLLUPS","").strip().lower() in ("1","true","yes")

def is_weekly_summary_day():
    return True if FORCE_ROLLUPS else get_market_now().date().weekday() == WEEKLY_SUMMARY_WEEKDAY

def is_monthly_summary_day():
    if FORCE_ROLLUPS: return True
    t = get_market_now().date()
    return t.day == calendar.monthrange(t.year, t.month)[1]

def get_past_month_dates(sd):
    t = datetime.date.fromisoformat(sd)
    f = t.replace(day=1)
    return [(f+datetime.timedelta(days=i)).isoformat() for i in range((t-f).days+1)]

def get_past_weekday_dates(sd):
    t = datetime.date.fromisoformat(sd)
    mon = t - datetime.timedelta(days=t.weekday())
    return [(mon+datetime.timedelta(days=i)).isoformat() for i in range(5)]

def get_preceding_dates(date_list, count):
    if not date_list: return []
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT signal_date FROM trend_scores WHERE signal_date < ? ORDER BY signal_date DESC LIMIT ?",
                        (min(date_list), count)).fetchall()
    conn.close()
    return sorted(r["signal_date"] for r in rows)

def _build_period_rollup(date_list, limit):
    if not date_list: return "No data."
    conn = get_db()
    ph = ",".join("?" for _ in date_list)
    rows = conn.execute(f"""SELECT keyword,SUM(trend_score) AS ts,AVG(trend_score) AS avg,MAX(trend_score) AS peak,
        COUNT(DISTINCT signal_date) AS ad,AVG(cross_platform_score) AS ac FROM trend_scores
        WHERE signal_date IN ({ph}) GROUP BY keyword""", date_list).fetchall()
    conn.close()
    pd = len(date_list)
    scored = []
    for r in rows:
        cov = r["ad"]/pd if pd else 0
        flow = (r["ts"]/pd)*math.log2(r["ad"]+1)*(0.7+0.3*cov)*(1.0+0.15*(r["ac"] or 0)/100.0)
        scored.append((r, flow))
    scored.sort(key=lambda x:-x[1])
    return "\n".join(f"- {r['keyword']}: flow={f:.1f} | 평균={r['avg']:.1f} | 최고={r['peak']:.1f} | 지속일={r['ad']}/{pd}일"
                     for r,f in scored[:limit]) or "No keyword data."

def build_period_delta(cur, prev):
    if not prev: return "No previous-period data available yet."
    conn = get_db()
    cph, pph = ",".join("?" for _ in cur), ",".join("?" for _ in prev)
    cr = conn.execute(f"SELECT keyword,SUM(trend_score) AS ts,COUNT(DISTINCT signal_date) AS d FROM trend_scores WHERE signal_date IN ({cph}) GROUP BY keyword", cur).fetchall()
    pr = conn.execute(f"SELECT keyword,SUM(trend_score) AS ts,COUNT(DISTINCT signal_date) AS d FROM trend_scores WHERE signal_date IN ({pph}) GROUP BY keyword", prev).fetchall()
    conn.close()
    cs = {r["keyword"]:(r["ts"],r["d"]) for r in cr}
    ps = {r["keyword"]:(r["ts"],r["d"]) for r in pr}
    new, rising, cooling = [], [], []
    for kw in set(cs)|set(ps):
        c,cd = cs.get(kw,(0,0)); p,pd_ = ps.get(kw,(0,0))
        if p==0 and c>0: new.append((kw,c,cd))
        elif p>0 and c==0: cooling.append((kw,p,pd_,0,0))
        elif p>0 and c>=p*1.5: rising.append((kw,p,pd_,c,cd))
        elif p>0 and c<=p*0.5: cooling.append((kw,p,pd_,c,cd))
    new.sort(key=lambda x:-x[1]); rising.sort(key=lambda x:-(x[3]-x[1])); cooling.sort(key=lambda x:(x[1]-x[3]) if x[3] else x[1], reverse=True)
    lines = ["신규 진입:"]+[f"- {k}: {s:.1f} ({d}일)" for k,s,d in new[:15]] or ["- none"]
    lines += ["","급상승 (1.5배 이상):"]+[f"- {k}: {p:.1f}({pd_}일) -> {c:.1f}({cd}일)" for k,p,pd_,c,cd in rising[:15]] or ["- none"]
    lines += ["","냉각/이탈:"]+[f"- {k}: {p:.1f}({pd_}일) -> {c:.1f}({cd}일)" for k,p,pd_,c,cd in cooling[:15]] or ["- none"]
    return "\n".join(lines)

def generate_weekly_summary_report(date_list, keyword_rollup, delta_text):
    theme_rollup = build_theme_rollup(date_list)
    prompt = f"""You are a market-intelligence analyst for Western Europe cosmetics/skincare trends. NOT K-Beauty angle. Focus on TRENDS and FLOWS.
Generate a WEEKLY TREND & FLOW ROLLUP covering {date_list[0]} to {date_list[-1]}.
{LIFECYCLE_GLOSSARY}
WEEKLY KEYWORD RANKING (by flow score = consistency-weighted):
{keyword_rollup}
THEME ROLLUP:
{theme_rollup}
WEEK-OVER-WEEK DELTA:
{delta_text}
Use delta and theme rollup as ground truth. Tag statuses: 🆕 신규 / 📈 상승 / ✅ 꾸준 / 📉 냉각. Group into 2-4 themes. Be honest about limitations.
THREE sections separated by ===SPLIT_SECTION===. KOREAN, ARABIC, ENGLISH.
--- SECTION 1 ---
📅 주간 화장품 & 스킨케어 트렌드 요약 ({date_list[0]} ~ {date_list[-1]})
🔄 이번 주 핵심 변화 | 🧩 테마로 보기 | 🏆 가장 꾸준했던 TOP 5 | ⚠️ 노이즈 주의 | 📌 다음 주 추적 포인트
===SPLIT_SECTION===
--- SECTION 2 ---
📅 ملخص أسبوعي لاتجاهات مستحضرات التجميل والعناية بالبشرة
===SPLIT_SECTION===
--- SECTION 3 ---
📅 WEEKLY COSMETICS & SKINCARE TREND ROLLUP ({date_list[0]} ~ {date_list[-1]})
🔄 KEY CHANGES | 🧩 THEMES | 🏆 TOP 5 CONSISTENT | ⚠️ NOISE | 📌 NEXT-WEEK TRACKING"""
    return call_gemini_api(prompt)

def generate_monthly_summary_report(date_list, keyword_rollup, delta_text):
    td = len(date_list)
    theme_rollup = build_theme_rollup(date_list)
    prompt = f"""You are a market-intelligence analyst for Western Europe cosmetics/skincare trends. NOT K-Beauty angle. Focus on TRENDS and FLOWS.
Generate a MONTHLY TREND & FLOW ROLLUP covering {date_list[0]} to {date_list[-1]} ({td} days).
{LIFECYCLE_GLOSSARY}
MONTHLY KEYWORD RANKING (by flow score):
{keyword_rollup}
THEME ROLLUP:
{theme_rollup}
MONTH-OVER-MONTH DELTA:
{delta_text}
Use delta and theme rollup as ground truth. Tag statuses. Group into 2-4 themes. Cover most persistent trends. Be honest.
THREE sections separated by ===SPLIT_SECTION===. KOREAN, ARABIC, ENGLISH.
--- SECTION 1 ---
🗓️ 월간 화장품 & 스킨케어 트렌드 요약 ({date_list[0]} ~ {date_list[-1]})
🔄 핵심 변화 | 🧩 테마 | 🏆 TOP 5 지속 트렌드 | 📉 노이즈 | 📌 다음 달 추적
===SPLIT_SECTION===
--- SECTION 2 ---
🗓️ ملخص شهري لاتجاهات مستحضرات التجميل والعناية بالبشرة
===SPLIT_SECTION===
--- SECTION 3 ---
🗓️ MONTHLY COSMETICS & SKINCARE TREND ROLLUP ({date_list[0]} ~ {date_list[-1]})
🔄 KEY CHANGES | 🧩 THEMES | 🏆 TOP 5 PERSISTENT | 📉 NOISE | 📌 NEXT-MONTH TRACKING"""
    return call_gemini_api(prompt)

# ============================================================
# 22. Quota snapshot
# ============================================================
def get_monthly_quota_snapshot():
    conn = get_db()
    rows = conn.execute("SELECT provider,endpoint,calls FROM api_usage WHERE usage_month=? ORDER BY provider,endpoint",(get_usage_month(),)).fetchall()
    conn.close()
    return " | ".join(f"{r['provider']}/{r['endpoint']}={r['calls']}" for r in rows) if rows else "No API calls recorded."

# ============================================================
# 23. Main Pipeline
# ============================================================
def main():
    logging.info("=== Daily Cosmetics Trend Bot V4 Started ===")
    try:
        init_database()
        signal_date = get_today_iso()
        regions = ["NL", "DE"]

        logging.info("Dynamic pool (%s): %s", get_iso_week_id(), get_weekly_dynamic_pool())
        logging.info("TikTok queries: %s", get_today_tiktok_queries())
        logging.info("Instagram tags: %s", get_today_apify_instagram_tags())

        # 1. Google
        google_data = collect_google_independent_signals(signal_date, regions)
        for region, items in google_data.items():
            logging.info("Google [%s]: %d signals", region, len(items))
        save_google_daily_rss(signal_date, "NL", fetch_google_daily_rss("NL", 15))
        save_google_daily_rss(signal_date, "DE", fetch_google_daily_rss("DE", 15))

        # 2. Social
        tiktok_signals = fetch_tiktok_captions()
        amazon_signals = fetch_amazon_products()
        instagram_signals = fetch_instagram_apify()
        youtube_signals = fetch_youtube_trends()
        all_signals = tiktok_signals + amazon_signals + instagram_signals + youtube_signals
        save_raw_signals(all_signals)

        # 3. AI Auto Filter
        if AI_FILTER_ENABLED:
            try: run_ai_filter(signal_date)
            except Exception as e:
                logging.error("AI filter failed; fallback to local: %s", e, exc_info=True)

        # 4. Trend source selection: AI first, local fallback
        ai_counts = build_daily_keyword_counts_from_ai(signal_date)
        if ai_counts:
            clear_keyword_counts(signal_date)
            daily_counts = ai_counts
            logging.info("Trend source: AI-filtered (%d pairs)", len(ai_counts))
        else:
            daily_counts = build_daily_keyword_counts(all_signals)
            logging.info("Trend source: local vocab (%d pairs)", len(daily_counts))
        save_keyword_counts(signal_date, daily_counts)

        # 5. Trend scores
        trend_scores = calculate_trend_scores(signal_date, daily_counts)
        save_trend_scores(signal_date, trend_scores)
        trend_summary_str = build_trend_summary(trend_scores, signal_date=signal_date)
        freq_lines = [f"- {i['keyword']}: {i['today_mentions']} mentions" for i in trend_scores[:20]]
        freq_summary_str = "\n".join(freq_lines) if freq_lines else "No vocabulary frequency data today."

        # 6. Google summary
        google_summary = get_google_summary(signal_date, regions)
        google_candidates = get_google_candidate_list(signal_date, 30)

        # 7. Gemini daily report
        report = generate_gemini_report(google_summary, google_candidates, all_signals, freq_summary_str, trend_summary_str)
        for idx, sec in enumerate([s.strip() for s in report.split("===SPLIT_SECTION===") if s.strip()]):
            logging.info("Sending daily section %d", idx+1)
            send_telegram_message(sec)

        # 8. Weekly rollup
        if is_weekly_summary_day():
            try:
                wd = get_past_weekday_dates(signal_date)
                kr = _build_period_rollup(wd, 25)
                pd_ = get_preceding_dates(wd, len(wd))
                delta = build_period_delta(wd, pd_)
                wr = generate_weekly_summary_report(wd, kr, delta)
                for idx, sec in enumerate([s.strip() for s in wr.split("===SPLIT_SECTION===") if s.strip()]):
                    send_telegram_message(sec)
            except Exception as e:
                logging.error("Weekly rollup failed: %s", e, exc_info=True)
                send_telegram_error(f"Weekly rollup failed: {e}")

        # 9. Monthly rollup
        if is_monthly_summary_day():
            try:
                md = get_past_month_dates(signal_date)
                kr = _build_period_rollup(md, 30)
                pd_ = get_preceding_dates(md, len(md))
                delta = build_period_delta(md, pd_)
                mr = generate_monthly_summary_report(md, kr, delta)
                for idx, sec in enumerate([s.strip() for s in mr.split("===SPLIT_SECTION===") if s.strip()]):
                    send_telegram_message(sec)
            except Exception as e:
                logging.error("Monthly rollup failed: %s", e, exc_info=True)
                send_telegram_error(f"Monthly rollup failed: {e}")

        logging.info("Quota: %s", get_monthly_quota_snapshot())
        logging.info("=== V4 Completed Successfully ===")

    except Exception as e:
        err = f"Pipeline failed: {e}"
        logging.error(err, exc_info=True)
        send_telegram_error(err)
        sys.exit(1)

if __name__ == "__main__":
    main()
