import os
import sys
import re
import json
import sqlite3
import logging
import datetime
import calendar
import math
from collections import Counter
from typing import List, Dict, Tuple, Optional
from zoneinfo import ZoneInfo
import time
import requests
import xml.etree.ElementTree as ET
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================
# SCORING V5 — 플랫폼 가중치 + EMA + Z-score + Lifecycle
# ============================================================
PLATFORM_WEIGHTS = {
    "tiktok": 1.5,     # 트렌드 선도 (가장 빠름)
    "instagram": 1.2,  # 확산 중
    "youtube": 1.0,    # 기준 (안정화)
    "amazon": 0.9,     # 실제 구매
    "google": 0.8,     # 검색 의도 (늦게 감지)
}

def _platform_weight(platform: str) -> float:
    p = (platform or "").lower()
    for key, w in PLATFORM_WEIGHTS.items():
        if key in p: return w
    return 1.0

LIFECYCLE_LABELS = {
    "DORMANT": "no recent signal", "NOISE_CANDIDATE": "possible noise",
    "SEED": "early signal", "WATCH": "watch", "EMERGING": "rising",
    "SCALING": "spreading", "ESTABLISHED": "steady", "COOLING": "cooling",
}

def lifecycle_label(status: str) -> str:
    return LIFECYCLE_LABELS.get((status or "").strip().upper(), (status or "unknown").lower().replace("_", " "))

# ============================================================
# 0. 기본 설정
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
MARKET_TZ = ZoneInfo("Europe/Amsterdam")
DB_PATH = os.getenv("TREND_DB_PATH", "beauty_trends.db")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
APIFY_TOKEN = os.getenv("APIFY_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Gemini: 빈 환경변수로 기본 모델이 덮어써지는 문제를 방지한다.
GEMINI_MODEL = (os.getenv("GEMINI_MODEL") or "gemini-3.6-flash").strip()
GEMINI_FALLBACK_MODEL = "gemini-3.5-flash-lite"

TIKTOK_DAILY_LIMIT = 9
TIKTOK_QUERY_COUNT = 50

APIFY_INSTAGRAM_ENABLED = True
APIFY_INSTAGRAM_MONTHLY_RESULT_LIMIT = 1800
APIFY_INSTAGRAM_DAILY_RESULT_LIMIT = 60
APIFY_INSTAGRAM_ACTOR = "apify/instagram-scraper"

AMAZON_DAILY_LIMIT = 3
AMAZON_QUERY_COUNT = 50

AMAZON_QUERY_ROTATION = [
    ["skincare", "skincare essentials", "facial skincare"],
    ["face serum", "ampoule", "essence"],
    ["moisturizer", "face cream", "barrier repair cream"],
    ["cleanser", "toner", "face mask"],
    ["sunscreen face", "sun stick", "spf 50 sunscreen"],
    ["eye cream", "anti aging cream", "brightening cream"],
    ["retinol serum", "retinal serum", "bakuchiol serum"],
    ["niacinamide serum", "vitamin c serum", "tranexamic acid serum"],
    ["pdrn serum", "pdrn skincare", "polynucleotide serum"],
    ["peptide serum", "collagen serum", "exosome skincare"],
    ["ceramide cream", "ectoin skincare", "skin barrier serum"],
    ["azelaic acid", "salicylic acid serum", "snail mucin"],
    ["propolis skincare", "centella cica", "spicule serum"],
    ["hyaluronic acid serum", "panthenol cream", "fermented skincare"],
    ["acne skincare", "blemish serum", "pore care"],
    ["hyperpigmentation", "dark spot serum", "brightening serum"],
    ["sensitive skin", "redness skincare", "rosacea skincare"],
    ["dry skin", "dehydrated skin", "hydrating serum"],
    ["anti aging skincare", "fine lines serum", "firming serum"],
    ["glass skin", "skin barrier", "barrier repair"],
    ["skin cycling", "skin flooding", "slugging skincare"],
    ["viral skincare", "trending skincare", "best skincare"],
    ["best serum", "best moisturizer", "best sunscreen"],
    ["skincare gift set", "trending skincare products", "viral serum"],
    ["skincare germany", "skincare trends germany", "sunscreen germany"],
    ["skincare europe", "skincare trends europe", "anti aging europe"],
]

YOUTUBE_SEARCH_CALLS_PER_DAY = 96
YOUTUBE_VIDEO_STATS_CALLS_PER_DAY = 6
YOUTUBE_SEARCH_RESULTS_PER_CALL = 50
YOUTUBE_VIDEO_STATS_BATCH_SIZE = 50
YOUTUBE_LOOKBACK_DAYS = 7

YOUTUBE_QUERY_ROTATION = [
    "skincare", "skincare routine", "beauty skincare", "skincare trends",
    "trending skincare routine", "skincare hacks", "skincare ingredient",
    "viral skincare ingredient", "beauty ingredient", "serum trend",
    "viral serum", "best serum", "skin barrier", "barrier repair",
    "sensitive skin skincare", "retinol skincare", "retinal skincare",
    "anti aging skincare", "pdrn skincare", "polynucleotide skincare",
    "exosome skincare", "peptide skincare", "collagen skincare",
    "firming skincare", "niacinamide skincare", "vitamin c skincare",
    "brightening skincare", "acne skincare", "blemish skincare",
    "pore care", "hyperpigmentation", "dark spot skincare",
    "brightening serum", "dry skin", "dehydrated skin",
    "hydrating skincare", "sunscreen", "sun stick", "spf skincare",
    "cica skincare", "centella skincare", "snail mucin",
    "spicule skincare", "spicule serum", "azelaic acid skincare",
    "glass skin", "skin flooding", "skin cycling"
]

TIKTOK_QUERY_ROTATION = [
    "skincare", "skincare routine", "beauty skincare",
    "skincare trends", "trending skincare routine", "skincare hacks",
    "skincare ingredient", "viral skincare ingredient", "beauty ingredient",
    "serum trend", "viral serum", "best serum",
    "skin barrier", "barrier repair", "sensitive skin skincare",
    "retinol skincare", "retinal skincare", "anti aging skincare",
    "pdrn skincare", "polynucleotide skincare", "exosome skincare",
    "peptide skincare", "collagen skincare", "firming skincare",
    "niacinamide skincare", "vitamin c skincare", "brightening skincare",
    "acne skincare", "blemish skincare", "pore care",
    "hyperpigmentation", "dark spot skincare", "brightening serum",
    "dry skin", "dehydrated skin", "hydrating skincare",
    "sunscreen", "sun stick", "spf skincare",
    "cica skincare", "centella skincare", "snail mucin",
    "spicule skincare", "spicule serum", "skin booster",
    "azelaic acid skincare", "salicylic acid skincare", "aha bha skincare",
    "glass skin", "skin flooding", "skin cycling",
    "slugging skincare", "skinimalism", "glowy skin",
    "viral beauty", "trending beauty", "new skincare",
    "skincare europe", "skincare trends europe", "beauty trends europe",
    "skincare germany", "skincare trends germany", "beauty germany",
]

INSTAGRAM_ROTATION = [
    "skincare", "skincaretrends", "skincarehacks", "beauty",
    "skincareproducts", "skincareroutine", "skincarecommunity",
    "skincareingredients", "beautytrends", "beautyproducts",
    "serum", "ampoule", "essence", "toner", "moisturizer",
    "sunscreen", "sunstick", "facemask", "sheetmask",
    "retinol", "retinal", "niacinamide", "pdrn", "polynucleotide",
    "peptide", "exosomeskincare", "ceramide", "ectoin",
    "centella", "cica", "snailmucin", "propolis",
    "spicule", "azelaicacid", "salicylicacid",
    "skinbarrier", "barrierrepair", "acneskincare",
    "hyperpigmentation", "darkspots", "sensitiveskin",
    "dryskin", "antiaging", "brighteningskincare",
    "glassskin", "skinscycling", "skinflooding",
    "viralbeauty", "viralskincare", "trendingskincare",
]

GOOGLE_SEED_GROUPS = {
    "category": [
        "skincare", "skin care", "trending skincare", "viral skincare", "cosmetics",
        "face serum", "moisturizer", "cleanser", "sunscreen",
        "facial skincare", "anti aging skincare"
    ],
    "ingredient": [
        "pdrn", "retinol", "retinal", "niacinamide", "peptide",
        "exosome", "azelaic acid", "ceramide", "ectoin", "bakuchiol",
        "spicule", "snail mucin", "propolis", "panthenol", "tranexamic acid",
        "vitamin c skincare", "salicylic acid", "hyaluronic acid"
    ],
    "problem": [
        "acne skincare", "dark spots", "hyperpigmentation",
        "skin barrier", "barrier repair", "redness skincare",
        "dry skin skincare", "aging skin", "brightening skincare",
        "dehydrated skin", "sensitive skin"
    ],
    "product": [
        "serum", "ampoule", "essence", "toner", "moisturizer",
        "face cream", "sunscreen", "sun stick", "sheet mask",
        "eye cream", "cleanser", "peeling"
    ]
}

INGREDIENTS_VOCAB = [
    "pdrn", "retinol", "cica", "niacinamide", "spicule", "reedle",
    "reedle shot", "peptide", "exosome", "exosomes", "azelaic",
    "azelaic acid", "salicylic", "panthenol", "hyaluronic", "collagen",
    "ceramide", "centella", "sunscreen", "sunstick", "sun stick",
    "glass skin", "barrier", "dark spot", "dark spots",
    "hyperpigmentation", "cleanser", "toner", "serum", "moisturizer",
    "moisturiser", "essence", "ampoule", "mask", "retinal", "bakuchiol",
    "vitamin c", "tranexamic", "tranexamic acid", "kojic", "urea",
    "squalane", "snail", "snail mucin", "propolis", "fermented",
    "fermentation", "volufiline", "peeling", "aha", "bha", "pha", "spf",
    "sun care", "skin barrier", "barrier repair", "acne", "acneskincare",
    "antiaging", "anti-aging", "hydration", "hydrating", "brightening",
    "glow", "slugging", "skin cycling", "skin flooding", "ectoin"
]

COMMERCIAL_WORDS = {
    "best", "review", "reviews", "price", "buy", "where to buy",
    "shop", "product", "products", "serum", "cream", "ampoule",
    "toner", "sunscreen", "moisturizer", "cleanser", "mask"
}
INFORMATIONAL_WORDS = {
    "what", "what is", "benefits", "benefit", "how", "why",
    "meaning", "side effects", "before after"
}

# ============================================================
# 1. HTTP Session
# ============================================================
def get_robust_session() -> requests.Session:
    retries = Retry(
        total=2,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False
    )
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retries))
    return s

session = get_robust_session()
apify_session = requests.Session()

# ============================================================
# 2. 날짜 / rotation
# ============================================================
def get_market_now() -> datetime.datetime:
    return datetime.datetime.now(MARKET_TZ)

def get_today_iso() -> str:
    return get_market_now().date().isoformat()

def rotation_index(length: int) -> int:
    if length <= 0: return 0
    epoch = datetime.date(2026, 1, 1)
    today = get_market_now().date()
    return (today - epoch).days % length

def get_today_tiktok_queries() -> List[str]:
    hybrid_pool = interleave_hybrid_expand(TIKTOK_QUERY_ROTATION, get_weekly_dynamic_pool())
    n = len(hybrid_pool)
    if n == 0: return []
    start = rotation_index(n)
    count = min(TIKTOK_DAILY_LIMIT, n)
    return [hybrid_pool[(start + i) % n] for i in range(count)]

def get_today_instagram_tag() -> str:
    if not INSTAGRAM_ROTATION: return "skincare"
    return INSTAGRAM_ROTATION[rotation_index(len(INSTAGRAM_ROTATION))]

def get_today_amazon_queries() -> List[str]:
    return AMAZON_QUERY_ROTATION[rotation_index(len(AMAZON_QUERY_ROTATION))]

def get_today_google_group_names() -> List[str]:
    names = list(GOOGLE_SEED_GROUPS.keys())
    idx = rotation_index(len(names))
    return [names[idx], names[(idx + 1) % len(names)]]

def get_today_google_seeds(limit: int = 12) -> List[str]:
    all_seeds = []
    for group in GOOGLE_SEED_GROUPS.values(): all_seeds.extend(group)
    unique = list(dict.fromkeys(all_seeds))
    if not unique: return []
    start = rotation_index(len(unique))
    return [unique[(start + i) % len(unique)] for i in range(min(limit, len(unique)))]

# ============================================================
# 2b. 동적 하이브리드 태그 파이프라인
# ============================================================
DYNAMIC_POOL_RATIO = 0.30
DYNAMIC_POOL_MAX_SIZE = 40
DYNAMIC_CANDIDATE_MIN_TIMES_SEEN = 2
DYNAMIC_CANDIDATE_LOOKBACK_DAYS = 14

def get_iso_week_id() -> str:
    year, week, _ = get_market_now().date().isocalendar()
    return f"{year}-W{week:02d}"

def build_dynamic_keyword_pool(limit: int = DYNAMIC_POOL_MAX_SIZE) -> List[str]:
    conn = get_db()
    today = get_market_now().date()
    lookback_start = (today - datetime.timedelta(days=DYNAMIC_CANDIDATE_LOOKBACK_DAYS)).isoformat()
    candidate_rows = conn.execute("""
        SELECT keyword, times_seen FROM google_candidates
        WHERE times_seen >= ? ORDER BY times_seen DESC, last_seen DESC LIMIT ?
    """, (DYNAMIC_CANDIDATE_MIN_TIMES_SEEN, limit * 2)).fetchall()
    trend_rows = conn.execute("""
        SELECT keyword, MAX(velocity_score) AS peak_velocity FROM trend_scores
        WHERE signal_date >= ? GROUP BY keyword HAVING peak_velocity >= 0.10
        ORDER BY peak_velocity DESC LIMIT ?
    """, (lookback_start, limit * 2)).fetchall()
    conn.close()
    
    pool = []
    seen_lower = set()
    for row in list(candidate_rows) + list(trend_rows):
        kw = (row["keyword"] or "").strip()
        if not kw: continue
        kw_lower = kw.lower()
        if kw_lower in seen_lower: continue
        if len(kw) < 3: continue
        if not is_beauty_relevant(kw): continue
        seen_lower.add(kw_lower)
        pool.append(kw)
        if len(pool) >= limit: break
    return pool

def get_weekly_dynamic_pool(limit: int = DYNAMIC_POOL_MAX_SIZE) -> List[str]:
    week_id = get_iso_week_id()
    conn = get_db()
    row = conn.execute("SELECT keywords_json FROM weekly_dynamic_pool WHERE week_id = ?", (week_id,)).fetchone()
    if row:
        conn.close()
        try: return json.loads(row["keywords_json"])
        except: return []
    pool = build_dynamic_keyword_pool(limit)
    conn.execute("""
        INSERT INTO weekly_dynamic_pool (week_id, keywords_json, created_at)
        VALUES (?, ?, ?) ON CONFLICT(week_id) DO NOTHING
    """, (week_id, json.dumps(pool), get_market_now().isoformat()))
    conn.commit()
    conn.close()
    return pool

def interleave_hybrid_expand(fixed: List[str], dynamic: List[str], ratio: float = DYNAMIC_POOL_RATIO) -> List[str]:
    fixed_lower = {f.lower() for f in fixed}
    dynamic_filtered = [d for d in dynamic if d.lower() not in fixed_lower]
    if not dynamic_filtered or not fixed: return list(fixed)
    target_dynamic_count = max(1, round(len(fixed) * ratio / (1 - ratio)))
    dynamic_selected = dynamic_filtered[:target_dynamic_count]
    spacing = max(1, round(len(fixed) / len(dynamic_selected)))
    result = []
    di = 0
    for idx, kw in enumerate(fixed):
        result.append(kw)
        if di < len(dynamic_selected) and (idx + 1) % spacing == 0:
            result.append(dynamic_selected[di])
            di += 1
    result.extend(dynamic_selected[di:])
    return result

def replace_hybrid_fixed_size(fixed: List[str], dynamic: List[str], ratio: float = DYNAMIC_POOL_RATIO) -> List[str]:
    fixed_lower = {f.lower() for f in fixed}
    dynamic_filtered = [d for d in dynamic if d.lower() not in fixed_lower]
    if not dynamic_filtered or not fixed: return list(fixed)
    replace_count = min(len(dynamic_filtered), max(1, round(len(fixed) * ratio)))
    result = list(fixed)
    spacing = max(1, len(result) // replace_count)
    for i in range(replace_count):
        idx = min((i + 1) * spacing - 1, len(result) - 1)
        result[idx] = dynamic_filtered[i]
    return result

# ============================================================
# 3. SQLite
# ============================================================
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS raw_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, collected_at TEXT NOT NULL, signal_date TEXT NOT NULL,
            platform TEXT NOT NULL, query TEXT, tag TEXT, region TEXT, text TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS keyword_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT, signal_date TEXT NOT NULL, keyword TEXT NOT NULL,
            platform TEXT NOT NULL, region TEXT NOT NULL, mentions INTEGER NOT NULL DEFAULT 0,
            UNIQUE(signal_date, keyword, platform, region)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trend_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT, signal_date TEXT NOT NULL, keyword TEXT NOT NULL,
            volume_score REAL NOT NULL, velocity_score REAL NOT NULL, persistence_score REAL NOT NULL,
            cross_platform_score REAL NOT NULL, regional_score REAL NOT NULL,
            platform_normalized_score REAL NOT NULL DEFAULT 0, trend_score REAL NOT NULL,
            UNIQUE(signal_date, keyword)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT, signal_date TEXT NOT NULL, region TEXT NOT NULL,
            rank INTEGER NOT NULL, term TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, signal_date TEXT NOT NULL, collected_at TEXT NOT NULL,
            region TEXT NOT NULL, seed_keyword TEXT, keyword TEXT NOT NULL, query_type TEXT NOT NULL,
            intent TEXT NOT NULL, interest_score REAL, rising_score REAL, comparison_group TEXT, source TEXT NOT NULL,
            UNIQUE(signal_date, region, seed_keyword, keyword, query_type, source)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_keyword_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, signal_date TEXT NOT NULL, region TEXT NOT NULL,
            keyword TEXT NOT NULL, interest_score REAL, source TEXT NOT NULL,
            UNIQUE(signal_date, region, keyword, source)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
            keyword TEXT NOT NULL UNIQUE, source TEXT NOT NULL, times_seen INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_usage (
            usage_month TEXT NOT NULL, provider TEXT NOT NULL, endpoint TEXT NOT NULL,
            calls INTEGER NOT NULL DEFAULT 0, last_called_at TEXT,
            PRIMARY KEY (usage_month, provider, endpoint)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS weekly_dynamic_pool (
            week_id TEXT PRIMARY KEY, keywords_json TEXT NOT NULL, created_at TEXT NOT NULL
        )
    """)
    
    # 기존 DB 호환: 신규 점수 컬럼이 없으면 추가 (V5 Ultimate)
    for col, typ in [
        ("platform_normalized_score", "REAL NOT NULL DEFAULT 0"),
        ("flow_score", "REAL NOT NULL DEFAULT 0"),
        ("z_score", "REAL NOT NULL DEFAULT 0"),
        ("active_days_14", "INTEGER NOT NULL DEFAULT 0"),
        ("validation_score", "REAL NOT NULL DEFAULT 0"),
        ("lifecycle", "TEXT NOT NULL DEFAULT ''")
    ]:
        try: conn.execute(f"ALTER TABLE trend_scores ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError: pass
        
    conn.commit()
    conn.close()
    logging.info("SQLite database initialized: %s", DB_PATH)

# ============================================================
# 4. Telegram Error
# ============================================================
def send_telegram_error(error_msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error("Telegram credentials missing.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        session.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": "🚨 Daily Trend Bot Error Alert\n\n" + error_msg}, timeout=10)
    except Exception as e:
        logging.error("Telegram error notification failed: %s", e)

# ============================================================
# 5~10. API Fetchers (유지)
# ============================================================
def fetch_google_daily_rss(geo: str, count: int = 15) -> List[str]:
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; BeautyTrendBot/1.0)"}
    try:
        res = session.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return []
        root = ET.fromstring(res.content)
        titles = [item.text.strip() for item in root.findall(".//item/title") if item.text]
        return titles[:count]
    except: return []

def save_google_daily_rss(signal_date: str, region: str, terms: List[str]):
    if not terms: return
    conn = get_db()
    for rank, term in enumerate(terms, start=1):
        conn.execute("INSERT INTO google_trends (signal_date, region, rank, term) VALUES (?, ?, ?, ?)", (signal_date, region, rank, term))
    conn.commit(); conn.close()

def fetch_google_autocomplete(seed: str, geo: str) -> List[str]:
    url = "https://suggestqueries.google.com/complete/search"
    params = {"client": "firefox", "q": seed, "hl": "en", "gl": geo.lower()}
    try:
        res = session.get(url, params=params, timeout=10)
        if res.status_code != 200: return []
        data = res.json()
        if not isinstance(data, list) or len(data) < 2: return []
        suggestions = data[1]
        if not isinstance(suggestions, list): return []
        output = []
        for item in suggestions:
            if isinstance(item, str):
                item = item.strip()
                if item and item.lower() != seed.lower(): output.append(item)
        return output[:10]
    except: return []

def classify_intent(keyword: str) -> str:
    text = keyword.lower()
    commercial = sum(1 for word in COMMERCIAL_WORDS if re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text))
    informational = sum(1 for word in INFORMATIONAL_WORDS if word in text)
    if commercial > informational and commercial > 0: return "commercial"
    if informational > commercial and informational > 0: return "informational"
    return "product_or_category"

def is_beauty_relevant(text: str) -> bool:
    t = text.lower()
    beauty_terms = [
        "skin", "skincare", "beauty", "cosmetic", "serum", "cream", "retinol", "retinal", "pdrn", "niacinamide", "peptide",
        "exosome", "sunscreen", "spf", "acne", "barrier", "toner", "ampoule", "essence", "cleanser", "mask", "moisturizer",
        "moisturiser", "hyperpigmentation", "dark spot", "kbeauty", "cica", "centella", "ceramide", "ectoin", "spicule",
        "snail", "propolis", "bakuchiol", "azelaic", "salicylic"
    ]
    return any(term in t for term in beauty_terms)

def save_google_signal(signal_date: str, region: str, seed: str, keyword: str, query_type: str, source: str, interest_score: Optional[float] = None, rising_score: Optional[float] = None):
    conn = get_db()
    now = get_market_now().isoformat()
    intent = classify_intent(keyword)
    conn.execute("""
        INSERT INTO google_signals (signal_date, collected_at, region, seed_keyword, keyword, query_type, intent, interest_score, rising_score, comparison_group, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(signal_date, region, seed_keyword, keyword, query_type, source) DO UPDATE SET interest_score = excluded.interest_score, rising_score = excluded.rising_score
    """, (signal_date, now, region, seed, keyword, query_type, intent, interest_score, rising_score, seed, source))
    conn.execute("""
        INSERT INTO google_candidates (first_seen, last_seen, keyword, source, times_seen) VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(keyword) DO UPDATE SET last_seen = excluded.last_seen, times_seen = google_candidates.times_seen + 1
    """, (signal_date, signal_date, keyword, source))
    if interest_score is not None:
        conn.execute("""
            INSERT INTO google_keyword_history (signal_date, region, keyword, interest_score, source) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(signal_date, region, keyword, source) DO UPDATE SET interest_score = excluded.interest_score
        """, (signal_date, region, keyword, interest_score, source))
    conn.commit(); conn.close()

def collect_google_independent_signals(signal_date: str, regions: List[str]) -> Dict[str, List[Dict]]:
    output = {region: [] for region in regions}
    seeds = get_today_google_seeds(limit=12)
    jobs = []
    for i, seed in enumerate(seeds):
        region = regions[i % len(regions)]
        jobs.append((seed, region))
    for seed, region in jobs:
        if is_beauty_relevant(seed):
            save_google_signal(signal_date=signal_date, region=region, seed=seed, keyword=seed, query_type="seed", source="google_seed")
        suggestions = fetch_google_autocomplete(seed, region)
        for suggestion in suggestions:
            if not is_beauty_relevant(suggestion): continue
            save_google_signal(signal_date=signal_date, region=region, seed=seed, keyword=suggestion, query_type="related_candidate", source="google_autocomplete")
            output[region].append({"keyword": suggestion, "seed": seed, "intent": classify_intent(suggestion), "source": "google_autocomplete", "interest_score": None, "rising_score": None})
        time.sleep(1.2)
    return output

def fetch_tiktok_captions() -> List[Dict]:
    if not RAPIDAPI_KEY: return []
    url = "https://tiktok-scraper7.p.rapidapi.com/feed/search"
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "tiktok-scraper7.p.rapidapi.com"}
    queries = get_today_tiktok_queries()[:TIKTOK_DAILY_LIMIT]
    results = []
    for query_index, query in enumerate(queries):
        try:
            res = session.get(url, headers=headers, params={"keywords": query, "region": "us", "count": str(TIKTOK_QUERY_COUNT), "cursor": "0", "publish_time": "0", "sort_type": "0"}, timeout=15)
            if res.status_code != 200: continue
            data = res.json()
            if isinstance(data.get("code"), int) and data["code"] != 0: continue
            if isinstance(data.get("data"), list): items = data["data"]
            elif isinstance(data.get("data"), dict): items = data["data"].get("videos") or data["data"].get("item_list") or []
            else: items = data.get("videos") or data.get("item_list") or []
            for item in items[:TIKTOK_QUERY_COUNT]:
                desc = item.get("title") or item.get("desc") or ""
                if not desc: continue
                desc = str(desc).strip()
                if len(desc) <= 10: continue
                region = "EU"
                q = query.lower()
                if "germany" in q: region = "DE"
                elif "europe" in q: region = "EU"
                results.append({"platform": "tiktok", "query": query, "tag": "", "region": region, "text": desc.replace("\n", " ")[:180]})
        except: pass
        finally:
            if query_index < len(queries) - 1: time.sleep(0.5)
    return results

def fetch_amazon_products() -> List[Dict]:
    if not RAPIDAPI_KEY: return []
    url = "https://real-time-amazon-data.p.rapidapi.com/search"
    headers = {"x-rapidapi-key": RAPIDAPI_KEY, "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com"}
    queries = get_today_amazon_queries()[:AMAZON_DAILY_LIMIT]
    results = []
    for query_index, query in enumerate(queries):
        try:
            res = session.get(url, headers=headers, params={"query": query, "page": "1", "country": "DE", "sort_by": "RELEVANCE"}, timeout=15)
            if res.status_code != 200: continue
            data = res.json()
            products = data.get("data", {}).get("products", []) if isinstance(data.get("data"), dict) else []
            for item in products[:AMAZON_QUERY_COUNT]:
                if not isinstance(item, dict): continue
                title = str(item.get("product_title") or "").strip()
                if not title or len(title) <= 10: continue
                is_best_seller = bool(item.get("is_best_seller"))
                text = ("[BESTSELLER] " + title) if is_best_seller else title
                results.append({"platform": "amazon", "query": query, "tag": "", "region": "DE", "text": text.replace("\n", " ")[:180]})
        except: pass
        if query_index < len(queries) - 1: time.sleep(0.5)
    return results

def get_usage_month() -> str: return get_market_now().strftime("%Y-%m")
def get_api_calls(provider: str, endpoint: str, month: Optional[str] = None) -> int:
    month = month or get_usage_month()
    conn = get_db()
    row = conn.execute("SELECT calls FROM api_usage WHERE usage_month = ? AND provider = ? AND endpoint = ?", (month, provider, endpoint)).fetchone()
    conn.close()
    return int(row["calls"]) if row else 0

def get_monthly_quota_snapshot() -> str:
    month = get_usage_month()
    conn = get_db()
    rows = conn.execute("SELECT provider, endpoint, calls FROM api_usage WHERE usage_month = ? ORDER BY provider, endpoint", (month,)).fetchall()
    conn.close()
    if not rows: return "No API calls recorded this month."
    return " | ".join(f"{r['provider']}/{r['endpoint']}={r['calls']}" for r in rows)

def _youtube_query_window() -> List[str]:
    hybrid_pool = replace_hybrid_fixed_size(YOUTUBE_QUERY_ROTATION, get_weekly_dynamic_pool())
    if not hybrid_pool: return []
    n = len(hybrid_pool)
    start = rotation_index(n)
    return [hybrid_pool[(start + i) % n] for i in range(n)]

def fetch_youtube_trends() -> List[Dict]:
    if not YOUTUBE_API_KEY: return []
    search_url = "https://www.googleapis.com/youtube/v3/search"
    videos_url = "https://www.googleapis.com/youtube/v3/videos"
    headers = {"Accept": "application/json"}
    queries = _youtube_query_window()
    regions = ["NL", "DE"]
    published_after = (get_market_now() - datetime.timedelta(days=YOUTUBE_LOOKBACK_DAYS)).astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    results = []
    video_ids = []
    seen_ids = set()
    search_calls = 0
    stats_calls = 0
    quota_exhausted = False
    for region in regions:
        for query in queries:
            if search_calls >= YOUTUBE_SEARCH_CALLS_PER_DAY or quota_exhausted: break
            try:
                res = session.get(search_url, headers=headers, params={"key": YOUTUBE_API_KEY, "part": "snippet", "q": query, "type": "video", "maxResults": str(YOUTUBE_SEARCH_RESULTS_PER_CALL), "order": "date", "publishedAfter": published_after, "regionCode": region, "safeSearch": "none"}, timeout=15)
                search_calls += 1
                if res.status_code != 200:
                    if res.status_code == 403 and "quotaExceeded" in res.text: quota_exhausted = True
                    continue
                data = res.json()
                for item in data.get("items", []):
                    video_id = str(item.get("id", {}).get("videoId") or "").strip()
                    snippet = item.get("snippet", {}) or {}
                    title = str(snippet.get("title") or "").strip()
                    description = str(snippet.get("description") or "").strip()
                    if not video_id or not title or video_id in seen_ids: continue
                    if not is_beauty_relevant(title + " " + description): continue
                    seen_ids.add(video_id)
                    video_ids.append(video_id)
                    results.append({"platform": "youtube", "query": query, "tag": "", "region": region, "text": title.replace("\n", " ")[:220], "video_id": video_id, "published_at": snippet.get("publishedAt")})
            except: pass
            time.sleep(0.15)
        if search_calls >= YOUTUBE_SEARCH_CALLS_PER_DAY or quota_exhausted: break
        
    stats_ids = video_ids[:YOUTUBE_VIDEO_STATS_CALLS_PER_DAY * YOUTUBE_VIDEO_STATS_BATCH_SIZE]
    stats_by_id = {}
    for start in range(0, len(stats_ids), YOUTUBE_VIDEO_STATS_BATCH_SIZE):
        if stats_calls >= YOUTUBE_VIDEO_STATS_CALLS_PER_DAY or quota_exhausted: break
        batch = stats_ids[start:start + YOUTUBE_VIDEO_STATS_BATCH_SIZE]
        try:
            res = session.get(videos_url, headers=headers, params={"key": YOUTUBE_API_KEY, "part": "statistics,snippet", "id": ",".join(batch), "maxResults": str(YOUTUBE_VIDEO_STATS_BATCH_SIZE)}, timeout=15)
            stats_calls += 1
            if res.status_code != 200:
                if res.status_code == 403 and "quotaExceeded" in res.text: quota_exhausted = True
                continue
            for item in res.json().get("items", []):
                vid = item.get("id")
                st = item.get("statistics", {}) or {}
                stats_by_id[vid] = {"views": st.get("viewCount"), "likes": st.get("likeCount"), "comments": st.get("commentCount")}
        except: pass
        time.sleep(0.15)
    for item in results:
        stats = stats_by_id.get(item.get("video_id"), {})
        item["text"] = (item["text"] + f" [views={stats.get('views','NA')}, likes={stats.get('likes','NA')}, comments={stats.get('comments','NA')}]")[:320]
    return results

APIFY_ACTOR_RUN_URL = "https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items"
def get_apify_monthly_results() -> int:
    month = get_usage_month()
    conn = get_db()
    row = conn.execute("SELECT COALESCE(SUM(calls), 0) AS total FROM api_usage WHERE usage_month = ? AND provider = 'apify_instagram'", (month,)).fetchone()
    conn.close()
    return int(row["total"] or 0)

def get_apify_daily_results() -> int:
    month = get_usage_month()
    day_endpoint = f"results:{get_today_iso()}"
    return get_api_calls("apify_instagram", day_endpoint, month)

def add_apify_result_usage(count: int) -> None:
    if count <= 0: return
    month = get_usage_month()
    now = get_market_now().isoformat()
    endpoint = f"results:{get_today_iso()}"
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            INSERT INTO api_usage(usage_month, provider, endpoint, calls, last_called_at)
            VALUES (?, 'apify_instagram', ?, ?, ?)
            ON CONFLICT(usage_month, provider, endpoint) DO UPDATE SET calls = calls + excluded.calls, last_called_at = excluded.last_called_at
        """, (month, endpoint, count, now))
        conn.commit()
    except: conn.rollback()
    finally: conn.close()

def get_today_apify_instagram_tags() -> List[str]:
    pool = interleave_hybrid_expand(INSTAGRAM_ROTATION, get_weekly_dynamic_pool())
    if not pool: return []
    idx = rotation_index(len(pool))
    return [pool[(idx + i) % len(pool)] for i in range(5)]

def fetch_instagram_apify() -> List[Dict]:
    if not APIFY_INSTAGRAM_ENABLED or not APIFY_TOKEN: return []
    used = get_apify_monthly_results()
    used_today = get_apify_daily_results()
    daily_remaining = APIFY_INSTAGRAM_DAILY_RESULT_LIMIT - used_today
    remaining = min(APIFY_INSTAGRAM_MONTHLY_RESULT_LIMIT - used, daily_remaining)
    if remaining <= 0: return []
    tags = get_today_apify_instagram_tags()
    results_limit = max(1, remaining // max(1, len(tags)))
    if remaining < 1: return []
    input_payload = {
        "directUrls": [f"https://www.instagram.com/explore/tags/{tag}/" for tag in tags],
        "resultsType": "posts", "resultsLimit": results_limit, "onlyPostsNewerThan": "3 days", "addParentData": True
    }
    headers = {"Authorization": f"Bearer {APIFY_TOKEN}", "Content-Type": "application/json"}
    try:
        res = apify_session.post(APIFY_ACTOR_RUN_URL, headers=headers, json=input_payload, params={"token": APIFY_TOKEN}, timeout=120)
        if not (200 <= res.status_code < 300): return []
        data = res.json()
        if not isinstance(data, list): return []
        results = []
        seen_ids = set()
        for item in data:
            if not isinstance(item, dict): continue
            shortcode = str(item.get("shortCode") or item.get("shortcode") or item.get("id") or "").strip()
            if shortcode and shortcode in seen_ids: continue
            if shortcode: seen_ids.add(shortcode)
            caption = str(item.get("caption") or "").strip()
            hashtags = item.get("hashtags") or []
            if isinstance(hashtags, list):
                hashtag_text = " ".join("#" + str(x).lstrip("#") for x in hashtags if str(x).strip())
            else:
                hashtag_text = str(hashtags)
            text = (caption + (" " + hashtag_text if hashtag_text else "")).strip()
            if len(text) <= 10: continue
            owner = str(item.get("ownerUsername") or "").strip()
            likes = item.get("likesCount")
            comments = item.get("commentsCount")
            views = item.get("videoViewCount")
            metrics = []
            if likes is not None: metrics.append(f"likes={likes}")
            if comments is not None: metrics.append(f"comments={comments}")
            if views is not None: metrics.append(f"views={views}")
            if owner: text = f"@{owner}: " + text
            if metrics: text += " [" + ", ".join(metrics) + "]"
            source_tag = ""
            parent = item.get("dataSource") or item.get("parentData")
            if isinstance(parent, dict): source_tag = str(parent.get("hashtag") or parent.get("tag") or "").strip().lstrip("#")
            if not source_tag and tags: source_tag = tags[0]
            results.append({"platform": "instagram", "query": "", "tag": source_tag, "region": "EU", "text": text.replace("\n", " ")[:260], "likes": likes, "comments": comments, "views": views, "instagram_id": shortcode})
        add_apify_result_usage(len(data))
        return results
    except: return []

# ============================================================
# 11. Raw signal 저장
# ============================================================
def save_raw_signals(signals: List[Dict]):
    if not signals: return
    conn = get_db()
    now = get_market_now().isoformat()
    signal_date = get_today_iso()
    for signal in signals:
        conn.execute("""
            INSERT INTO raw_signals (collected_at, signal_date, platform, query, tag, region, text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (now, signal_date, signal.get("platform", ""), signal.get("query", ""), signal.get("tag", ""), signal.get("region", ""), signal.get("text", "")))
    conn.commit(); conn.close()

# ============================================================
# 12. Keyword extraction
# ============================================================
def normalize_keyword(keyword: str) -> str:
    return keyword.lower().strip()

def count_keywords_in_text(text: str) -> Counter:
    text = text.lower()
    counts = Counter()
    for keyword in INGREDIENTS_VOCAB:
        pattern = r"(?<!\w)" + re.escape(keyword.lower()) + r"(?!\w)"
        if re.search(pattern, text): counts[normalize_keyword(keyword)] = 1
    return counts

def build_daily_keyword_counts(signals: List[Dict]) -> Dict[Tuple[str, str, str], int]:
    counts = Counter()
    for signal in signals:
        platform = signal["platform"]
        region = signal["region"]
        keyword_counts = count_keywords_in_text(signal["text"])
        for keyword in keyword_counts: counts[(keyword, platform, region)] += 1
    return counts

def save_keyword_counts(signal_date: str, counts: Dict[Tuple[str, str, str], int]):
    if not counts: return
    conn = get_db()
    for (keyword, platform, region), mentions in counts.items():
        conn.execute("""
            INSERT INTO keyword_daily (signal_date, keyword, platform, region, mentions)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(signal_date, keyword, platform, region) DO UPDATE SET mentions = excluded.mentions
        """, (signal_date, keyword, platform, region, mentions))
    conn.commit(); conn.close()

# ============================================================
# 13. Social Trend Calculation (V5 Ultimate Upgraded)
# ============================================================
def get_keyword_daily_history(keyword: str, end_date: str, days: int) -> List[Tuple[str, int]]:
    conn = get_db()
    rows = conn.execute("""
        SELECT signal_date, SUM(mentions) AS total_mentions FROM keyword_daily
        WHERE keyword = ? AND signal_date < ? AND signal_date >= date(?, ?)
        GROUP BY signal_date ORDER BY signal_date ASC
    """, (keyword, end_date, end_date, f"-{days} day")).fetchall()
    conn.close()
    return [(row["signal_date"], row["total_mentions"]) for row in rows]

def calculate_velocity(today_mentions: float, history: List[Tuple[str, int]]) -> Tuple[float, bool]:
    previous_values = [mentions for _, mentions in history if mentions > 0]
    if not previous_values: return 0.0, False
    avg_previous = sum(previous_values) / len(previous_values)
    if avg_previous <= 0: return 0.0, False
    return ((today_mentions - avg_previous) / avg_previous, True)

def calculate_persistence(history: List[Tuple[str, int]], window_days: int = 7) -> float:
    if not history: return 0.0
    active_days = sum(1 for _, mentions in history if mentions > 0)
    return min(active_days / window_days, 1.0)

def calculate_cross_platform(keyword: str, signal_date: str) -> float:
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT platform FROM keyword_daily WHERE keyword = ? AND signal_date = ? AND mentions > 0", (keyword, signal_date)).fetchall()
    conn.close()
    platforms = {row["platform"] for row in rows}
    return min(len(platforms) / 3.0, 1.0)

def calculate_regional_score(keyword: str, signal_date: str) -> float:
    conn = get_db()
    rows = conn.execute("SELECT DISTINCT region FROM keyword_daily WHERE keyword = ? AND signal_date = ? AND mentions > 0", (keyword, signal_date)).fetchall()
    conn.close()
    regions = {row["region"] for row in rows}
    return min(len(regions) / 2.0, 1.0)

def calculate_platform_normalized_score(keyword: str, signal_date: str) -> float:
    conn = get_db()
    rows = conn.execute("""
        SELECT platform, SUM(CASE WHEN keyword = ? THEN mentions ELSE 0 END) AS kw_mentions, SUM(mentions) AS platform_mentions
        FROM keyword_daily WHERE signal_date = ? GROUP BY platform
    """, (keyword, signal_date)).fetchall()
    conn.close()
    rates = []
    for row in rows:
        total = row["platform_mentions"] or 0
        kw = row["kw_mentions"] or 0
        if total > 0: rates.append(min(kw / total, 1.0))
    if not rates: return 0.0
    return sum(rates) / len(rates)

def calculate_generic_penalty(keyword: str) -> float:
    generic = {"skincare", "serum", "cream", "beauty", "sunscreen", "cleanser", "toner", "moisturizer", "mask", "cosmetics", "kbeauty", "skin barrier"}
    return 0.72 if keyword.lower() in generic else 1.0

def calculate_trend_status(velocity: float, has_history: bool, persistence: float) -> str:
    if not has_history: return "INSUFFICIENT DATA"
    if velocity >= 0.50: return "RISING"
    if velocity >= 0.10: return "EMERGING"
    if velocity <= -0.30: return "DECLINING"
    if persistence >= 0.40: return "ESTABLISHED"
    return "EMERGING"

# V5 Advanced Metrics Helpers
def _ema(vals, alpha):
    if not vals: return 0.0
    e = vals[0]
    for v in vals[1:]: e = alpha*v + (1-alpha)*e
    return e

def _flow_metrics(series):
    vals = [m for _,m in series]; lv = [math.log1p(v) for v in vals]
    ema7 = _ema(lv[-7:], 0.35) if len(lv) >= 7 else _ema(lv, 0.35)
    ema28 = _ema(lv, 0.15)
    hist = lv[:-1]
    if hist:
        mean = sum(hist)/len(hist); var = sum((v-mean)**2 for v in hist)/len(hist)
        z = (lv[-1]-mean)/(math.sqrt(var)+1e-6)
    else: z = 0.0
    return {"today":vals[-1] if vals else 0, "ema7":ema7, "ema28":ema28, "momentum":ema7-ema28, "z":z, "a7":sum(1 for v in vals[-7:] if v>0), "a14":sum(1 for v in vals[-14:] if v>0), "a28":sum(1 for v in vals if v>0)}

def _validation_score(platforms, has_commercial, a7):
    s = 0.0
    if "youtube" in platforms and "amazon" in platforms: s += 0.45
    elif "amazon" in platforms: s += 0.25
    elif "youtube" in platforms: s += 0.20
    if "tiktok" in platforms and ("instagram" in platforms or "youtube" in platforms): s += 0.20
    if has_commercial: s += 0.20
    if a7 >= 3: s += 0.15
    return min(s, 1.0)

def _observation_confidence(platforms, a14):
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

def calculate_weighted_volume_score(pm):
    if not pm: return 0.0
    ws = sum(m*_platform_weight(p) for p,m in pm.items())
    tw = sum(_platform_weight(p) for p in pm)
    if tw <= 0: return 0.0
    return min(math.log1p(ws/tw)/math.log1p(30), 1.0)

def calculate_trend_scores(signal_date: str, daily_counts: Dict[Tuple[str, str, str], int]) -> List[Dict]:
    keywords = {kw for kw, _, _ in daily_counts.keys()}
    
    # Load 28-day series map for EMA/Z-score
    conn = get_db()
    rows = conn.execute("""
        SELECT keyword, signal_date, SUM(mentions) AS m FROM keyword_daily
        WHERE signal_date <= ? AND signal_date >= date(?, '-28 day')
        GROUP BY keyword, signal_date
    """, (signal_date, signal_date)).fetchall()
    
    plat_rows = conn.execute("""
        SELECT keyword, GROUP_CONCAT(DISTINCT platform) AS p FROM keyword_daily
        WHERE signal_date = ? AND mentions > 0 GROUP BY keyword
    """, (signal_date,)).fetchall()
    kw_plats = {r["keyword"]: {x for x in r["p"].split(",") if x} for r in plat_rows}
    
    comm_rows = conn.execute("SELECT DISTINCT keyword FROM google_signals WHERE signal_date = ? AND intent = 'commercial'", (signal_date,)).fetchall()
    conn.close()
    comm_kws = {r["keyword"] for r in comm_rows}
    
    sm = {}
    for r in rows: sm.setdefault(r["keyword"], {})[r["signal_date"]] = r["m"]
    
    pm_today = {}
    for (kw, plat, _), m in daily_counts.items():
        pm_today.setdefault(kw, {})[plat] = pm_today.get(kw, {}).get(plat, 0) + m
        
    results = []
    end_date = datetime.date.fromisoformat(signal_date)
    
    for keyword in keywords:
        today_mentions = sum(pm_today.get(keyword, {}).values())
        
        history = get_keyword_daily_history(keyword, signal_date, 7)
        velocity, has_history = calculate_velocity(today_mentions, history)
        persistence = calculate_persistence(history, 7)
        cross_platform = calculate_cross_platform(keyword, signal_date)
        regional = calculate_regional_score(keyword, signal_date)
        platform_normalized = calculate_platform_normalized_score(keyword, signal_date)
        
        bd = sm.get(keyword, {})
        series = [
            ((end_date - datetime.timedelta(days=i)).isoformat(), bd.get((end_date - datetime.timedelta(days=i)).isoformat(), 0))
            for i in range(27, -1, -1)
        ]
        fm = _flow_metrics(series)
        
        plats = kw_plats.get(keyword, set())
        val = _validation_score(plats, keyword in comm_kws, fm["a7"])
        obs_conf = _observation_confidence(plats, fm["a14"])
        vol = calculate_weighted_volume_score(pm_today.get(keyword, {}))
        
        vel_score = (max(-1.0, min(velocity, 1.0)) + 1.0) / 2.0 if has_history else 0.5
        mom_score = max(0.0, min(1.0, 0.5 + fm["momentum"]/2.0))
        pers14 = min(fm["a14"] / 7.0, 1.0)
        
        base = (vol*0.15 + vel_score*0.20 + persistence*0.10 + pers14*0.15 + cross_platform*0.20 + regional*0.05 + platform_normalized*0.10 + mom_score*0.05) * 100
        trend = base * calculate_generic_penalty(keyword) * obs_conf * (1.0 + 0.25*val)
        lifecycle = _classify_lifecycle(fm, plats, val)
        flow_sc = trend * (0.5 + 0.5*pers14)
        
        results.append({
            "keyword": keyword, "today_mentions": today_mentions, "velocity": velocity,
            "has_history": has_history, "status": calculate_trend_status(velocity, has_history, persistence),
            "lifecycle": lifecycle, "z_score": fm["z"], "active_days_14": fm["a14"], "validation_score": val,
            "volume_score": vol * 100, "velocity_score": vel_score * 100, "persistence_score": persistence * 100,
            "cross_platform_score": cross_platform * 100, "regional_score": regional * 100,
            "platform_normalized_score": platform_normalized * 100, "flow_score": flow_sc, "trend_score": trend
        })
    results.sort(key=lambda x: x["trend_score"], reverse=True)
    return results

def save_trend_scores(signal_date: str, scores: List[Dict]):
    conn = get_db()
    for item in scores:
        conn.execute("""
            INSERT INTO trend_scores (
                signal_date, keyword, volume_score, velocity_score, persistence_score, cross_platform_score,
                regional_score, platform_normalized_score, trend_score, flow_score, z_score,
                active_days_14, validation_score, lifecycle
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(signal_date, keyword) DO UPDATE SET
                volume_score = excluded.volume_score, velocity_score = excluded.velocity_score,
                persistence_score = excluded.persistence_score, cross_platform_score = excluded.cross_platform_score,
                regional_score = excluded.regional_score, platform_normalized_score = excluded.platform_normalized_score,
                trend_score = excluded.trend_score, flow_score = excluded.flow_score, z_score = excluded.z_score,
                active_days_14 = excluded.active_days_14, validation_score = excluded.validation_score, lifecycle = excluded.lifecycle
        """, (
            signal_date, item["keyword"], item["volume_score"], item["velocity_score"], item["persistence_score"],
            item["cross_platform_score"], item["regional_score"], item.get("platform_normalized_score", 0),
            item["trend_score"], item.get("flow_score", 0), item.get("z_score", 0), item.get("active_days_14", 0),
            item.get("validation_score", 0), item.get("lifecycle", "")
        ))
    conn.commit(); conn.close()

# ============================================================
# 14. Google summary
# ============================================================
def get_google_summary(signal_date: str, regions: List[str]) -> str:
    conn = get_db()
    lines = []
    for region in regions:
        rows = conn.execute("""
            SELECT keyword, intent, interest_score, rising_score, source FROM google_signals
            WHERE signal_date = ? AND region = ? AND (query_type = 'related_candidate' OR query_type = 'interest')
            ORDER BY CASE WHEN rising_score IS NULL THEN -999999 ELSE rising_score END DESC,
                     CASE WHEN interest_score IS NULL THEN -999999 ELSE interest_score END DESC LIMIT 20
        """, (signal_date, region)).fetchall()
        lines.append(f"[Google {region}]")
        if not rows:
            lines.append("No Google beauty discovery data today.")
            continue
        seen = set()
        for row in rows:
            keyword = row["keyword"]
            if keyword in seen: continue
            seen.add(keyword)
            interest = f"{row['interest_score']:.0f}" if row["interest_score"] is not None else "NA"
            rising = f"{row['rising_score']:+.1f}%" if row["rising_score"] is not None else "NA"
            lines.append(f"- {keyword} | intent={row['intent']} | interest={interest} | rising={rising} | source={row['source']}")
    conn.close()
    return "\n".join(lines)

def get_google_candidate_list(signal_date: str, limit: int = 30) -> List[str]:
    conn = get_db()
    rows = conn.execute("""
        SELECT keyword FROM google_signals WHERE signal_date = ?
        ORDER BY CASE WHEN rising_score IS NULL THEN 0 ELSE rising_score END DESC,
                 CASE WHEN interest_score IS NULL THEN 0 ELSE interest_score END DESC LIMIT ?
    """, (signal_date, limit)).fetchall()
    conn.close()
    output = []
    seen = set()
    for row in rows:
        kw = row["keyword"]
        if kw not in seen:
            seen.add(kw)
            output.append(kw)
    return output

# ============================================================
# 15. Trend Summary & Theme Rollup
# ============================================================
def get_keyword_platforms(keyword: str, signal_date: str) -> str:
    conn = get_db()
    rows = conn.execute("""
        SELECT platform, SUM(mentions) AS m FROM keyword_daily
        WHERE keyword = ? AND signal_date = ? AND mentions > 0 GROUP BY platform ORDER BY m DESC
    """, (keyword, signal_date)).fetchall()
    conn.close()
    if not rows: return "none"
    return ", ".join(f"{r['platform']}({r['m']})" for r in rows)

def build_trend_summary(scores: List[Dict], signal_date: str = None) -> str:
    if not scores: return "No quantitative social trend score available today."
    lines = []
    for rank, item in enumerate(scores[:10], start=1):
        velocity_text = f"{item['velocity'] * 100:+.1f}%" if item["has_history"] else "INSUFFICIENT_HISTORY"
        platforms_text = "unknown"
        if signal_date: platforms_text = get_keyword_platforms(item["keyword"], signal_date)
        lc = lifecycle_label(item.get("lifecycle", ""))
        lines.append(
            f"{rank}. {item['keyword']} | lifecycle={lc} | mentions={item['today_mentions']} | "
            f"platforms=[{platforms_text}] | velocity={velocity_text} | active14={item.get('active_days_14',0)}d | "
            f"validation={item.get('validation_score',0):.2f} | z={item.get('z_score',0):+.1f} | "
            f"cross={item['cross_platform_score']:.0f}/100 | TREND_SCORE={item['trend_score']:.1f}/100"
        )
    return "\n".join(lines)

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
        if any(t in kw for t in terms): return theme
    return "other"

def build_theme_rollup(date_list: List[str]) -> str:
    if not date_list: return "No theme data."
    conn = get_db()
    placeholders = ",".join("?" for _ in date_list)
    rows = conn.execute(f"""
        SELECT keyword, SUM(trend_score) AS ts, COUNT(DISTINCT signal_date) AS d
        FROM trend_scores WHERE signal_date IN ({placeholders}) GROUP BY keyword
    """, date_list).fetchall()
    conn.close()
    themes = {}
    for r in rows:
        t = keyword_theme(r["keyword"])
        if t == "other": continue
        agg = themes.setdefault(t, {"m": 0, "kws": []})
        agg["m"] += r["ts"]
        agg["kws"].append((r["keyword"], r["ts"], r["d"]))
    lines = []
    for t, a in sorted(themes.items(), key=lambda x: -x[1]["m"]):
        top = sorted(a["kws"], key=lambda x: -x[1])[:5]
        lines.append(f"- {t}: 총 flow={a['m']:.1f} | 대표: " + ", ".join(f"{k}({m:.1f}/{d}d)" for k,m,d in top))
    return "\n".join(lines) if lines else "No distinct theme data."

# ============================================================
# 16. Gemini (Upgraded Prompts)
# ============================================================
def call_gemini_api(prompt: str) -> str:
    if not GEMINI_API_KEY: raise RuntimeError("GEMINI_API_KEY is missing.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192}}
    res = session.post(url, headers=headers, json=payload, timeout=60)
    if res.status_code == 404 and GEMINI_MODEL != GEMINI_FALLBACK_MODEL:
        fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_FALLBACK_MODEL}:generateContent"
        res = session.post(fallback_url, headers=headers, json=payload, timeout=60)
    if res.status_code != 200: raise RuntimeError(f"Gemini API failed with status {res.status_code}")
    data = res.json()
    candidates = data.get("candidates", [])
    if not candidates: raise RuntimeError("Gemini API returned no candidates.")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts: raise RuntimeError("Gemini API response parts empty.")
    report_text = parts[0].get("text", "").strip()
    if not report_text: raise RuntimeError("Gemini returned empty report.")
    return report_text

LIFECYCLE_GLOSSARY = """INTUITIVE LIFECYCLE GLOSSARY (use these simple terms, not internal codes):
early signal = 초기 신호 = إشارة مبكرة
rising = 상승 = صاعد
spreading = 확산 = منتشر
steady = 꾸준함 = مستقر
cooling = 둔화 = يتراجع
possible noise = 노이즈 가능성 = ضوضاء محتملة
no recent signal = 최근 신호 없음 = لا توجد إشارة حديثة
SHORT KEYWORD RULE: Short keywords have broader recall. If a short keyword appears only on one platform with no confirmation, treat it as "possible noise" or "watch".
When describing lifecycle, prefer intuitive words. Do not output raw internal codes such as NOISE_CANDIDATE or SCALING."""

def generate_gemini_report(google_summary: str, google_candidates: List[str], social_data: List[Dict], freq_summary: str, trend_summary: str) -> str:
    social_lines = []
    for item in social_data:
        platform = item.get("platform", "")
        query = item.get("query", "")
        tag = item.get("tag", "")
        region = item.get("region", "")
        text = item.get("text", "")
        source = platform
        if query: source += f"/{query}"
        if tag: source += f"/#{tag}"
        social_lines.append(f"[{source} | {region}] {text}")
    social_text = "\n".join(social_lines)
    social_count = len(social_data)
    google_candidates_text = ", ".join(google_candidates) if google_candidates else "NONE"
    if social_count == 0 and not google_summary.strip():
        data_status = "CRITICAL DATA STATUS: Today's live social and Google beauty discovery data are unavailable. Do not fabricate a measured trend ranking."
    else:
        data_status = f"DATA STATUS: Valid social samples: {social_count}. Google discovery is independent from social sampling. Use measured quantitative signals first. Do not turn autocomplete candidates into search-volume claims."
    prompt = f"""
You are a market-intelligence analyst tracking cosmetics and skincare consumer interest in Western Europe. You are NOT analyzing this from a "K-Beauty" angle; you simply track which ingredients, product formats, and skin concerns these consumers are actually interested in right now.
Generate a DAILY WESTERN-EUROPE COSMETICS & SKINCARE TREND REPORT.
{data_status}
IMPORTANT DATA MODEL: TikTok = early viral. Instagram = secondary confirmation. Amazon = purchase-stage. Google = independent search. YouTube = longer-form interest. Single-platform weak signals are not confirmed trends.
{LIFECYCLE_GLOSSARY}
GOOGLE INDEPENDENT DISCOVERY: {google_summary}
GOOGLE CANDIDATES: {google_candidates_text}
SOCIAL QUANTITATIVE TREND SCORES: {trend_summary}
KNOWN VOCABULARY FREQUENCY: {freq_summary}
LIVE SOCIAL SAMPLES: {social_text}

ANALYSIS TASK
Internally grade each major signal with a star rating (do not print the tier name):
★★★ : cross-platform social + independent Google and/or Amazon support
★★  : only one strong source
★   : weak / single / flat signal
CRITICAL RULES: Star rating alone is never enough. Every TOP signal must include an explicit data-analysis sentence naming the platforms where it appeared. Keep language SIMPLE and DIRECT. Do NOT use technical jargon like "velocity", "persistence", "acceleration" in the output text. Describe speed and duration naturally.
STRICT LANGUAGE & ORDER RULES: THREE sections separated by ===SPLIT_SECTION===. Order: KOREAN, ARABIC, ENGLISH.
--- SECTION 1 ---
Title: 🌐 글로벌 화장품 & 스킨케어 시장 데일리 트렌드 리포트
📊 오늘의 데이터 분석 (TOP 5): Title + star rating on the same line. Right under it: plain-language sentence stating WHERE it was mentioned, how fast it's showing up, and how many days it's kept appearing.
🔇 노이즈 구분
📌 짧은 시사점 (2-3문장)
===SPLIT_SECTION===
--- SECTION 2 ---
Title: 🌐 التقرير اليومي العالمي لاتجاهات مستحضرات التجميل والعناية بالبشرة
📊 تحليل بيانات اليوم (أفضل 5)
🔇 تمييز الضوضاء
📌 ملاحظات قصيرة
===SPLIT_SECTION===
--- SECTION 3 ---
Title: 🌐 GLOBAL COSMETICS & SKINCARE MARKET DAILY TREND REPORT
📊 TODAY'S DATA ANALYSIS (TOP 5)
🔇 NOISE CHECK
📌 SHORT IMPLICATIONS"""
    return call_gemini_api(prompt)

# ============================================================
# 16b. Weekly Rollup
# ============================================================
WEEKLY_SUMMARY_WEEKDAY = 5
FORCE_ROLLUPS = os.getenv("FORCE_ROLLUPS", "").strip().lower() in ("1", "true", "yes")

def is_weekly_summary_day() -> bool:
    if FORCE_ROLLUPS: return True
    return get_market_now().date().weekday() == WEEKLY_SUMMARY_WEEKDAY

def is_monthly_summary_day() -> bool:
    if FORCE_ROLLUPS: return True
    today = get_market_now().date()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return today.day == last_day

def get_past_month_dates(signal_date: str) -> List[str]:
    today = datetime.date.fromisoformat(signal_date)
    first_day = today.replace(day=1)
    days_in_month = (today - first_day).days + 1
    return [(first_day + datetime.timedelta(days=i)).isoformat() for i in range(days_in_month)]

def get_past_weekday_dates(signal_date: str) -> List[str]:
    today = datetime.date.fromisoformat(signal_date)
    monday = today - datetime.timedelta(days=today.weekday())
    return [(monday + datetime.timedelta(days=i)).isoformat() for i in range(5)]

def get_preceding_dates(date_list: List[str], count: int) -> List[str]:
    if not date_list: return []
    conn = get_db()
    earliest = min(date_list)
    rows = conn.execute("SELECT DISTINCT signal_date FROM trend_scores WHERE signal_date < ? ORDER BY signal_date DESC LIMIT ?", (earliest, count)).fetchall()
    conn.close()
    return sorted(row["signal_date"] for row in rows)

def build_period_delta(current_dates: List[str], previous_dates: List[str]) -> str:
    if not previous_dates: return "No previous-period data available yet for comparison."
    conn = get_db()
    cur_ph = ",".join("?" for _ in current_dates)
    prev_ph = ",".join("?" for _ in previous_dates)
    cur_score_rows = conn.execute(f"SELECT keyword, SUM(trend_score) AS total_score FROM trend_scores WHERE signal_date IN ({cur_ph}) GROUP BY keyword", current_dates).fetchall()
    prev_score_rows = conn.execute(f"SELECT keyword, SUM(trend_score) AS total_score FROM trend_scores WHERE signal_date IN ({prev_ph}) GROUP BY keyword", previous_dates).fetchall()
    conn.close()
    cur_scores = {r["keyword"]: r["total_score"] for r in cur_score_rows}
    prev_scores = {r["keyword"]: r["total_score"] for r in prev_score_rows}
    new_entries, rising, cooling = [], [], []
    for kw in set(cur_scores) | set(prev_scores):
        cur_s = cur_scores.get(kw, 0.0)
        prev_s = prev_scores.get(kw, 0.0)
        if prev_s == 0 and cur_s > 0: new_entries.append((kw, cur_s))
        elif prev_s > 0 and cur_s == 0: cooling.append((kw, prev_s, 0.0))
        elif prev_s > 0 and cur_s >= prev_s * 1.5: rising.append((kw, prev_s, cur_s))
        elif prev_s > 0 and cur_s <= prev_s * 0.5: cooling.append((kw, prev_s, cur_s))
    new_entries.sort(key=lambda x: -x[1])
    rising.sort(key=lambda x: -(x[2] - x[1]))
    cooling.sort(key=lambda x: (x[1] - x[2]) * -1 if x[2] else -x[1])
    lines = ["신규 진입:"] + [f"- {kw}: {s:.1f}" for kw, s in new_entries[:15]] or ["- none"]
    lines.append("")
    lines.append("급상승 (1.5배 이상):")
    lines += [f"- {kw}: {p:.1f} -> {c:.1f}" for kw, p, c in rising[:15]] or ["- none"]
    lines.append("")
    lines.append("냉각/이탈 (절반 이하 또는 사라짐):")
    lines += [f"- {kw}: {p:.1f} -> {c:.1f}" for kw, p, c in cooling[:15]] or ["- none"]
    return "\n".join(lines)

def build_weekly_rollup(date_list: List[str]) -> str:
    if not date_list: return "No data."
    conn = get_db()
    placeholders = ",".join("?" for _ in date_list)
    keyword_rows = conn.execute(f"""
        SELECT keyword, SUM(trend_score) AS total_score, AVG(trend_score) AS avg_score, MAX(trend_score) AS peak_score, COUNT(DISTINCT signal_date) AS active_days
        FROM trend_scores WHERE signal_date IN ({placeholders}) GROUP BY keyword ORDER BY total_score DESC LIMIT 25
    """, date_list).fetchall()
    conn.close()
    keyword_lines = []
    for row in keyword_rows:
        keyword_lines.append(f"- {row['keyword']}: 평균={row['avg_score']:.1f}, 최고={row['peak_score']:.1f}, 지속일={row['active_days']}/5일")
    return "\n".join(keyword_lines) if keyword_lines else "No weekly keyword data."

def generate_weekly_summary_report(date_list: List[str], keyword_rollup: str, delta_text: str) -> str:
    theme_rollup = build_theme_rollup(date_list)
    prompt = f"""
You are a market-intelligence analyst tracking cosmetics and skincare consumer interest in Western Europe. Focus on TRENDS and FLOWS.
Generate a WEEKLY WESTERN-EUROPE COSMETICS & SKINCARE TREND & FLOW ROLLUP covering {date_list[0]} to {date_list[-1]}.
WEEKLY KEYWORD RANKING: {keyword_rollup}
THEME ROLLUP (Ingredients/Concerns grouped): {theme_rollup}
WEEK-OVER-WEEK DELTA: {delta_text}
Use the DELTA block as ground truth. Tag statuses: 🆕 신규 / 📈 상승 / ✅ 꾸준 / 📉 냉각. Group related keywords into 2-4 THEMES.
THREE sections separated by ===SPLIT_SECTION===. KOREAN, ARABIC, ENGLISH.
--- SECTION 1 ---
Title: 📅 주간 화장품 & 스킨케어 트렌드 요약 ({date_list[0]} ~ {date_list[-1]})
🔄 이번 주 핵심 변화 | 🧩 테마로 보기 | 🏆 가장 꾸준했던 TOP 5 | ⚠️ 노이즈 주의 | 📌 다음 주 추적 포인트
===SPLIT_SECTION===
--- SECTION 2 ---
Title: 📅 ملخص أسبوعي لاتجاهات مستحضرات التجميل والعناية بالبشرة
🔄 أهم التغييرات | 🧩 التجميع حسب الثيمات | 🏆 أكثر 5 اتجاهات ثباتاً | ⚠️ ضوضاء | 📌 نقاط المتابعة
===SPLIT_SECTION===
--- SECTION 3 ---
Title: 📅 WEEKLY COSMETICS & SKINCARE TREND ROLLUP ({date_list[0]} ~ {date_list[-1]})
🔄 KEY CHANGES | 🧩 THEMES | 🏆 TOP 5 CONSISTENT | ⚠️ NOISE | 📌 NEXT-WEEK TRACKING"""
    return call_gemini_api(prompt)

# ============================================================
# 16c. Monthly Rollup
# ============================================================
def build_monthly_rollup(date_list: List[str]) -> str:
    if not date_list: return "No data."
    conn = get_db()
    placeholders = ",".join("?" for _ in date_list)
    total_days = len(date_list)
    keyword_rows = conn.execute(f"""
        SELECT keyword, SUM(trend_score) AS total_score, AVG(trend_score) AS avg_score, MAX(trend_score) AS peak_score, COUNT(DISTINCT signal_date) AS active_days
        FROM trend_scores WHERE signal_date IN ({placeholders}) GROUP BY keyword ORDER BY total_score DESC LIMIT 30
    """, date_list).fetchall()
    conn.close()
    keyword_lines = []
    for row in keyword_rows:
        keyword_lines.append(f"- {row['keyword']}: 평균={row['avg_score']:.1f}, 최고={row['peak_score']:.1f}, 지속일={row['active_days']}/{total_days}일")
    return "\n".join(keyword_lines) if keyword_lines else "No monthly keyword data."

def generate_monthly_summary_report(date_list: List[str], keyword_rollup: str, delta_text: str) -> str:
    total_days = len(date_list)
    theme_rollup = build_theme_rollup(date_list)
    prompt = f"""
You are a market-intelligence analyst tracking cosmetics and skincare consumer interest in Western Europe. Focus on TRENDS and FLOWS.
Generate a MONTHLY WESTERN-EUROPE COSMETICS & SKINCARE TREND & FLOW ROLLUP covering {date_list[0]} to {date_list[-1]} ({total_days} days).
MONTHLY KEYWORD RANKING: {keyword_rollup}
THEME ROLLUP: {theme_rollup}
MONTH-OVER-MONTH DELTA: {delta_text}
Use the DELTA block as ground truth. Tag statuses: 🆕 신규 / 📈 상승 / ✅ 꾸준 / 📉 냉각. Group into 2-4 THEMES.
THREE sections separated by ===SPLIT_SECTION===. KOREAN, ARABIC, ENGLISH.
--- SECTION 1 ---
Title: 🗓️ 월간 화장품 & 스킨케어 트렌드 요약 ({date_list[0]} ~ {date_list[-1]})
🔄 이번 달 핵심 변화 | 🧩 테마로 보기 | 🏆 TOP 5 지속 트렌드 (★★★/★★/★) | 📉 노이즈 | 📌 다음 달 추적 포인트
===SPLIT_SECTION===
--- SECTION 2 ---
Title: 🗓️ ملخص شهري لاتجاهات مستحضرات التجميل والعناية بالبشرة
🔄 أهم التغييرات | 🧩 التجميع حسب الثيمات | 🏆 أفضل 5 اتجاهات مستمرة | 📉 ضوضاء | 📌 نقاط المتابعة
===SPLIT_SECTION===
--- SECTION 3 ---
Title: 🗓️ MONTHLY COSMETICS & SKINCARE TREND ROLLUP ({date_list[0]} ~ {date_list[-1]})
🔄 KEY CHANGES | 🧩 THEMES | 🏆 TOP 5 PERSISTENT | 📉 NOISE | 📌 NEXT-MONTH TRACKING"""
    return call_gemini_api(prompt)

# ============================================================
# 17. Telegram
# ============================================================
def send_telegram_message(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    max_length = 4000
    chunks = [message[i:i + max_length] for i in range(0, len(message), max_length)]
    for chunk in chunks:
        try:
            res = session.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk}, timeout=15)
            if res.status_code != 200: logging.warning("Telegram failed HTTP %s", res.status_code)
        except Exception as e: logging.error("Telegram notification failed: %s", e)

# ============================================================
# 18. Main Pipeline
# ============================================================
def main():
    logging.info("=== Daily Cosmetics Trend Bot Started ===")
    try:
        init_database()
        signal_date = get_today_iso()
        regions = ["NL", "DE"]
        
        google_data = collect_google_independent_signals(signal_date, regions)
        google_nl_rss = fetch_google_daily_rss("NL", 15)
        google_de_rss = fetch_google_daily_rss("DE", 15)
        save_google_daily_rss(signal_date, "NL", google_nl_rss)
        save_google_daily_rss(signal_date, "DE", google_de_rss)
        
        tiktok_signals = fetch_tiktok_captions()
        amazon_signals = fetch_amazon_products()
        instagram_signals = fetch_instagram_apify()
        youtube_signals = fetch_youtube_trends()
        all_signals = tiktok_signals + amazon_signals + instagram_signals + youtube_signals
        save_raw_signals(all_signals)
        
        daily_counts = build_daily_keyword_counts(all_signals)
        save_keyword_counts(signal_date, daily_counts)
        
        trend_scores = calculate_trend_scores(signal_date, daily_counts)
        save_trend_scores(signal_date, trend_scores)
        trend_summary_str = build_trend_summary(trend_scores, signal_date=signal_date)
        
        freq_lines = [f"- {item['keyword']}: {item['today_mentions']} mentions" for item in trend_scores[:20]]
        freq_summary_str = "\n".join(freq_lines) if freq_lines else "No vocabulary frequency data today."
        
        google_summary = get_google_summary(signal_date, regions)
        google_candidates = get_google_candidate_list(signal_date, 30)
        
        report = generate_gemini_report(google_summary, google_candidates, all_signals, freq_summary_str, trend_summary_str)
        sections = [section.strip() for section in report.split("===SPLIT_SECTION===") if section.strip()]
        for index, section in enumerate(sections):
            send_telegram_message(section)
            
        if is_weekly_summary_day():
            try:
                week_dates = get_past_weekday_dates(signal_date)
                keyword_rollup = build_weekly_rollup(week_dates)
                prev_week_dates = get_preceding_dates(week_dates, len(week_dates))
                weekly_delta = build_period_delta(week_dates, prev_week_dates)
                weekly_report = generate_weekly_summary_report(week_dates, keyword_rollup, weekly_delta)
                for section in [s.strip() for s in weekly_report.split("===SPLIT_SECTION===") if s.strip()]:
                    send_telegram_message(section)
            except Exception as e:
                send_telegram_error(f"Weekly rollup failed: {str(e)}")
                
        if is_monthly_summary_day():
            try:
                month_dates = get_past_month_dates(signal_date)
                keyword_rollup = build_monthly_rollup(month_dates)
                prev_month_dates = get_preceding_dates(month_dates, len(month_dates))
                monthly_delta = build_period_delta(month_dates, prev_month_dates)
                monthly_report = generate_monthly_summary_report(month_dates, keyword_rollup, monthly_delta)
                for section in [s.strip() for s in monthly_report.split("===SPLIT_SECTION===") if s.strip()]:
                    send_telegram_message(section)
            except Exception as e:
                send_telegram_error(f"Monthly rollup failed: {str(e)}")
                
        logging.info("Monthly API quota snapshot: %s", get_monthly_quota_snapshot())
        logging.info("=== Daily Cosmetics Trend Bot Completed Successfully ===")
    except Exception as e:
        err_msg = f"Pipeline execution failed: {str(e)}"
        logging.error(err_msg, exc_info=True)
        send_telegram_error(err_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
