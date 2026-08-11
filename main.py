import os
import sys
import re
import json
import sqlite3
import logging
import datetime
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


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# 무료 RapidAPI 제한
TIKTOK_DAILY_LIMIT = 3
TIKTOK_QUERY_COUNT = 50  # 요청 1회당 가져오는 최대 영상 수 (쿼터는 호출 수 기준이므로 부담 없음)

# instagram-scraper2 (JoTucker) - 신규 대체 API. 파라미터 확정 후 아래 함수에서 사용.
INSTAGRAM_SCRAPER_ENABLED = True
INSTAGRAM_SCRAPER_DAILY_LIMIT = 10
INSTAGRAM_SCRAPER_QUERY_COUNT = 50

# Amazon은 "구매 전환 신호"로 활용한다 (SNS의 화제성 신호와 상호보완).
AMAZON_DAILY_LIMIT = 3
AMAZON_QUERY_COUNT = 50  # /search 응답에서 최대로 취할 상품 수 (실제 페이지당 반환 수는 API 쪽 상한을 따름)

AMAZON_QUERY_ROTATION = [
    # Category / product discovery
    ["skincare", "kbeauty skincare", "facial skincare"],
    ["face serum", "ampoule", "essence"],
    ["moisturizer", "face cream", "barrier repair cream"],
    ["cleanser", "toner", "face mask"],
    ["sunscreen face", "sun stick", "spf 50 sunscreen"],
    ["eye cream", "anti aging cream", "brightening cream"],
    # Ingredients
    ["retinol serum", "retinal serum", "bakuchiol serum"],
    ["niacinamide serum", "vitamin c serum", "tranexamic acid serum"],
    ["pdrn serum", "pdrn skincare", "polynucleotide serum"],
    ["peptide serum", "collagen serum", "exosome skincare"],
    ["ceramide cream", "ectoin skincare", "skin barrier serum"],
    ["azelaic acid", "salicylic acid serum", "snail mucin"],
    ["propolis skincare", "centella cica", "spicule serum"],
    ["hyaluronic acid serum", "panthenol cream", "fermented skincare"],
    # Skin concerns
    ["acne skincare", "blemish serum", "pore care"],
    ["hyperpigmentation", "dark spot serum", "brightening serum"],
    ["sensitive skin", "redness skincare", "rosacea skincare"],
    ["dry skin", "dehydrated skin", "hydrating serum"],
    ["anti aging skincare", "fine lines serum", "firming serum"],
    # Trend / commercial intent
    ["glass skin", "skin barrier", "barrier repair"],
    ["skin cycling", "skin flooding", "slugging skincare"],
    ["viral skincare", "trending skincare", "best skincare"],
    ["best serum", "best moisturizer", "best sunscreen"],
    ["korean skincare set", "kbeauty products", "korean serum"],
    # Europe-oriented demand
    ["skincare germany", "kbeauty germany", "sunscreen germany"],
    ["skincare europe", "kbeauty europe", "anti aging europe"],
]

# TikTok은 매일 3개만 사용하고, 날짜를 기준으로 검색군을 회전한다.
TIKTOK_QUERY_ROTATION = [
    ["skincare", "skincare routine", "beauty skincare"],
    ["kbeauty", "korean skincare", "kbeauty routine"],
    ["skincare ingredient", "viral skincare ingredient", "beauty ingredient"],
    ["serum trend", "viral serum", "best serum"],
    ["skin barrier", "barrier repair", "sensitive skin skincare"],
    ["retinol skincare", "retinal skincare", "anti aging skincare"],
    ["pdrn skincare", "polynucleotide skincare", "exosome skincare"],
    ["peptide skincare", "collagen skincare", "firming skincare"],
    ["niacinamide skincare", "vitamin c skincare", "brightening skincare"],
    ["acne skincare", "blemish skincare", "pore care"],
    ["hyperpigmentation", "dark spot skincare", "brightening serum"],
    ["dry skin", "dehydrated skin", "hydrating skincare"],
    ["sunscreen", "sun stick", "spf skincare"],
    ["cica skincare", "centella skincare", "snail mucin"],
    ["spicule skincare", "spicule serum", "skin booster"],
    ["azelaic acid skincare", "salicylic acid skincare", "aha bha skincare"],
    ["glass skin", "skin flooding", "skin cycling"],
    ["slugging skincare", "skinimalism", "glowy skin"],
    ["viral beauty", "trending beauty", "new skincare"],
    ["skincare europe", "kbeauty europe", "beauty trends europe"],
    ["skincare germany", "kbeauty germany", "beauty germany"],
]

# Instagram은 하루 1개이므로 2주 rotation으로 넓게 탐색한다.
INSTAGRAM_ROTATION = [
    "skincare", "kbeauty", "koreanskincare", "beauty",
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
    "viralbeauty", "viralskincare", "kbeautyproducts",
]

# Google은 SNS와 독립적으로 탐색한다.
# 너무 많은 API 요청을 만들지 않도록 날짜별 batch를 회전한다.
GOOGLE_SEED_GROUPS = {
    "category": [
        "skincare", "skin care", "kbeauty", "k beauty", "cosmetics",
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

# 기존 vocabulary + Google에서 새로 발견된 후보를 담을 때 사용하는 기본 사전
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

# 검색어 의도 분류용 단어
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


# ============================================================
# 2. 날짜 / rotation
# ============================================================

def get_market_now() -> datetime.datetime:
    return datetime.datetime.now(MARKET_TZ)


def get_today_iso() -> str:
    return get_market_now().date().isoformat()


def rotation_index(length: int) -> int:
    if length <= 0:
        return 0
    epoch = datetime.date(2026, 1, 1)
    today = get_market_now().date()
    return (today - epoch).days % length


def get_today_tiktok_queries() -> List[str]:
    return TIKTOK_QUERY_ROTATION[rotation_index(len(TIKTOK_QUERY_ROTATION))]



def get_today_instagram_scraper_tags() -> List[str]:
    """
    하루 최대 INSTAGRAM_SCRAPER_DAILY_LIMIT개의 해시태그를 순환하며 수집한다.
    INSTAGRAM_ROTATION(14개) 중 오늘 시작 위치부터 연속으로 뽑아 넓게 커버한다.
    """
    n = len(INSTAGRAM_ROTATION)
    if n == 0:
        return []

    start = rotation_index(n)
    count = min(INSTAGRAM_SCRAPER_DAILY_LIMIT, n)

    return [
        INSTAGRAM_ROTATION[(start + i) % n]
        for i in range(count)
    ]


def get_today_amazon_queries() -> List[str]:
    return AMAZON_QUERY_ROTATION[rotation_index(len(AMAZON_QUERY_ROTATION))]


def get_today_google_group_names() -> List[str]:
    # 하루 1개 group을 깊게 보고, 2개는 가볍게 seed 후보를 유지한다.
    names = list(GOOGLE_SEED_GROUPS.keys())
    idx = rotation_index(len(names))
    return [
        names[idx],
        names[(idx + 1) % len(names)]
    ]


def get_today_google_seeds(limit: int = 12) -> List[str]:
    """Autocomplete는 요청 폭주를 막기 위해 하루 총 12개 seed만 사용한다."""
    all_seeds = []
    for group in GOOGLE_SEED_GROUPS.values():
        all_seeds.extend(group)

    # 중복 제거 후 날짜별 window rotation
    unique = list(dict.fromkeys(all_seeds))
    if not unique:
        return []

    start = rotation_index(len(unique))
    return [
        unique[(start + i) % len(unique)]
        for i in range(min(limit, len(unique)))
    ]


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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collected_at TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            platform TEXT NOT NULL,
            query TEXT,
            tag TEXT,
            region TEXT,
            text TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS keyword_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date TEXT NOT NULL,
            keyword TEXT NOT NULL,
            platform TEXT NOT NULL,
            region TEXT NOT NULL,
            mentions INTEGER NOT NULL DEFAULT 0,
            UNIQUE(signal_date, keyword, platform, region)
        )
    """)

    # 기존 DB와 호환되는 기존 trend_scores
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trend_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date TEXT NOT NULL,
            keyword TEXT NOT NULL,
            volume_score REAL NOT NULL,
            velocity_score REAL NOT NULL,
            persistence_score REAL NOT NULL,
            cross_platform_score REAL NOT NULL,
            regional_score REAL NOT NULL,
            platform_normalized_score REAL NOT NULL DEFAULT 0,
            trend_score REAL NOT NULL,
            UNIQUE(signal_date, keyword)
        )
    """)

    # 기존 RSS 저장용
    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date TEXT NOT NULL,
            region TEXT NOT NULL,
            rank INTEGER NOT NULL,
            term TEXT NOT NULL
        )
    """)

    # 새로운 Google 신호
    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date TEXT NOT NULL,
            collected_at TEXT NOT NULL,
            region TEXT NOT NULL,
            seed_keyword TEXT,
            keyword TEXT NOT NULL,
            query_type TEXT NOT NULL,
            intent TEXT NOT NULL,
            interest_score REAL,
            rising_score REAL,
            comparison_group TEXT,
            source TEXT NOT NULL,
            UNIQUE(
                signal_date, region, seed_keyword, keyword,
                query_type, source
            )
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_keyword_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date TEXT NOT NULL,
            region TEXT NOT NULL,
            keyword TEXT NOT NULL,
            interest_score REAL,
            source TEXT NOT NULL,
            UNIQUE(signal_date, region, keyword, source)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS google_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            keyword TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL,
            times_seen INTEGER NOT NULL DEFAULT 1
        )
    """)

    # 기존 DB 호환: 신규 점수 컬럼이 없으면 추가
    try:
        conn.execute(
            "ALTER TABLE trend_scores ADD COLUMN platform_normalized_score REAL NOT NULL DEFAULT 0"
        )
    except sqlite3.OperationalError:
        pass

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
        session.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": "🚨 Daily Trend Bot Error Alert\n\n" + error_msg
            },
            timeout=10
        )
    except Exception as e:
        logging.error("Telegram error notification failed: %s", e)


# ============================================================
# 5. Google - Daily RSS (보조 신호)
# ============================================================

def fetch_google_daily_rss(geo: str, count: int = 15) -> List[str]:
    # 2024년 이후 구형 daily RSS(/trends/trendingsearches/daily/rss)는
    # 폐지되어 항상 404를 반환한다. 현재는 /trending/rss 경로를 사용해야 한다.
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; BeautyTrendBot/1.0)"
    }

    try:
        res = session.get(url, headers=headers, timeout=15)
        if res.status_code != 200:
            logging.warning(
                "[%s] Google daily RSS HTTP %s",
                geo, res.status_code
            )
            return []

        root = ET.fromstring(res.content)
        titles = [
            item.text.strip()
            for item in root.findall(".//item/title")
            if item.text
        ]
        return titles[:count]

    except Exception as e:
        logging.error("[%s] Google daily RSS failed: %s", geo, e)
        return []


def save_google_daily_rss(signal_date: str, region: str, terms: List[str]):
    if not terms:
        return

    conn = get_db()
    for rank, term in enumerate(terms, start=1):
        conn.execute("""
            INSERT INTO google_trends
            (signal_date, region, rank, term)
            VALUES (?, ?, ?, ?)
        """, (signal_date, region, rank, term))
    conn.commit()
    conn.close()


# ============================================================
# 6. Google - Autocomplete
# ============================================================

def fetch_google_autocomplete(seed: str, geo: str) -> List[str]:
    """
    Google autocomplete는 Trends 지수가 아니다.
    따라서 '검색량'으로 사용하지 않고 '검색어 후보 발견' 용도로만 사용한다.
    """
    url = "https://suggestqueries.google.com/complete/search"

    params = {
        "client": "firefox",
        "q": seed,
        "hl": "en",
        "gl": geo.lower()
    }

    try:
        res = session.get(url, params=params, timeout=10)
        if res.status_code != 200:
            return []

        data = res.json()
        if not isinstance(data, list) or len(data) < 2:
            return []

        suggestions = data[1]
        if not isinstance(suggestions, list):
            return []

        output = []
        for item in suggestions:
            if isinstance(item, str):
                item = item.strip()
                if item and item.lower() != seed.lower():
                    output.append(item)

        return output[:10]

    except Exception as e:
        logging.debug("Autocomplete failed for %s/%s: %s", seed, geo, e)
        return []


# ============================================================
# 7. Google signal classification
# ============================================================

def classify_intent(keyword: str) -> str:
    text = keyword.lower()

    commercial = sum(
        1 for word in COMMERCIAL_WORDS
        if re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text)
    )

    informational = sum(
        1 for word in INFORMATIONAL_WORDS
        if word in text
    )

    if commercial > informational and commercial > 0:
        return "commercial"
    if informational > commercial and informational > 0:
        return "informational"
    return "product_or_category"


def is_beauty_relevant(text: str) -> bool:
    t = text.lower()

    beauty_terms = [
        "skin", "skincare", "beauty", "cosmetic", "serum", "cream",
        "retinol", "retinal", "pdrn", "niacinamide", "peptide",
        "exosome", "sunscreen", "spf", "acne", "barrier", "toner",
        "ampoule", "essence", "cleanser", "mask", "moisturizer",
        "moisturiser", "hyperpigmentation", "dark spot", "kbeauty",
        "cica", "centella", "ceramide", "ectoin", "spicule",
        "snail", "propolis", "bakuchiol", "azelaic", "salicylic"
    ]

    return any(term in t for term in beauty_terms)


def save_google_signal(
    signal_date: str,
    region: str,
    seed: str,
    keyword: str,
    query_type: str,
    source: str,
    interest_score: Optional[float] = None,
    rising_score: Optional[float] = None
):
    conn = get_db()
    now = get_market_now().isoformat()
    intent = classify_intent(keyword)

    conn.execute("""
        INSERT INTO google_signals
        (
            signal_date, collected_at, region, seed_keyword,
            keyword, query_type, intent, interest_score,
            rising_score, comparison_group, source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(
            signal_date, region, seed_keyword, keyword,
            query_type, source
        )
        DO UPDATE SET
            interest_score = excluded.interest_score,
            rising_score = excluded.rising_score
    """, (
        signal_date, now, region, seed, keyword,
        query_type, intent, interest_score, rising_score,
        seed, source
    ))

    conn.execute("""
        INSERT INTO google_candidates
        (first_seen, last_seen, keyword, source, times_seen)
        VALUES (?, ?, ?, ?, 1)
        ON CONFLICT(keyword)
        DO UPDATE SET
            last_seen = excluded.last_seen,
            times_seen = google_candidates.times_seen + 1
    """, (
        signal_date, signal_date, keyword, source
    ))

    if interest_score is not None:
        conn.execute("""
            INSERT INTO google_keyword_history
            (signal_date, region, keyword, interest_score, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(signal_date, region, keyword, source)
            DO UPDATE SET
                interest_score = excluded.interest_score
        """, (
            signal_date, region, keyword,
            interest_score, source
        ))

    conn.commit()
    conn.close()


def collect_google_independent_signals(
    signal_date: str,
    regions: List[str]
) -> Dict[str, List[Dict]]:
    """
    Google는 SNS와 독립적인 discovery source다.

    무료/무인 GitHub Actions 환경에서는:
    - RSS: NL/DE 각각 1회
    - Autocomplete: 하루 총 12회 이하
    - 요청은 직렬 처리
    - 429/403 발생 시 즉시 해당 실행의 Autocomplete를 중단
    - Autocomplete 결과는 검색량/트렌드 점수로 취급하지 않음
    """
    output = {region: [] for region in regions}
    seeds = get_today_google_seeds(limit=12)

    # 12개 요청을 지역별로 균등 분배
    jobs = []
    for i, seed in enumerate(seeds):
        region = regions[i % len(regions)]
        jobs.append((seed, region))

    logging.info(
        "Google independent discovery: autocomplete_jobs=%d (hard cap=12)",
        len(jobs)
    )

    for seed, region in jobs:
        if is_beauty_relevant(seed):
            save_google_signal(
                signal_date=signal_date,
                region=region,
                seed=seed,
                keyword=seed,
                query_type="seed",
                source="google_seed"
            )

        suggestions = fetch_google_autocomplete(seed, region)

        for suggestion in suggestions:
            if not is_beauty_relevant(suggestion):
                continue

            save_google_signal(
                signal_date=signal_date,
                region=region,
                seed=seed,
                keyword=suggestion,
                query_type="related_candidate",
                source="google_autocomplete"
            )

            output[region].append({
                "keyword": suggestion,
                "seed": seed,
                "intent": classify_intent(suggestion),
                "source": "google_autocomplete",
                "interest_score": None,
                "rising_score": None
            })

        # Google suggestion endpoint도 너무 빠르게 연속 호출하지 않는다.
        time.sleep(1.2)

    return output


# ============================================================
# 9. TikTok - 하루 3 calls
# ============================================================

def fetch_tiktok_captions() -> List[Dict]:
    if not RAPIDAPI_KEY:
        logging.warning("RAPIDAPI_KEY missing. TikTok skipped.")
        return []

    url = (
        "https://tiktok-api23.p.rapidapi.com/"
        "api/search/video"
    )
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "tiktok-api23.p.rapidapi.com"
    }

    queries = get_today_tiktok_queries()[:TIKTOK_DAILY_LIMIT]
    results = []

    for query_index, query in enumerate(queries):
        try:
            # 요청 횟수는 그대로 두고 count만 최대치로 올려
            # 동일 쿼터 안에서 표본을 최대한 확보한다.
            res = session.get(
                url,
                headers=headers,
                params={
                    "keyword": query,
                    "count": str(TIKTOK_QUERY_COUNT),
                    "cursor": "0"
                },
                timeout=15
            )

            if res.status_code != 200:
                logging.warning(
                    "TikTok query '%s' HTTP %s: %s",
                    query, res.status_code, res.text[:300]
                )
                continue

            data = res.json()
            if isinstance(data.get("data"), list):
                items = data["data"]
            elif isinstance(data.get("data"), dict):
                items = (
                    data["data"].get("item_list")
                    or data["data"].get("videos")
                    or []
                )
            else:
                items = []

            for item in items[:TIKTOK_QUERY_COUNT]:
                desc = (
                    item.get("desc")
                    or item.get("title")
                    or ""
                )

                if not desc:
                    continue

                desc = str(desc).strip()
                if len(desc) <= 10:
                    continue

                region = "EU"
                q = query.lower()
                if "germany" in q:
                    region = "DE"
                elif "europe" in q:
                    region = "EU"

                results.append({
                    "platform": "tiktok",
                    "query": query,
                    "tag": "",
                    "region": region,
                    "text": desc.replace("\n", " ")[:180]
                })

        except Exception as e:
            logging.error(
                "TikTok query '%s' failed: %s",
                query, e
            )

        if query_index < len(queries) - 1:
            time.sleep(0.5)

    logging.info(
        "TikTok calls=%d/%d, count_per_call=%d, valid samples=%d",
        len(queries), TIKTOK_DAILY_LIMIT, TIKTOK_QUERY_COUNT, len(results)
    )
    return results


# ============================================================
# 9b. Amazon - Real-Time Amazon Data (하루 3 calls)
# ============================================================

def fetch_amazon_products() -> List[Dict]:
    if not RAPIDAPI_KEY:
        logging.warning("RAPIDAPI_KEY missing. Amazon skipped.")
        return []

    url = "https://real-time-amazon-data.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "real-time-amazon-data.p.rapidapi.com"
    }

    queries = get_today_amazon_queries()[:AMAZON_DAILY_LIMIT]
    results = []

    for query_index, query in enumerate(queries):
        try:
            res = session.get(
                url,
                headers=headers,
                params={
                    "query": query,
                    "page": "1",
                    "country": "DE",  # 유럽 마켓 대표로 독일 아마존 사용 (NL 마켓플레이스 없음)
                    "sort_by": "RELEVANCE"
                },
                timeout=15
            )

            if res.status_code != 200:
                logging.warning(
                    "Amazon query '%s' HTTP %s: %s",
                    query, res.status_code, res.text[:300]
                )
                continue

            data = res.json()
            products = (
                data.get("data", {}).get("products", [])
                if isinstance(data.get("data"), dict)
                else []
            )

            for item in products[:AMAZON_QUERY_COUNT]:
                if not isinstance(item, dict):
                    continue

                title = str(item.get("product_title") or "").strip()
                if not title or len(title) <= 10:
                    continue

                is_best_seller = bool(item.get("is_best_seller"))
                rating_count = item.get("product_num_ratings")

                text = title
                if is_best_seller:
                    text = "[BESTSELLER] " + text

                results.append({
                    "platform": "amazon",
                    "query": query,
                    "tag": "",
                    "region": "DE",
                    "text": text.replace("\n", " ")[:180]
                })

            logging.info(
                "Amazon query '%s' -> %d products (rating samples e.g. %s)",
                query, len(products[:AMAZON_QUERY_COUNT]), rating_count
                if products else None
            )

        except Exception as e:
            logging.error(
                "Amazon query '%s' failed: %s",
                query, e
            )

        if query_index < len(queries) - 1:
            time.sleep(0.5)

    logging.info(
        "Amazon calls=%d/%d, count_per_call<=%d, valid samples=%d",
        len(queries), AMAZON_DAILY_LIMIT, AMAZON_QUERY_COUNT, len(results)
    )
    return results



# ============================================================
# 10. Instagram Scraper2 (JoTucker) - 하루 최대 10 calls
# ============================================================

def fetch_instagram_scraper_captions() -> List[Dict]:
    if not INSTAGRAM_SCRAPER_ENABLED:
        logging.info("Instagram Scraper2 disabled.")
        return []

    if not RAPIDAPI_KEY:
        logging.warning("RAPIDAPI_KEY missing. Instagram Scraper2 skipped.")
        return []

    url = "https://instagram-scraper2.p.rapidapi.com/hash_tag_medias_v2"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "instagram-scraper2.p.rapidapi.com"
    }

    tags = get_today_instagram_scraper_tags()
    results = []

    for tag_index, tag in enumerate(tags):
        try:
            res = session.get(
                url,
                headers=headers,
                params={
                    "hash_tag": tag,
                    "batch_size": str(INSTAGRAM_SCRAPER_QUERY_COUNT)
                },
                timeout=15
            )

            if res.status_code != 200:
                logging.warning(
                    "Instagram Scraper2 #%s HTTP %s: %s",
                    tag, res.status_code, res.text[:300]
                )
                continue

            data = res.json()

            # 응답 스키마가 확정되지 않았으므로 여러 형태를 방어적으로 처리한다.
            if isinstance(data, list):
                items = data
            elif isinstance(data.get("data"), list):
                items = data["data"]
            elif isinstance(data.get("data"), dict):
                items = (
                    data["data"].get("medias")
                    or data["data"].get("items")
                    or []
                )
            else:
                items = (
                    data.get("medias")
                    or data.get("items")
                    or []
                )

            if not isinstance(items, list):
                items = []

            if not items:
                logging.info(
                    "Instagram Scraper2 #%s returned 0 items. "
                    "Raw response (first 300 chars): %s",
                    tag, str(data)[:300]
                )

            for item in items[:INSTAGRAM_SCRAPER_QUERY_COUNT]:
                if not isinstance(item, dict):
                    continue

                raw = item.get("caption")
                if isinstance(raw, dict):
                    raw = raw.get("text", "")
                if not raw:
                    raw = (
                        item.get("caption_text")
                        or item.get("text")
                        or ""
                    )

                if not raw:
                    continue

                raw = str(raw).strip()
                if len(raw) <= 10:
                    continue

                results.append({
                    "platform": "instagram",
                    "query": "",
                    "tag": tag,
                    "region": "GLOBAL",
                    "text": raw.replace("\n", " ")[:180]
                })

        except Exception as e:
            logging.error(
                "Instagram Scraper2 #%s failed: %s",
                tag, e
            )

        if tag_index < len(tags) - 1:
            time.sleep(0.4)

    logging.info(
        "Instagram Scraper2 calls=%d/%d, count_per_call=%d, valid samples=%d",
        len(tags), INSTAGRAM_SCRAPER_DAILY_LIMIT,
        INSTAGRAM_SCRAPER_QUERY_COUNT, len(results)
    )
    return results


# ============================================================
# 11. Raw signal 저장
# ============================================================

def save_raw_signals(signals: List[Dict]):
    if not signals:
        return

    conn = get_db()
    now = get_market_now().isoformat()
    signal_date = get_today_iso()

    for signal in signals:
        conn.execute("""
            INSERT INTO raw_signals
            (
                collected_at, signal_date, platform,
                query, tag, region, text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            now, signal_date,
            signal.get("platform", ""),
            signal.get("query", ""),
            signal.get("tag", ""),
            signal.get("region", ""),
            signal.get("text", "")
        ))

    conn.commit()
    conn.close()


# ============================================================
# 12. Keyword extraction
# ============================================================

def normalize_keyword(keyword: str) -> str:
    return keyword.lower().strip()


def count_keywords_in_text(text: str) -> Counter:
    """
    한 게시물/상품명 안에서 같은 키워드가 여러 번 반복되어도 1회만 센다.
    이렇게 해야 Amazon 상품명이나 해시태그 반복이 volume을 부풀리지 않는다.
    """
    text = text.lower()
    counts = Counter()

    for keyword in INGREDIENTS_VOCAB:
        pattern = (
            r"(?<!\w)" +
            re.escape(keyword.lower()) +
            r"(?!\w)"
        )
        if re.search(pattern, text):
            counts[normalize_keyword(keyword)] = 1

    return counts


def build_daily_keyword_counts(
    signals: List[Dict]
) -> Dict[Tuple[str, str, str], int]:
    """
    keyword mentions = 해당 플랫폼의 독립 sample 수.
    한 sample 안의 반복 단어는 중복 가산하지 않는다.
    """
    counts = Counter()

    for signal in signals:
        platform = signal["platform"]
        region = signal["region"]
        keyword_counts = count_keywords_in_text(signal["text"])

        for keyword in keyword_counts:
            counts[(keyword, platform, region)] += 1

    return counts


def save_keyword_counts(
    signal_date: str,
    counts: Dict[Tuple[str, str, str], int]
):
    if not counts:
        return

    conn = get_db()

    for (keyword, platform, region), mentions in counts.items():
        conn.execute("""
            INSERT INTO keyword_daily
            (
                signal_date, keyword, platform,
                region, mentions
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(
                signal_date, keyword,
                platform, region
            )
            DO UPDATE SET
                mentions = excluded.mentions
        """, (
            signal_date, keyword,
            platform, region, mentions
        ))

    conn.commit()
    conn.close()


# ============================================================
# 13. Social Trend Calculation
# ============================================================

def get_keyword_daily_history(
    keyword: str,
    end_date: str,
    days: int
) -> List[Tuple[str, int]]:
    conn = get_db()

    rows = conn.execute("""
        SELECT signal_date, SUM(mentions) AS total_mentions
        FROM keyword_daily
        WHERE keyword = ?
          AND signal_date < ?
          AND signal_date >= date(?, ?)
        GROUP BY signal_date
        ORDER BY signal_date ASC
    """, (
        keyword, end_date, end_date, f"-{days} day"
    )).fetchall()

    conn.close()

    return [
        (row["signal_date"], row["total_mentions"])
        for row in rows
    ]


def calculate_velocity(
    today_mentions: float,
    history: List[Tuple[str, int]]
) -> Tuple[float, bool]:
    previous_values = [
        mentions
        for _, mentions in history
        if mentions > 0
    ]

    if not previous_values:
        return 0.0, False

    avg_previous = sum(previous_values) / len(previous_values)

    if avg_previous <= 0:
        return 0.0, False

    return (
        (today_mentions - avg_previous) / avg_previous,
        True
    )


def calculate_persistence(
    history: List[Tuple[str, int]],
    window_days: int = 7
) -> float:
    if not history:
        return 0.0

    active_days = sum(
        1 for _, mentions in history
        if mentions > 0
    )

    return min(active_days / window_days, 1.0)


def calculate_cross_platform(
    keyword: str,
    signal_date: str
) -> float:
    conn = get_db()

    rows = conn.execute("""
        SELECT DISTINCT platform
        FROM keyword_daily
        WHERE keyword = ?
          AND signal_date = ?
          AND mentions > 0
    """, (keyword, signal_date)).fetchall()

    conn.close()

    platforms = {row["platform"] for row in rows}
    return min(len(platforms) / 3.0, 1.0)


def calculate_regional_score(
    keyword: str,
    signal_date: str
) -> float:
    conn = get_db()

    rows = conn.execute("""
        SELECT DISTINCT region
        FROM keyword_daily
        WHERE keyword = ?
          AND signal_date = ?
          AND mentions > 0
    """, (keyword, signal_date)).fetchall()

    conn.close()

    regions = {row["region"] for row in rows}
    return min(len(regions) / 2.0, 1.0)


def calculate_volume_score(today_mentions: float) -> float:
    if today_mentions <= 0:
        return 0.0

    return min(
        math.log1p(today_mentions) / math.log1p(30),
        1.0
    )


def calculate_trend_status(
    velocity: float,
    has_history: bool,
    persistence: float
) -> str:
    if not has_history:
        return "INSUFFICIENT DATA"
    if velocity >= 0.50:
        return "RISING"
    if velocity >= 0.10:
        return "EMERGING"
    if velocity <= -0.30:
        return "DECLINING"
    if persistence >= 0.40:
        return "ESTABLISHED"
    return "EMERGING"




def calculate_platform_normalized_score(
    keyword: str,
    signal_date: str
) -> float:
    """
    플랫폼별 샘플 수가 다르므로 단순 mentions 합산 대신
    각 플랫폼 내 keyword 비율을 평균한다.
    """
    conn = get_db()
    rows = conn.execute("""
        SELECT platform,
               SUM(CASE WHEN keyword = ? THEN mentions ELSE 0 END) AS kw_mentions,
               SUM(mentions) AS platform_mentions
        FROM keyword_daily
        WHERE signal_date = ?
        GROUP BY platform
    """, (keyword, signal_date)).fetchall()
    conn.close()

    rates = []
    for row in rows:
        total = row["platform_mentions"] or 0
        kw = row["kw_mentions"] or 0
        if total > 0:
            rates.append(min(kw / total, 1.0))

    if not rates:
        return 0.0

    return sum(rates) / len(rates)


def calculate_generic_penalty(keyword: str) -> float:
    """너무 일반적인 카테고리 단어가 상위권을 독점하지 않도록 약한 감점."""
    generic = {
        "skincare", "serum", "cream", "beauty", "sunscreen",
        "cleanser", "toner", "moisturizer", "mask", "cosmetics",
        "kbeauty", "skin barrier"
    }
    return 0.72 if keyword.lower() in generic else 1.0

def calculate_trend_scores(
    signal_date: str,
    daily_counts: Dict[Tuple[str, str, str], int]
) -> List[Dict]:
    keywords = {
        keyword
        for keyword, _, _
        in daily_counts.keys()
    }

    results = []

    for keyword in keywords:
        today_mentions = sum(
            mentions
            for (kw, _, _), mentions
            in daily_counts.items()
            if kw == keyword
        )

        history = get_keyword_daily_history(
            keyword, signal_date, 7
        )

        velocity, has_history = calculate_velocity(
            today_mentions, history
        )

        persistence = calculate_persistence(history, 7)
        cross_platform = calculate_cross_platform(
            keyword, signal_date
        )
        regional = calculate_regional_score(
            keyword, signal_date
        )
        volume_score = calculate_volume_score(today_mentions)
        platform_normalized = calculate_platform_normalized_score(
            keyword, signal_date
        )

        if has_history:
            velocity_clamped = max(-1.0, min(velocity, 1.0))
            velocity_score = (velocity_clamped + 1.0) / 2.0
        else:
            velocity_score = 0.5

        # 신규 발견은 volume보다 cross-platform/velocity를 더 중요하게 본다.
        base_score = (
            volume_score * 0.15
            + velocity_score * 0.30
            + persistence * 0.20
            + cross_platform * 0.20
            + regional * 0.05
            + platform_normalized * 0.10
        ) * 100

        trend_score = base_score * calculate_generic_penalty(keyword)

        results.append({
            "keyword": keyword,
            "today_mentions": today_mentions,
            "velocity": velocity,
            "has_history": has_history,
            "status": calculate_trend_status(
                velocity, has_history, persistence
            ),
            "volume_score": volume_score * 100,
            "velocity_score": velocity_score * 100,
            "persistence_score": persistence * 100,
            "cross_platform_score": cross_platform * 100,
            "regional_score": regional * 100,
            "platform_normalized_score": platform_normalized * 100,
            "trend_score": trend_score
        })

    results.sort(
        key=lambda x: x["trend_score"],
        reverse=True
    )

    return results


def save_trend_scores(
    signal_date: str,
    scores: List[Dict]
):
    conn = get_db()

    for item in scores:
        conn.execute("""
            INSERT INTO trend_scores
            (
                signal_date, keyword,
                volume_score, velocity_score,
                persistence_score, cross_platform_score,
                regional_score, platform_normalized_score, trend_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(signal_date, keyword)
            DO UPDATE SET
                volume_score = excluded.volume_score,
                velocity_score = excluded.velocity_score,
                persistence_score = excluded.persistence_score,
                cross_platform_score = excluded.cross_platform_score,
                regional_score = excluded.regional_score,
                platform_normalized_score = excluded.platform_normalized_score,
                trend_score = excluded.trend_score
        """, (
            signal_date,
            item["keyword"],
            item["volume_score"],
            item["velocity_score"],
            item["persistence_score"],
            item["cross_platform_score"],
            item["regional_score"],
            item.get("platform_normalized_score", 0),
            item["trend_score"]
        ))

    conn.commit()
    conn.close()


# ============================================================
# 14. Google summary
# ============================================================

def get_google_summary(
    signal_date: str,
    regions: List[str]
) -> str:
    conn = get_db()

    lines = []

    for region in regions:
        rows = conn.execute("""
            SELECT
                keyword,
                intent,
                interest_score,
                rising_score,
                source
            FROM google_signals
            WHERE signal_date = ?
              AND region = ?
              AND (
                  query_type = 'related_candidate'
                  OR query_type = 'interest'
              )
            ORDER BY
                CASE
                    WHEN rising_score IS NULL THEN -999999
                    ELSE rising_score
                END DESC,
                CASE
                    WHEN interest_score IS NULL THEN -999999
                    ELSE interest_score
                END DESC
            LIMIT 20
        """, (signal_date, region)).fetchall()

        lines.append(f"[Google {region}]")

        if not rows:
            lines.append("No Google beauty discovery data today.")
            continue

        seen = set()

        for row in rows:
            keyword = row["keyword"]
            if keyword in seen:
                continue
            seen.add(keyword)

            interest = (
                f"{row['interest_score']:.0f}"
                if row["interest_score"] is not None
                else "NA"
            )

            rising = (
                f"{row['rising_score']:+.1f}%"
                if row["rising_score"] is not None
                else "NA"
            )

            lines.append(
                f"- {keyword} | "
                f"intent={row['intent']} | "
                f"interest={interest} | "
                f"rising={rising} | "
                f"source={row['source']}"
            )

    conn.close()
    return "\n".join(lines)


def get_google_candidate_list(
    signal_date: str,
    limit: int = 30
) -> List[str]:
    conn = get_db()

    rows = conn.execute("""
        SELECT keyword
        FROM google_signals
        WHERE signal_date = ?
        ORDER BY
            CASE
                WHEN rising_score IS NULL THEN 0
                ELSE rising_score
            END DESC,
            CASE
                WHEN interest_score IS NULL THEN 0
                ELSE interest_score
            END DESC
        LIMIT ?
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
# 15. Trend Summary
# ============================================================

def build_trend_summary(scores: List[Dict]) -> str:
    if not scores:
        return "No quantitative social trend score available today."

    lines = []

    for rank, item in enumerate(scores[:10], start=1):
        velocity_text = (
            f"{item['velocity'] * 100:+.1f}%"
            if item["has_history"]
            else "INSUFFICIENT_HISTORY"
        )

        lines.append(
            f"{rank}. {item['keyword']} | "
            f"status={item['status']} | "
            f"mentions={item['today_mentions']} | "
            f"velocity={velocity_text} | "
            f"persistence={item['persistence_score']:.0f}/100 | "
            f"cross_platform={item['cross_platform_score']:.0f}/100 | "
            f"regional={item['regional_score']:.0f}/100 | "
            f"TREND_SCORE={item['trend_score']:.1f}/100"
        )

    return "\n".join(lines)


# ============================================================
# 16. Gemini
# ============================================================

def call_gemini_api(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
    )

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8192
        }
    }

    res = session.post(
        url,
        headers=headers,
        json=payload,
        timeout=60
    )

    if res.status_code != 200:
        logging.error(
            "Gemini API HTTP %s: %s",
            res.status_code, res.text
        )
        raise RuntimeError(
            f"Gemini API failed with status {res.status_code}"
        )

    data = res.json()
    candidates = data.get("candidates", [])

    if not candidates:
        raise RuntimeError("Gemini API returned no candidates.")

    parts = candidates[0].get("content", {}).get("parts", [])

    if not parts:
        raise RuntimeError("Gemini API response parts empty.")

    report_text = parts[0].get("text", "").strip()

    if not report_text:
        raise RuntimeError("Gemini returned empty report.")

    return report_text


def generate_gemini_report(
    google_summary: str,
    google_candidates: List[str],
    social_data: List[Dict],
    freq_summary: str,
    trend_summary: str
) -> str:
    social_lines = []

    for item in social_data:
        platform = item.get("platform", "")
        query = item.get("query", "")
        tag = item.get("tag", "")
        region = item.get("region", "")
        text = item.get("text", "")

        source = platform
        if query:
            source += f"/{query}"
        if tag:
            source += f"/#{tag}"

        social_lines.append(
            f"[{source} | {region}] {text}"
        )

    social_text = "\n".join(social_lines)
    social_count = len(social_data)

    google_candidates_text = (
        ", ".join(google_candidates)
        if google_candidates
        else "NONE"
    )

    if social_count == 0 and not google_summary.strip():
        data_status = """
CRITICAL DATA STATUS:
Today's live social and Google beauty discovery data are unavailable.
Do not fabricate a measured trend ranking.
You may provide only clearly labeled commercial hypotheses.
"""
    else:
        data_status = f"""
DATA STATUS:
Valid social samples: {social_count}
Google discovery is independent from social sampling.
Use measured quantitative signals first.
Do not turn autocomplete candidates into search-volume claims.
If a Google value is NA, do not invent a number.
"""

    prompt = f"""
You are the CEO and Head of Sourcing for a European cosmetics and skincare
e-commerce platform based in the Netherlands.

Generate a DAILY COSMETICS & SKINCARE MARKET TREND REPORT.

{data_status}

IMPORTANT DATA MODEL:
1. TikTok = early viral/discovery signal.
2. Instagram Scraper = secondary social/content confirmation.
3. Amazon = purchase-stage signal (actual product titles, best-seller
   tags, review counts). Amazon presence means the keyword has already
   reached commercial demand, not just social chatter.
4. Google = independent search-market discovery.
5. A keyword found only on TikTok/Instagram should NOT be considered
   confirmed unless Google or Amazon data supports it, or it is
   explicitly labeled emerging.
6. Google Autocomplete candidates are NOT Google Trends volume scores.
7. Google Trends interest/rising values, when available, are relative
   signals.
8. Do not claim that one keyword's 100 is directly comparable with
   another keyword's 100 unless they were collected in the same
   comparison group.
9. Do not invent missing values.

GOOGLE INDEPENDENT DISCOVERY:
{google_summary}

GOOGLE CANDIDATES:
{google_candidates_text}

SOCIAL QUANTITATIVE TREND SCORES:
{trend_summary}

KNOWN VOCABULARY FREQUENCY:
{freq_summary}

LIVE SOCIAL SAMPLES:
{social_text}

========================================================
ANALYSIS TASK
========================================================

Classify major signals into:
- CONFIRMED TREND: cross-platform social signal + independent Google discovery support
- EMERGING / VIRAL: strong social, weak or not-yet-confirmed Google
- SEARCH-DRIVEN: strong Google, weak social
- ESTABLISHED: persistent signal without unusual acceleration

For each major candidate, distinguish measured evidence from hypothesis.

Focus on:
- Netherlands / Western Europe
- Germany
- K-Beauty
- Arabic/Middle Eastern customer opportunities
- ingredients
- product formats
- commercial intent
- sourcing opportunities

Do not overstate small samples. Today's TikTok maximum is 3 API calls,
Amazon maximum is 3 API calls, and Instagram (Scraper2) maximum is
10 API calls, so social sampling, while broader than before, is still
not a full-population census.

========================================================
STRICT LANGUAGE & ORDER RULES
========================================================

The report MUST contain exactly THREE sections separated by
===SPLIT_SECTION===.

Order:
1. KOREAN
2. ARABIC
3. ENGLISH

Do not include Dutch or German.

--- SECTION 1 ---
Title: 🌐 글로벌 화장품 & 스킨케어 시장 데일리 트렌드 리포트

1. 📈 오늘의 TOP 5 트렌드 시그널
For every signal state its evidence type:
[CONFIRMED], [EMERGING], [SEARCH-DRIVEN], or [ESTABLISHED].

2. 💡 CEO 소싱 & 마케팅 전략
Focus on Netherlands/Western Europe, Germany, Arabic/Middle East,
and K-Beauty.

3. 💄 바이럴 제품 컨셉
Give commercially actionable product concepts.

===SPLIT_SECTION===

--- SECTION 2 ---
Title: 🌐 التقرير اليومي العالمي لاتجاهات مستحضرات التجميل والعناية بالبشرة

1. 📈 أهم 5 إشارات للاتجاهات اليوم
Use the same evidence labels in English in parentheses.

2. 💡 استراتيجية التوريد والتسويق

3. 💄 مفهوم منتج تجاري

===SPLIT_SECTION===

--- SECTION 3 ---
Title: 🌐 GLOBAL COSMETICS & SKINCARE MARKET DAILY TREND REPORT

1. 📈 TOP 5 TREND SIGNALS TODAY
Use [CONFIRMED], [EMERGING], [SEARCH-DRIVEN], or [ESTABLISHED].

2. 💡 CEO SOURCING & MARKETING STRATEGY

3. 💄 VIRAL PRODUCT CONCEPT
"""

    return call_gemini_api(prompt)


# ============================================================
# 16b. Weekly Rollup (주말 요약)
# ============================================================

WEEKLY_SUMMARY_WEEKDAY = 5  # Python date.weekday(): Mon=0 ... Sat=5, Sun=6


def is_weekly_summary_day() -> bool:
    return get_market_now().date().weekday() == WEEKLY_SUMMARY_WEEKDAY


def get_past_weekday_dates(signal_date: str) -> List[str]:
    """
    이번 주(월~금)의 날짜 리스트를 반환한다.
    토요일에 실행되면 바로 직전의 월~금이 대상이 된다.
    """
    today = datetime.date.fromisoformat(signal_date)
    # 이번 주 월요일 = 오늘 - (오늘의 weekday 값)
    monday = today - datetime.timedelta(days=today.weekday())
    return [
        (monday + datetime.timedelta(days=i)).isoformat()
        for i in range(5)  # Mon~Fri
    ]


def build_weekly_rollup(date_list: List[str]) -> Tuple[str, str]:
    """
    trend_scores와 keyword_daily를 주간 단위로 집계해서
    (키워드 랭킹 텍스트, 플랫폼별 집계 텍스트) 튜플로 반환한다.
    """
    if not date_list:
        return "No data.", "No data."

    conn = get_db()
    placeholders = ",".join("?" for _ in date_list)

    keyword_rows = conn.execute(f"""
        SELECT
            keyword,
            SUM(trend_score) AS total_score,
            AVG(trend_score) AS avg_score,
            MAX(trend_score) AS peak_score,
            COUNT(DISTINCT signal_date) AS active_days
        FROM trend_scores
        WHERE signal_date IN ({placeholders})
        GROUP BY keyword
        ORDER BY total_score DESC
        LIMIT 25
    """, date_list).fetchall()

    platform_rows = conn.execute(f"""
        SELECT
            platform,
            SUM(mentions) AS total_mentions,
            COUNT(DISTINCT keyword) AS unique_keywords
        FROM keyword_daily
        WHERE signal_date IN ({placeholders})
        GROUP BY platform
        ORDER BY total_mentions DESC
    """, date_list).fetchall()

    conn.close()

    keyword_lines = []
    for row in keyword_rows:
        keyword_lines.append(
            f"- {row['keyword']}: "
            f"avg_score={row['avg_score']:.1f}, "
            f"peak_score={row['peak_score']:.1f}, "
            f"active_days={row['active_days']}/5"
        )

    platform_lines = []
    for row in platform_rows:
        platform_lines.append(
            f"- {row['platform']}: "
            f"mentions={row['total_mentions']}, "
            f"unique_keywords={row['unique_keywords']}"
        )

    keyword_text = (
        "\n".join(keyword_lines)
        if keyword_lines
        else "No weekly keyword data."
    )
    platform_text = (
        "\n".join(platform_lines)
        if platform_lines
        else "No weekly platform data."
    )

    return keyword_text, platform_text


def generate_weekly_summary_report(
    date_list: List[str],
    keyword_rollup: str,
    platform_rollup: str
) -> str:
    prompt = f"""
You are the CEO and Head of Sourcing for a European cosmetics and skincare
e-commerce platform based in the Netherlands.

Generate a WEEKLY COSMETICS & SKINCARE MARKET ROLLUP covering
{date_list[0]} to {date_list[-1]} (Mon-Fri), based on aggregated
quantitative trend scores collected this week. Weekend data collection
continues separately and is not part of this rollup.

WEEKLY KEYWORD RANKING (by aggregated trend_score):
{keyword_rollup}

WEEKLY PLATFORM BREAKDOWN (TikTok / Amazon / Instagram / Google):
{platform_rollup}

========================================================
ANALYSIS TASK
========================================================

Summarize the week's overall direction:
- Which keywords held the strongest, most persistent signal all week
  (high active_days, not just a single-day spike)?
- Which platform contributed the most this week, and what does that
  imply (e.g. Amazon-heavy = purchase-stage signal, TikTok-heavy =
  early viral signal)?
- Any keyword that spiked once but did not persist (low active_days,
  high peak_score) should be flagged as noise, not a trend.

Do not overstate small samples. Be honest about data limitations.

========================================================
STRICT LANGUAGE & ORDER RULES
========================================================

The report MUST contain exactly THREE sections separated by
===SPLIT_SECTION===, in this order: KOREAN, ARABIC, ENGLISH.
Do not include Dutch or German.

--- SECTION 1 ---
Title: 📅 주간 화장품 & 스킨케어 트렌드 요약 ({date_list[0]} ~ {date_list[-1]})

1. 🏆 이번 주 TOP 5 지속 트렌드
2. 📊 플랫폼별 기여도 분석
3. ⚠️ 일시적 스파이크(노이즈) 주의 키워드
4. 💡 다음 주 소싱/마케팅 제안

===SPLIT_SECTION===

--- SECTION 2 ---
Title: 📅 ملخص أسبوعي لاتجاهات مستحضرات التجميل والعناية بالبشرة

1. 🏆 أفضل 5 اتجاهات مستمرة هذا الأسبوع
2. 📊 تحليل مساهمة كل منصة
3. ⚠️ كلمات مفتاحية قد تكون ضجة مؤقتة فقط
4. 💡 اقتراحات التوريد والتسويق للأسبوع القادم

===SPLIT_SECTION===

--- SECTION 3 ---
Title: 📅 WEEKLY COSMETICS & SKINCARE TREND ROLLUP ({date_list[0]} ~ {date_list[-1]})

1. 🏆 TOP 5 PERSISTENT TRENDS THIS WEEK
2. 📊 PLATFORM CONTRIBUTION ANALYSIS
3. ⚠️ KEYWORDS THAT LOOK LIKE ONE-DAY NOISE
4. 💡 NEXT WEEK SOURCING/MARKETING SUGGESTIONS
"""

    return call_gemini_api(prompt)


# ============================================================
# 17. Telegram
# ============================================================

def send_telegram_message(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram credentials missing. Message not sent.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    max_length = 4000
    chunks = [
        message[i:i + max_length]
        for i in range(0, len(message), max_length)
    ]

    for chunk in chunks:
        try:
            res = session.post(
                url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": chunk
                },
                timeout=15
            )

            if res.status_code != 200:
                logging.warning(
                    "Telegram failed HTTP %s: %s",
                    res.status_code, res.text
                )

        except Exception as e:
            logging.error(
                "Telegram notification failed: %s", e
            )


# ============================================================
# 18. Main Pipeline
# ============================================================

def main():
    logging.info("=== Daily Cosmetics Trend Bot Started ===")

    try:
        init_database()

        signal_date = get_today_iso()
        regions = ["NL", "DE"]

        logging.info(
            "Today's TikTok queries: %s",
            get_today_tiktok_queries()
        )
        logging.info(
            "Today's Instagram scraper tags: %s",
            get_today_instagram_scraper_tags()
        )
        logging.info(
            "Today's Google groups: %s",
            get_today_google_group_names()
        )

        # ----------------------------------------------------
        # 1. Google independent discovery
        # ----------------------------------------------------
        logging.info(
            "Collecting independent Google beauty signals..."
        )

        google_data = collect_google_independent_signals(
            signal_date, regions
        )

        # Daily general RSS는 보조적인 시장 context로만 저장
        google_nl_rss = fetch_google_daily_rss("NL", 15)
        google_de_rss = fetch_google_daily_rss("DE", 15)

        save_google_daily_rss(
            signal_date, "NL", google_nl_rss
        )
        save_google_daily_rss(
            signal_date, "DE", google_de_rss
        )

        # ----------------------------------------------------
        # 2. Social signals
        # ----------------------------------------------------
        logging.info("Fetching TikTok...")
        tiktok_signals = fetch_tiktok_captions()

        logging.info("Fetching Amazon...")
        amazon_signals = fetch_amazon_products()

        logging.info("Fetching Instagram (Scraper2)...")
        instagram_signals = fetch_instagram_scraper_captions()

        all_signals = (
            tiktok_signals +
            amazon_signals +
            instagram_signals
        )

        save_raw_signals(all_signals)

        # ----------------------------------------------------
        # 3. Social keyword counts
        # ----------------------------------------------------
        daily_counts = build_daily_keyword_counts(
            all_signals
        )

        save_keyword_counts(
            signal_date,
            daily_counts
        )

        # ----------------------------------------------------
        # 4. Social trend scores
        # ----------------------------------------------------
        trend_scores = calculate_trend_scores(
            signal_date,
            daily_counts
        )

        save_trend_scores(
            signal_date,
            trend_scores
        )

        trend_summary_str = build_trend_summary(
            trend_scores
        )

        freq_lines = []

        for item in trend_scores[:20]:
            freq_lines.append(
                f"- {item['keyword']}: "
                f"{item['today_mentions']} mentions"
            )

        freq_summary_str = (
            "\n".join(freq_lines)
            if freq_lines
            else "No vocabulary frequency data today."
        )

        # ----------------------------------------------------
        # 5. Google summary
        # ----------------------------------------------------
        google_summary = get_google_summary(
            signal_date, regions
        )

        google_candidates = get_google_candidate_list(
            signal_date, 30
        )

        # ----------------------------------------------------
        # 6. Gemini
        # ----------------------------------------------------
        logging.info("Generating Gemini report...")

        report = generate_gemini_report(
            google_summary=google_summary,
            google_candidates=google_candidates,
            social_data=all_signals,
            freq_summary=freq_summary_str,
            trend_summary=trend_summary_str
        )

        # ----------------------------------------------------
        # 7. Telegram
        # ----------------------------------------------------
        sections = [
            section.strip()
            for section
            in report.split("===SPLIT_SECTION===")
            if section.strip()
        ]

        for index, section in enumerate(sections):
            logging.info(
                "Sending report section %d/%d",
                index + 1, len(sections)
            )
            send_telegram_message(section)

        # ----------------------------------------------------
        # 8. Weekly rollup (토요일에만 추가 발송, 데이터 수집은 계속됨)
        # ----------------------------------------------------
        if is_weekly_summary_day():
            try:
                logging.info(
                    "Today is the weekly summary day - "
                    "building weekly rollup..."
                )

                week_dates = get_past_weekday_dates(signal_date)
                keyword_rollup, platform_rollup = build_weekly_rollup(
                    week_dates
                )

                weekly_report = generate_weekly_summary_report(
                    week_dates, keyword_rollup, platform_rollup
                )

                weekly_sections = [
                    section.strip()
                    for section
                    in weekly_report.split("===SPLIT_SECTION===")
                    if section.strip()
                ]

                for index, section in enumerate(weekly_sections):
                    logging.info(
                        "Sending weekly report section %d/%d",
                        index + 1, len(weekly_sections)
                    )
                    send_telegram_message(section)

            except Exception as e:
                logging.error(
                    "Weekly rollup failed (daily report already sent): %s",
                    e, exc_info=True
                )
                send_telegram_error(
                    f"Weekly rollup failed: {str(e)} "
                    "(daily report was sent successfully)"
                )

        logging.info(
            "=== Daily Cosmetics Trend Bot Completed Successfully ==="
        )

    except Exception as e:
        err_msg = f"Pipeline execution failed: {str(e)}"
        logging.error(err_msg, exc_info=True)
        send_telegram_error(err_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
