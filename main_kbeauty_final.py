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

# tiktok-scraper7 (tikwm) 유료 플랜 실측 한도: 300 requests/month (hard limit),
# 120 requests/minute. 월간 한도 기준 하루 9회로 고정한다 (9 * 31일 = 279 <= 300,
# 재시도/여유분을 감안해 10이 아닌 9로 설정).
TIKTOK_DAILY_LIMIT = 9
TIKTOK_QUERY_COUNT = 50  # 요청 1회당 가져오는 최대 영상 수 (쿼터는 호출 수 기준이므로 부담 없음)

# Instagram은 Apify의 공식 유지 Actor(apify/instagram-scraper)를 사용한다.
# Free plan에서 이 Actor의 결과 단가는 $2.70/1,000 results.
# $5.00 무료 크레딧 기준 이론상 한도는 1,851건($5.00 / $2.70 * 1000).
# 진짜 안전장치는 월간 캡(아래 1,800건=$4.86)이다. 하루 캡은 태그당 배분량을
# 정하는 목표치일 뿐이고, remaining이 월간 캡에 의해 자동으로 줄어들기 때문에
# 하루 캡을 다소 넉넉히 잡아도(60 x 31일 = 1,860건, 단독으로는 $5.02로 살짝
# 초과) 실제로는 월중 어느 시점에 월간 캡에서 자연스럽게 멈춘다 - 이번 달
# 며칠 일찍 예산을 다 쓰고 그 뒤에는 0건 수집으로 안전하게 유지된다.
# 태그당 12건(5개 태그 x 12 = 60) 목표.
APIFY_INSTAGRAM_ENABLED = True
APIFY_INSTAGRAM_MONTHLY_RESULT_LIMIT = 1800
APIFY_INSTAGRAM_DAILY_RESULT_LIMIT = 60
APIFY_INSTAGRAM_ACTOR = "apify/instagram-scraper"

# Amazon은 "구매 전환 신호"로 활용한다 (SNS의 화제성 신호와 상호보완).
AMAZON_DAILY_LIMIT = 3
AMAZON_QUERY_COUNT = 50  # /search 응답에서 최대로 취할 상품 수 (실제 페이지당 반환 수는 API 쪽 상한을 따름)

# K-Signal (Korea Beauty & Fashion Velocity Feed) - 한국 국내 이커머스
# (Olive Young/Musinsa/Zigzag/Glowpick/Hwahae) 랭킹 가속도를 기반으로 한
# "선행 지표" 신호. 서구권 SNS/아마존에 아직 안 뜬 트렌드를 미리 포착하는 용도.
# RapidAPI BASIC 플랜 실측 한도: 월 50 calls (hard limit).
# 매일 1회씩만 호출한다 (31일 기준 31회 <= 50, 여유 19회 확보 - 재시도/테스트용 버퍼).
K_SIGNAL_MONTHLY_LIMIT = 50
K_SIGNAL_DAILY_LIMIT = 1
K_SIGNAL_FETCH_LIMIT = 50
K_SIGNAL_MIN_CONFIDENCE = 0.5
K_SIGNAL_TEASER_ENABLED = False
K_SIGNAL_TEASER_MAX_MONTHLY = 19
# 기존 timeout=8 -> 25초로 올렸는데도 실측 응답이 25초를 넘는 날이 있어
# 여전히 Read timed out이 발생했다(2026-08-12 07:57 실행 로그: read timeout=25
# 로 실패). GitHub Actions 잡 전체 시간에는 여유가 있으므로 45초로 더 늘려
# 정상 응답을 받을 확률을 높인다. reserve_provider_call은 호출 전에 이미
# quota를 차감하므로(= RapidAPI 쪽에서도 요청 자체는 처리 중이었을 가능성이 큼),
# 타임아웃을 늘려 "호출은 셌는데 데이터는 못 받는" 낭비를 줄이는 게 목적이다.
K_SIGNAL_TIMEOUT_SECONDS = 45

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


# YouTube Data API v3 - 공식 API
# 기본 무료 quota: 10,000 units/day. search.list = 100 units/call,
# videos.list = 1 unit/call. 실사용 안정성을 위해 96 search calls +
# 6 video-stat calls = 9,606 units/day까지 사용한다.
# 48개 beauty query를 NL/DE 각각 검색해 서유럽 신호를 넓게 커버한다.
YOUTUBE_SEARCH_CALLS_PER_DAY = 96
YOUTUBE_VIDEO_STATS_CALLS_PER_DAY = 6
YOUTUBE_SEARCH_RESULTS_PER_CALL = 50
YOUTUBE_VIDEO_STATS_BATCH_SIZE = 50
YOUTUBE_LOOKBACK_DAYS = 7

YOUTUBE_QUERY_ROTATION = [
    "skincare", "skincare routine", "beauty skincare", "kbeauty",
    "korean skincare", "kbeauty routine", "skincare ingredient",
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

# TikTok은 tiktok-scraper7 플랜 기준 300 calls/month(hard limit)이다.
# 31일 기준으로도 한도를 넘지 않도록 하루 9회로 설정한다 (9 * 31 = 279 <= 300).
# 하루 9개를 flat pool에서 sliding window로 순환 선택해 넓게 커버한다.
TIKTOK_QUERY_ROTATION = [
    "skincare", "skincare routine", "beauty skincare",
    "kbeauty", "korean skincare", "kbeauty routine",
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
    "skincare europe", "kbeauty europe", "beauty trends europe",
    "skincare germany", "kbeauty germany", "beauty germany",
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
# K-Signal은 read timeout이 발생해도 urllib3 재시도로 30~45초를 소비하지 않도록
# 별도 no-retry 세션을 사용한다. 실패하면 해당 소스만 비우고 전체 보고서는 계속 진행한다.
k_signal_session = requests.Session()
apify_session = requests.Session()


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
    """
    하루 최대 TIKTOK_DAILY_LIMIT개의 검색어를 순환하며 수집한다.
    고정 TIKTOK_QUERY_ROTATION(70%)에 이번 주 동적 후보 풀(30%)을 섞은
    하이브리드 풀에서, 오늘 시작 위치부터 연속으로 뽑아 넓게 커버한다.
    """
    hybrid_pool = interleave_hybrid_expand(
        TIKTOK_QUERY_ROTATION, get_weekly_dynamic_pool()
    )
    n = len(hybrid_pool)
    if n == 0:
        return []

    start = rotation_index(n)
    count = min(TIKTOK_DAILY_LIMIT, n)

    return [
        hybrid_pool[(start + i) % n]
        for i in range(count)
    ]



def get_today_instagram_tag() -> str:
    """Instagram Statistics API: 하루 1개 tag를 순환한다. (현재 미사용 - Apify 경로가 실제 사용됨)"""
    if not INSTAGRAM_ROTATION:
        return "kbeauty"
    return INSTAGRAM_ROTATION[rotation_index(len(INSTAGRAM_ROTATION))]


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
# 2b. 동적 하이브리드 태그 파이프라인 (고정 70% + 동적 30%)
# ============================================================
#
# 아이디어: 우리가 이미 매일 수집하는 Google 자동완성 candidate와
# (TikTok/Instagram/YouTube가 다 같이 합류하는) trend_scores의
# velocity 상승 키워드를 "그 주의 신규 후보 풀"로 뽑아서,
# 기존 고정 rotation 리스트에 섞어 넣는다.
#
# - 캐시 단위: ISO 주(월요일 시작). 같은 주 안에서는 동일한 동적 풀을
#   재사용한다 (매일 다시 뽑으면 sliding-window 커버리지가 흔들림).
# - TikTok/Instagram: 하루 호출 수(TIKTOK_DAILY_LIMIT=9, Instagram=1개)가
#   풀 크기와 무관하게 고정돼 있으므로, 풀 자체를 "확장"해서 섞는다
#   (interleave_hybrid_expand). 예산에 영향 없음.
# - YouTube: 매일 풀 전체를 다 검색하므로(96 calls/day 예산이 풀 크기에
#   비례), 풀 크기를 그대로 유지한 채 30%만 동적 키워드로 "교체"한다
#   (replace_hybrid_fixed_size). 예산 불변.

DYNAMIC_POOL_RATIO = 0.30
DYNAMIC_POOL_MAX_SIZE = 40
DYNAMIC_CANDIDATE_MIN_TIMES_SEEN = 2      # google_candidates 최소 재등장 횟수
DYNAMIC_CANDIDATE_LOOKBACK_DAYS = 14      # trend_scores 조회 기간


def get_iso_week_id() -> str:
    """ISO 연-주 문자열, 예: '2026-W33'. 월요일 기준으로 주가 바뀐다."""
    year, week, _ = get_market_now().date().isocalendar()
    return f"{year}-W{week:02d}"


def build_dynamic_keyword_pool(limit: int = DYNAMIC_POOL_MAX_SIZE) -> List[str]:
    """
    Google 자동완성에서 반복적으로 잡힌 candidate + 최근 2주간
    trend_scores에서 velocity가 상승세(EMERGING/RISING 임계치 이상)였던
    키워드를 합쳐서 "이번 주 동적 후보 풀"의 원재료를 만든다.
    """
    conn = get_db()
    today = get_market_now().date()
    lookback_start = (
        today - datetime.timedelta(days=DYNAMIC_CANDIDATE_LOOKBACK_DAYS)
    ).isoformat()

    candidate_rows = conn.execute("""
        SELECT keyword, times_seen
        FROM google_candidates
        WHERE times_seen >= ?
        ORDER BY times_seen DESC, last_seen DESC
        LIMIT ?
    """, (DYNAMIC_CANDIDATE_MIN_TIMES_SEEN, limit * 2)).fetchall()

    # calculate_trend_status와 동일한 임계치(EMERGING: velocity>=0.10)를
    # 재사용해서, "최근 2주 안에 한 번이라도 상승세였던 키워드"를 뽑는다.
    # (trend_scores에는 status 컬럼이 없어서 velocity_score로 근사한다.)
    trend_rows = conn.execute("""
        SELECT keyword, MAX(velocity_score) AS peak_velocity
        FROM trend_scores
        WHERE signal_date >= ?
        GROUP BY keyword
        HAVING peak_velocity >= 0.10
        ORDER BY peak_velocity DESC
        LIMIT ?
    """, (lookback_start, limit * 2)).fetchall()

    conn.close()

    pool = []
    seen_lower = set()

    for row in list(candidate_rows) + list(trend_rows):
        kw = (row["keyword"] or "").strip()
        if not kw:
            continue
        kw_lower = kw.lower()
        if kw_lower in seen_lower:
            continue
        if len(kw) < 3:
            continue
        if not is_beauty_relevant(kw):
            continue
        seen_lower.add(kw_lower)
        pool.append(kw)
        if len(pool) >= limit:
            break

    return pool


def get_weekly_dynamic_pool(limit: int = DYNAMIC_POOL_MAX_SIZE) -> List[str]:
    """
    이번 주(ISO 주 기준)의 동적 후보 풀을 반환한다.
    이미 이번 주에 계산해둔 게 있으면 그걸 재사용하고,
    없으면 새로 계산해서 캐시한다.
    """
    week_id = get_iso_week_id()
    conn = get_db()

    row = conn.execute(
        "SELECT keywords_json FROM weekly_dynamic_pool WHERE week_id = ?",
        (week_id,)
    ).fetchone()

    if row:
        conn.close()
        try:
            return json.loads(row["keywords_json"])
        except (json.JSONDecodeError, TypeError):
            return []

    pool = build_dynamic_keyword_pool(limit)

    conn.execute("""
        INSERT INTO weekly_dynamic_pool (week_id, keywords_json, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(week_id) DO NOTHING
    """, (week_id, json.dumps(pool), get_market_now().isoformat()))
    conn.commit()
    conn.close()

    logging.info(
        "Weekly dynamic keyword pool built for %s: %d candidates -> %s",
        week_id, len(pool), pool[:10]
    )

    return pool


def interleave_hybrid_expand(
    fixed: List[str],
    dynamic: List[str],
    ratio: float = DYNAMIC_POOL_RATIO
) -> List[str]:
    """
    TikTok/Instagram처럼 '하루에 뽑는 개수'가 풀 크기와 무관하게 고정된
    경우에 쓴다. 고정 풀은 그대로 두고, 동적 키워드를 골고루 끼워 넣어서
    풀 자체를 키운다 -> 일일 호출 예산에는 영향 없음.
    """
    fixed_lower = {f.lower() for f in fixed}
    dynamic_filtered = [d for d in dynamic if d.lower() not in fixed_lower]

    if not dynamic_filtered or not fixed:
        return list(fixed)

    # fixed : dynamic 비율이 (1-ratio) : ratio 가 되도록 동적 후보 개수를 정한다.
    target_dynamic_count = max(
        1, round(len(fixed) * ratio / (1 - ratio))
    )
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


def replace_hybrid_fixed_size(
    fixed: List[str],
    dynamic: List[str],
    ratio: float = DYNAMIC_POOL_RATIO
) -> List[str]:
    """
    YouTube처럼 '풀 전체를 매일 다 쓰는' 경우에 쓴다. 호출 예산이 풀
    크기에 비례하므로, 풀 크기는 그대로 유지한 채 ratio만큼의 자리를
    동적 키워드로 교체한다 (매주 동일하게 유지 -> 같은 주 안에서는
    호출 예산이 완전히 고정된다).
    """
    fixed_lower = {f.lower() for f in fixed}
    dynamic_filtered = [d for d in dynamic if d.lower() not in fixed_lower]

    if not dynamic_filtered or not fixed:
        return list(fixed)

    replace_count = min(
        len(dynamic_filtered),
        max(1, round(len(fixed) * ratio))
    )

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

    # GitHub Actions 사이에서도 월간 API quota를 누적하기 위한 ledger
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_usage (
            usage_month TEXT NOT NULL,
            provider TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            calls INTEGER NOT NULL DEFAULT 0,
            last_called_at TEXT,
            PRIMARY KEY (usage_month, provider, endpoint)
        )
    """)

    # 하이브리드 동적 태그 파이프라인: 그 주에 뽑힌 "동적 30%" 후보를
    # 주 단위로 고정 캐시해서, 같은 주 안에서는 매일 같은 풀을 쓰도록 한다
    # (매일 다시 뽑으면 sliding window 커버리지가 흔들린다).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS weekly_dynamic_pool (
            week_id TEXT PRIMARY KEY,
            keywords_json TEXT NOT NULL,
            created_at TEXT NOT NULL
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
# 9. TikTok (tiktok-scraper7 / tikwm) - 하루 9 calls
# ============================================================

def fetch_tiktok_captions() -> List[Dict]:
    if not RAPIDAPI_KEY:
        logging.warning("RAPIDAPI_KEY missing. TikTok skipped.")
        return []

    url = "https://tiktok-scraper7.p.rapidapi.com/feed/search"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "tiktok-scraper7.p.rapidapi.com"
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
                    "keywords": query,
                    "region": "us",
                    "count": str(TIKTOK_QUERY_COUNT),
                    "cursor": "0",
                    "publish_time": "0",
                    "sort_type": "0"
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

            # tiktok-scraper7(tikwm) 정상 응답: {"code":0,"msg":"success","data":{"videos":[...]}}
            # code != 0 이면 API 자체 에러(예: 쿼터 초과, 잘못된 파라미터)이므로 스킵한다.
            if isinstance(data.get("code"), int) and data["code"] != 0:
                logging.warning(
                    "TikTok query '%s' API error code=%s msg=%s",
                    query, data.get("code"), data.get("msg")
                )
                continue

            if isinstance(data.get("data"), list):
                items = data["data"]
            elif isinstance(data.get("data"), dict):
                items = (
                    data["data"].get("videos")
                    or data["data"].get("item_list")
                    or []
                )
            else:
                # data 래핑 없이 최상위에 videos/item_list를 바로 반환하는
                # 경우에 대한 방어적 처리.
                items = (
                    data.get("videos")
                    or data.get("item_list")
                    or []
                )

            if not items:
                logging.info(
                    "TikTok query '%s' returned 0 items despite HTTP 200. "
                    "Raw response (first 300 chars): %s",
                    query, str(data)[:300]
                )

            for item in items[:TIKTOK_QUERY_COUNT]:
                # tikwm 계열은 캡션을 "title" 필드에 담는다.
                # 혹시 다른 변형 스키마가 오더라도 대응하도록 desc도 함께 체크한다.
                desc = (
                    item.get("title")
                    or item.get("desc")
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

        finally:
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
# 9b. Monthly API quota ledger
# ============================================================

def get_usage_month() -> str:
    return get_market_now().strftime("%Y-%m")


def get_api_calls(provider: str, endpoint: str, month: Optional[str] = None) -> int:
    month = month or get_usage_month()
    conn = get_db()
    row = conn.execute("""
        SELECT calls FROM api_usage
        WHERE usage_month = ? AND provider = ? AND endpoint = ?
    """, (month, provider, endpoint)).fetchone()
    conn.close()
    return int(row["calls"]) if row else 0


def reserve_provider_call(provider: str, endpoint: str, monthly_limit: int) -> bool:
    """Provider 전체 endpoint 합산 월간 quota를 원자적으로 예약한다."""
    month = get_usage_month()
    now = get_market_now().isoformat()
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""
            SELECT COALESCE(SUM(calls), 0) AS total
            FROM api_usage
            WHERE usage_month = ? AND provider = ?
        """, (month, provider)).fetchone()
        current = int(row["total"] or 0)
        if current >= monthly_limit:
            conn.rollback()
            logging.warning("%s monthly quota exhausted: %d/%d", provider, current, monthly_limit)
            return False
        conn.execute("""
            INSERT INTO api_usage(usage_month, provider, endpoint, calls, last_called_at)
            VALUES (?, ?, ?, 1, ?)
            ON CONFLICT(usage_month, provider, endpoint) DO UPDATE SET
                calls = calls + 1,
                last_called_at = excluded.last_called_at
        """, (month, provider, endpoint, now))
        conn.commit()
        logging.info("Quota reserved %s total=%d/%d endpoint=%s", provider, current + 1, monthly_limit, endpoint)
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_monthly_quota_snapshot() -> str:
    month = get_usage_month()
    conn = get_db()
    rows = conn.execute("""
        SELECT provider, endpoint, calls
        FROM api_usage
        WHERE usage_month = ?
        ORDER BY provider, endpoint
    """, (month,)).fetchall()
    conn.close()
    if not rows:
        return "No API calls recorded this month."
    return " | ".join(f"{r['provider']}/{r['endpoint']}={r['calls']}" for r in rows)


# ============================================================
# 9c. K-Signal (Korea Beauty & Fashion Velocity Feed) - 월 50 calls,
#     하루 1회. 한국 국내 랭킹 가속도 기반 "선행 지표" (서구권 SNS/아마존
#     보다 먼저 뜨는 트렌드를 포착).
#
#     주의: RapidAPI 콘솔에 Example Response가 제공되지 않아 실제 응답
#     필드명을 확정하지 못했다. 아래는 API 설명(velocity/acceleration/
#     score/confidence/source_link)을 근거로 한 최선의 추정 파싱이며,
#     실제 실행 후 로그의 raw response를 확인해 필드명이 다르면 그대로
#     알려주면 파싱 로직을 맞춘다.
# ============================================================

def _extract_k_signal_items(data) -> List[Dict]:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("signals", "data", "results", "items"):
        val = data.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            for inner in ("signals", "items", "results"):
                if isinstance(val.get(inner), list):
                    return val[inner]
    return []


def _parse_k_signal_item(item: Dict) -> Optional[Dict]:
    product = str(item.get("product_name") or item.get("sku_name") or item.get("title") or item.get("name") or item.get("product") or "").strip()
    if not product:
        return None
    brand = str(item.get("brand") or "").strip()
    source = str(item.get("source") or item.get("platform") or item.get("marketplace") or "").strip()
    velocity = item.get("velocity")
    acceleration = item.get("acceleration")
    score = item.get("score") if item.get("score") is not None else item.get("signal_score")
    confidence = item.get("confidence") if item.get("confidence") is not None else item.get("confidence_score")
    url = str(item.get("source_link") or item.get("url") or "").strip()
    label = product if not brand or brand.lower() in product.lower() else f"{brand} {product}"
    details=[]
    for k,v in (("velocity",velocity),("accel",acceleration),("score",score),("confidence",confidence)):
        if v is not None: details.append(f"{k}={v}")
    text=label + ((" (" + ", ".join(details) + ")") if details else "")
    if url: text += f" [{url}]"
    return {
        "platform":"k_signal", "query":source, "tag":"", "region":"KR",
        "text":text.replace("\n"," ")[:220],
        "velocity":velocity, "acceleration":acceleration,
        "score":score, "confidence":confidence, "product":label
    }


def fetch_k_signal() -> List[Dict]:
    if not RAPIDAPI_KEY:
        logging.warning("RAPIDAPI_KEY missing. K-Signal skipped.")
        return []
    endpoint="/v1/signals"
    if not reserve_provider_call("k_signal", endpoint, K_SIGNAL_MONTHLY_LIMIT):
        return []
    url="https://k-signal-korea-beauty-fashion-velocity-feed.p.rapidapi.com/v1/signals"
    headers={"x-rapidapi-key":RAPIDAPI_KEY,"x-rapidapi-host":"k-signal-korea-beauty-fashion-velocity-feed.p.rapidapi.com"}
    try:
        res=k_signal_session.get(url,headers=headers,params={"limit":str(K_SIGNAL_FETCH_LIMIT),"min_confidence":str(K_SIGNAL_MIN_CONFIDENCE)},timeout=K_SIGNAL_TIMEOUT_SECONDS)
        if res.status_code!=200:
            logging.warning("K-Signal /signals HTTP %s: %s",res.status_code,res.text[:300])
            return []
        items=_extract_k_signal_items(res.json())
        results=[]
        for item in items[:K_SIGNAL_FETCH_LIMIT]:
            if isinstance(item,dict):
                parsed=_parse_k_signal_item(item)
                if parsed: results.append(parsed)
        logging.info("K-Signal /signals samples=%d; quota=%s",len(results),get_monthly_quota_snapshot())
        return results
    except Exception as e:
        logging.error("K-Signal /signals failed: %s",e)
        return []


def k_signal_needs_teaser(signals: List[Dict]) -> bool:
    for s in signals:
        try:
            confidence=float(s.get("confidence")) if s.get("confidence") is not None else 0.0
            accel=float(s.get("acceleration")) if s.get("acceleration") is not None else None
            velocity=float(s.get("velocity")) if s.get("velocity") is not None else None
            if confidence >= 0.75 and ((accel is not None and accel >= 20) or (velocity is not None and velocity >= 50)):
                return True
        except (TypeError,ValueError):
            continue
    return False


def fetch_k_signal_teaser(signals: List[Dict]) -> List[Dict]:
    if not K_SIGNAL_TEASER_ENABLED or not signals or not k_signal_needs_teaser(signals):
        return []
    # teaser는 별도 19회 reserve를 넘지 않으면서 K-Signal 전체 50회 안에서만 사용한다.
    endpoint="/v1/signals/teaser"
    if get_api_calls("k_signal", endpoint) >= K_SIGNAL_TEASER_MAX_MONTHLY:
        return []
    if not reserve_provider_call("k_signal", endpoint, K_SIGNAL_MONTHLY_LIMIT):
        return []
    url="https://k-signal-korea-beauty-fashion-velocity-feed.p.rapidapi.com/v1/signals/teaser"
    headers={"x-rapidapi-key":RAPIDAPI_KEY,"x-rapidapi-host":"k-signal-korea-beauty-fashion-velocity-feed.p.rapidapi.com"}
    try:
        res=session.get(url,headers=headers,timeout=15)
        if res.status_code!=200:
            logging.warning("K-Signal /teaser HTTP %s: %s",res.status_code,res.text[:300])
            return []
        results=[]
        for item in _extract_k_signal_items(res.json())[:20]:
            if isinstance(item,dict):
                parsed=_parse_k_signal_item(item)
                if parsed: results.append(parsed)
        logging.info("K-Signal /teaser samples=%d; quota=%s",len(results),get_monthly_quota_snapshot())
        return results
    except Exception as e:
        logging.error("K-Signal /teaser failed: %s",e)
        return []


# ============================================================
# 9d. YouTube Data API v3 - 공식 API
# ============================================================

def _youtube_query_window() -> List[str]:
    """
    하루 쿼리 전체를 NL/DE에 각각 적용한다.
    풀 크기가 곧 API 호출 예산과 직결되므로(94~96 calls/day 전제),
    풀 크기는 고정한 채 ratio만큼만 동적 키워드로 교체한다.
    """
    hybrid_pool = replace_hybrid_fixed_size(
        YOUTUBE_QUERY_ROTATION, get_weekly_dynamic_pool()
    )
    if not hybrid_pool:
        return []
    n = len(hybrid_pool)
    start = rotation_index(n)
    return [hybrid_pool[(start + i) % n] for i in range(n)]


def fetch_youtube_trends() -> List[Dict]:
    """
    공식 YouTube Data API v3만 사용한다.

    96 search.list 호출(48 queries x NL/DE) + 6 videos.list 호출로
    기본 10,000 units/day 중 9,406 units를 사용한다.
    search 결과는 최근 7일 영상만 수집하고, videos.list로 일부 영상의
    조회수/좋아요/댓글수를 보강한다.
    """
    if not YOUTUBE_API_KEY:
        logging.warning("YOUTUBE_API_KEY missing. YouTube skipped.")
        return []

    search_url = "https://www.googleapis.com/youtube/v3/search"
    videos_url = "https://www.googleapis.com/youtube/v3/videos"
    headers = {"Accept": "application/json"}
    queries = _youtube_query_window()
    regions = ["NL", "DE"]
    published_after = (
        get_market_now() - datetime.timedelta(days=YOUTUBE_LOOKBACK_DAYS)
    ).astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    results = []
    video_ids = []
    seen_ids = set()
    search_calls = 0
    stats_calls = 0
    quota_exhausted = False

    for region in regions:
        for query in queries:
            if search_calls >= YOUTUBE_SEARCH_CALLS_PER_DAY or quota_exhausted:
                break
            try:
                res = session.get(
                    search_url,
                    headers=headers,
                    params={
                        "key": YOUTUBE_API_KEY,
                        "part": "snippet",
                        "q": query,
                        "type": "video",
                        "maxResults": str(YOUTUBE_SEARCH_RESULTS_PER_CALL),
                        "order": "date",
                        "publishedAfter": published_after,
                        "regionCode": region,
                        "safeSearch": "none"
                    },
                    timeout=15
                )
                search_calls += 1

                if res.status_code != 200:
                    logging.warning(
                        "YouTube search '%s' [%s] HTTP %s: %s",
                        query, region, res.status_code, res.text[:300]
                    )
                    if res.status_code == 403 and "quotaExceeded" in res.text:
                        quota_exhausted = True
                    continue

                data = res.json()
                for item in data.get("items", []):
                    video_id = str(item.get("id", {}).get("videoId") or "").strip()
                    snippet = item.get("snippet", {}) or {}
                    title = str(snippet.get("title") or "").strip()
                    description = str(snippet.get("description") or "").strip()
                    if not video_id or not title or video_id in seen_ids:
                        continue
                    if not is_beauty_relevant(title + " " + description):
                        continue
                    seen_ids.add(video_id)
                    video_ids.append(video_id)
                    results.append({
                        "platform": "youtube",
                        "query": query,
                        "tag": "",
                        "region": region,
                        "text": title.replace("\n", " ")[:220],
                        "video_id": video_id,
                        "published_at": snippet.get("publishedAt")
                    })

            except Exception as e:
                logging.error(
                    "YouTube search '%s' [%s] failed: %s", query, region, e
                )

            time.sleep(0.15)

        if search_calls >= YOUTUBE_SEARCH_CALLS_PER_DAY or quota_exhausted:
            break

    # search 결과에서 중복 제거된 영상 중 최대 300개에 대해 통계를 보강한다.
    stats_ids = video_ids[:YOUTUBE_VIDEO_STATS_CALLS_PER_DAY * YOUTUBE_VIDEO_STATS_BATCH_SIZE]
    stats_by_id = {}

    for start in range(0, len(stats_ids), YOUTUBE_VIDEO_STATS_BATCH_SIZE):
        if stats_calls >= YOUTUBE_VIDEO_STATS_CALLS_PER_DAY or quota_exhausted:
            break
        batch = stats_ids[start:start + YOUTUBE_VIDEO_STATS_BATCH_SIZE]
        try:
            res = session.get(
                videos_url,
                headers=headers,
                params={
                    "key": YOUTUBE_API_KEY,
                    "part": "statistics,snippet",
                    "id": ",".join(batch),
                    "maxResults": str(YOUTUBE_VIDEO_STATS_BATCH_SIZE)
                },
                timeout=15
            )
            stats_calls += 1
            if res.status_code != 200:
                logging.warning(
                    "YouTube videos.list HTTP %s: %s", res.status_code, res.text[:300]
                )
                if res.status_code == 403 and "quotaExceeded" in res.text:
                    quota_exhausted = True
                continue

            for item in res.json().get("items", []):
                vid = item.get("id")
                st = item.get("statistics", {}) or {}
                stats_by_id[vid] = {
                    "views": st.get("viewCount"),
                    "likes": st.get("likeCount"),
                    "comments": st.get("commentCount")
                }
        except Exception as e:
            logging.error("YouTube videos.list failed: %s", e)
        time.sleep(0.15)

    for item in results:
        stats = stats_by_id.get(item.get("video_id"), {})
        item["text"] = (
            item["text"]
            + f" [views={stats.get('views','NA')}, likes={stats.get('likes','NA')}, comments={stats.get('comments','NA')}]"
        )[:320]

    logging.info(
        "YouTube calls search=%d/%d, videos=%d/%d, unique valid samples=%d, quota_used_est=%d/10000",
        search_calls,
        YOUTUBE_SEARCH_CALLS_PER_DAY,
        stats_calls,
        YOUTUBE_VIDEO_STATS_CALLS_PER_DAY,
        len(results),
        search_calls * 100 + stats_calls
    )
    return results


# ============================================================
# 10. Instagram - Apify official maintained Actor
# ============================================================

APIFY_ACTOR_RUN_URL = (
    "https://api.apify.com/v2/acts/"
    "apify~instagram-scraper/run-sync-get-dataset-items"
)


def get_apify_monthly_results() -> int:
    month = get_usage_month()
    conn = get_db()
    row = conn.execute("""
        SELECT COALESCE(SUM(calls), 0) AS total
        FROM api_usage
        WHERE usage_month = ? AND provider = 'apify_instagram'
    """, (month,)).fetchone()
    conn.close()
    return int(row["total"] or 0)


def get_apify_daily_results() -> int:
    month = get_usage_month()
    day_endpoint = f"results:{get_today_iso()}"
    return get_api_calls("apify_instagram", day_endpoint, month)


def add_apify_result_usage(count: int) -> None:
    if count <= 0:
        return
    month = get_usage_month()
    now = get_market_now().isoformat()
    endpoint = f"results:{get_today_iso()}"
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            INSERT INTO api_usage(usage_month, provider, endpoint, calls, last_called_at)
            VALUES (?, 'apify_instagram', ?, ?, ?)
            ON CONFLICT(usage_month, provider, endpoint) DO UPDATE SET
                calls = calls + excluded.calls,
                last_called_at = excluded.last_called_at
        """, (month, endpoint, count, now))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_today_apify_instagram_tags() -> List[str]:
    # 하루 5개씩 순환하여 broad discovery와 ingredient/product discovery를 교차한다.
    # (기존 2개 -> 4개 -> 5개: 니치 해시태그일수록 3일 이내 후보 게시물 자체가 적어
    # resultsLimit을 다 못 채우는 문제가 있었음. 태그 다양성을 늘려 후보 풀을 넓힌다.)
    # 고정 INSTAGRAM_ROTATION(70%) + 이번 주 동적 후보 풀(30%)을 섞은 하이브리드
    # 풀에서 뽑는다. 하루 5개라는 예산은 풀 크기와 무관하므로 그대로 확장한다.
    pool = interleave_hybrid_expand(
        INSTAGRAM_ROTATION, get_weekly_dynamic_pool()
    )
    if not pool:
        return []
    idx = rotation_index(len(pool))
    return [pool[(idx + i) % len(pool)] for i in range(5)]


def fetch_instagram_apify() -> List[Dict]:
    if not APIFY_INSTAGRAM_ENABLED:
        logging.info("Apify Instagram disabled.")
        return []
    if not APIFY_TOKEN:
        logging.warning("APIFY_TOKEN missing. Instagram skipped.")
        return []

    used = get_apify_monthly_results()
    used_today = get_apify_daily_results()
    daily_remaining = APIFY_INSTAGRAM_DAILY_RESULT_LIMIT - used_today
    remaining = min(
        APIFY_INSTAGRAM_MONTHLY_RESULT_LIMIT - used,
        daily_remaining
    )
    if remaining <= 0:
        logging.warning(
            "Apify Instagram result cap reached: month=%d/%d today=%d/%d. Instagram collection stopped.",
            used, APIFY_INSTAGRAM_MONTHLY_RESULT_LIMIT,
            used_today, APIFY_INSTAGRAM_DAILY_RESULT_LIMIT
        )
        return []

    tags = get_today_apify_instagram_tags()
    # 2026-08-13 실행 로그에서 실측으로 확인됨: resultsLimit=58(합산 상한이라고
    # 가정했던 값)로 요청했는데 실제로는 84건이 돌아왔다(태그 5개, 평균
    # 태그당 ~17건). 즉 이 Actor의 resultsLimit은 directUrls 전체에 대한
    # 합산 상한이 아니라 URL(태그)별 상한이다 - "1회 호출 = 합산 총량"이라는
    # 이전 가정은 틀렸다. 이 상태로 두면 하루/월 예산을 실제로 초과할 수 있어
    # (이번에도 하루 캡 58을 84로 넘김) 태그 개수로 다시 나눠서, 태그별 상한 x
    # 태그 개수의 합이 remaining을 절대 넘지 않도록 한다. 이렇게 하면 실제
    # 의미가 "합산"이든 "태그별"이든 상관없이 항상 안전하다.
    results_limit = max(1, remaining // max(1, len(tags)))
    if remaining < 1:
        logging.warning("Apify Instagram remaining result budget too small: %d", remaining)
        return []

    input_payload = {
        "directUrls": [
            f"https://www.instagram.com/explore/tags/{tag}/"
            for tag in tags
        ],
        "resultsType": "posts",
        "resultsLimit": results_limit,
        "onlyPostsNewerThan": "3 days",
        "addParentData": True
    }
    headers = {
        "Authorization": f"Bearer {APIFY_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        logging.info(
            "Fetching Instagram via Apify actor=%s tags=%s limit=%d remaining=%d",
            APIFY_INSTAGRAM_ACTOR, tags, results_limit, remaining
        )
        res = apify_session.post(
            APIFY_ACTOR_RUN_URL,
            headers=headers,
            json=input_payload,
            params={"token": APIFY_TOKEN},
            timeout=120
        )
        # Apify의 run-sync-get-dataset-items 엔드포인트는 정상 처리 시에도
        # 200이 아니라 201을 반환하는 경우가 있다(실제 로그에서 201 + 정상
        # dataset JSON이 함께 온 사례 확인). 200만 성공으로 인정하면 정상
        # 수집분까지 버려지고, 이미 청구된 Apify 비용만 낭비된다. 2xx 전체를
        # 성공으로 간주하고, 실패는 4xx/5xx만으로 판단한다.
        if not (200 <= res.status_code < 300):
            logging.warning(
                "Apify Instagram HTTP %s: %s",
                res.status_code, res.text[:500]
            )
            return []

        data = res.json()
        if not isinstance(data, list):
            logging.warning("Apify Instagram returned non-list dataset payload.")
            return []

        results = []
        seen_ids = set()
        for item in data:
            if not isinstance(item, dict):
                continue
            shortcode = str(item.get("shortCode") or item.get("shortcode") or item.get("id") or "").strip()
            if shortcode and shortcode in seen_ids:
                continue
            if shortcode:
                seen_ids.add(shortcode)

            caption = str(item.get("caption") or "").strip()
            hashtags = item.get("hashtags") or []
            if isinstance(hashtags, list):
                hashtag_text = " ".join(
                    "#" + str(x).lstrip("#") for x in hashtags if str(x).strip()
                )
            else:
                hashtag_text = str(hashtags)
            text = (caption + (" " + hashtag_text if hashtag_text else "")).strip()
            if len(text) <= 10:
                continue

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
            if isinstance(parent, dict):
                source_tag = str(parent.get("hashtag") or parent.get("tag") or "").strip().lstrip("#")
            if not source_tag and tags:
                source_tag = tags[0]

            results.append({
                "platform": "instagram",
                "query": "",
                "tag": source_tag,
                "region": "EU",
                "text": text.replace("\n", " ")[:260],
                "likes": likes,
                "comments": comments,
                "views": views,
                "instagram_id": shortcode
            })

        # 실제 반환 결과만 quota ledger에 기록한다.
        add_apify_result_usage(len(data))
        logging.info(
            "Apify Instagram results=%d valid=%d; quota month=%d/%d today=%d/%d",
            len(data), len(results), get_apify_monthly_results(),
            APIFY_INSTAGRAM_MONTHLY_RESULT_LIMIT, get_apify_daily_results(),
            APIFY_INSTAGRAM_DAILY_RESULT_LIMIT
        )
        return results
    except requests.exceptions.Timeout:
        logging.warning("Apify Instagram timed out; Instagram skipped for today.")
        return []
    except Exception as e:
        logging.error("Apify Instagram failed: %s", e)
        return []


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

def get_keyword_platforms(keyword: str, signal_date: str) -> str:
    """Return comma-separated platform list for a keyword on a given date."""
    conn = get_db()
    rows = conn.execute("""
        SELECT platform, SUM(mentions) AS m
        FROM keyword_daily
        WHERE keyword = ?
          AND signal_date = ?
          AND mentions > 0
        GROUP BY platform
        ORDER BY m DESC
    """, (keyword, signal_date)).fetchall()
    conn.close()

    if not rows:
        return "none"
    return ", ".join(f"{r['platform']}({r['m']})" for r in rows)


def build_trend_summary(scores: List[Dict], signal_date: str = None) -> str:
    if not scores:
        return "No quantitative social trend score available today."

    lines = []

    for rank, item in enumerate(scores[:10], start=1):
        velocity_text = (
            f"{item['velocity'] * 100:+.1f}%"
            if item["has_history"]
            else "INSUFFICIENT_HISTORY"
        )

        platforms_text = "unknown"
        if signal_date:
            platforms_text = get_keyword_platforms(item["keyword"], signal_date)

        lines.append(
            f"{rank}. {item['keyword']} | "
            f"status={item['status']} | "
            f"mentions={item['today_mentions']} | "
            f"platforms=[{platforms_text}] | "
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

    # 404는 잘못된/폐기된 모델명일 가능성이 높다. fallback 1회로 보고서 전체 실패를 막는다.
    if res.status_code == 404 and GEMINI_MODEL != GEMINI_FALLBACK_MODEL:
        fallback_url = (
            "https://generativelanguage.googleapis.com/"
            f"v1beta/models/{GEMINI_FALLBACK_MODEL}:generateContent"
        )
        logging.warning(
            "Gemini model %s returned 404; retrying with %s",
            GEMINI_MODEL, GEMINI_FALLBACK_MODEL
        )
        res = session.post(
            fallback_url,
            headers=headers,
            json=payload,
            timeout=60
        )

    if res.status_code != 200:
        logging.error(
            "Gemini API HTTP %s: %s",
            res.status_code, res.text[:1000]
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
You are a market-intelligence analyst for a Korean cosmetics (K-Beauty)
company that sells into the Netherlands and Western Europe. Your job is
NOT to write retail merchandising advice or shelf-display concepts.
Your sole purpose is to detect and explain market TRENDS and FLOWS:
what is rising, what is transferring from Korea to the West, what is
sustained vs temporary noise, and where regional differences appear.

Generate a DAILY K-BEAUTY / COSMETICS MARKET TREND & FLOW REPORT.

{data_status}

IMPORTANT DATA MODEL:
1. TikTok = early viral / discovery signal.
2. Instagram = secondary social / content confirmation.
3. Amazon = purchase-stage signal (commercial demand already present).
4. Google = independent search-market discovery.
5. K-Signal = Korea-domestic UPSTREAM signal (Olive Young, Musinsa,
   Zigzag, Glowpick, Hwahae ranking velocity). A K-Signal-only item is
   an early lead still mostly inside Korea. If the same item also appears
   on Western TikTok / Instagram / Amazon / Google, call out the
   Korea → West transfer explicitly — this is one of the highest-value
   insights.
6. YouTube = longer-form interest / review confirmation (sustained
   interest, not pure virality).
7. Single-platform weak signals are not confirmed trends.
8. Google Autocomplete candidates are NOT volume scores. Do not invent
   numbers. Do not claim direct comparability of relative scores across
   different comparison groups.

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

Internally grade each major signal with a star rating (do not print the
tier name):
- ★★★ : cross-platform social + independent Google and/or Amazon support
- ★★  : only one strong source (Google intent OR solid social/Amazon)
- ★   : weak / single / flat signal — watch only

CRITICAL RULES:
- Star rating alone is never enough. Every TOP signal must include an
  explicit data-analysis sentence naming the platforms where it appeared
  (use the platforms=[...] field and LIVE SOCIAL SAMPLES). Never invent
  a platform absent from the data.
- Prioritize FLOW over static ranking: velocity, persistence,
  Korea→West transfer, and cross-platform confirmation.
- Distinguish measured evidence from hypothesis.
- Do not overstate small samples. These are directional signals.

Focus geography & themes:
- Netherlands / Western Europe
- Germany
- Arabic / Middle Eastern customer signals (if present in data)
- Ingredients, product formats, and commercial-intent shifts
- K-Beauty specific movements

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
Do NOT include shelf/display/bundle concepts.
Do NOT write detailed "order this SKU" retail sourcing plans.
Keep any implication short and trend-focused.

--- SECTION 1 ---
Title: 🌐 글로벌 화장품 & 스킨케어 시장 데일리 트렌드 리포트

1. 📈 오늘의 TOP 5 트렌드 시그널
For every signal:
- Title + star rating on the same line
  (e.g. "① 여드름 & BHA/살리실산 모공 솔루션 ★★★")
- Right under it: short data-analysis paragraph stating WHERE it was
  mentioned (platforms from platforms=[...] and samples) and evidence
  strength (mentions / cross-platform / velocity).
- 1-2 sentences of trend interpretation (not retail merchandising advice).
Do NOT use bracket labels like [CONFIRMED].
Do NOT output only stars without source analysis.

2. 🔄 흐름 & 가속도 분석
Explain today's movement:
- Which signals are accelerating vs already flat/persistent
- Any clear Korea (K-Signal) → Western platforms transfer
- Cross-platform confirmation strength overall
- What the combination of sources implies about the current phase
  of the trend (early discovery / commercial demand / sustained)

3. 👀 워치리스트 & 노이즈 구분
- Early or weak signals that are rising fast enough to keep watching
- Signals that look like one-day spikes or noise
- Any notable regional differences (NL/Western Europe vs Germany vs
  Arabic-related signals) if the data supports it

4. 📌 짧은 시사점 (2-4문장)
Trend-monitoring implications only. No shelf concepts, no detailed
sourcing/marketing plans. Example tone: "PDRN 관련 신호는 한국에서
이미 강했고 오늘 서구 SNS에서도 나타나기 시작했다 — 전이 초기 단계로
보고 지속 여부를 추적할 가치가 있다."

===SPLIT_SECTION===

--- SECTION 2 ---
Title: 🌐 التقرير اليومي العالمي لاتجاهات مستحضرات التجميل والعناية بالبشرة

1. 📈 أهم 5 إشارات للاتجاهات اليوم
Same structure as Korean section 1 (title + star, platform/source
analysis, short trend interpretation). No stars-only output.

2. 🔄 تحليل التدفق والتسارع
Same content focus as Korean section 2 (acceleration, Korea→West
transfer, cross-platform strength, trend phase).

3. 👀 قائمة المراقبة مقابل الضوضاء
Same content focus as Korean section 3 (watchlist, noise, regional
differences if data supports).

4. 📌 ملاحظات قصيرة
Trend-monitoring implications only (2-4 sentences). No shelf or
detailed sourcing advice.

===SPLIT_SECTION===

--- SECTION 3 ---
Title: 🌐 GLOBAL COSMETICS & SKINCARE MARKET DAILY TREND REPORT

1. 📈 TOP 5 TREND SIGNALS TODAY
Same structure as Korean section 1: title + star, explicit platform/
source analysis from the data, short trend interpretation.
Do NOT output only the star rating.

2. 🔄 FLOW & ACCELERATION ANALYSIS
- Accelerating vs flat/persistent signals
- Korea (K-Signal) → Western transfer if present
- Overall cross-platform confirmation
- What this implies about the current phase of the trend

3. 👀 WATCHLIST vs NOISE
- Early/weak but rising signals worth tracking
- Likely one-day spikes / noise
- Regional differences (NL/Western Europe, Germany, Arabic-related)
  only when supported by the data

4. 📌 SHORT IMPLICATIONS
2-4 sentences of trend-monitoring implications only.
No shelf/display concepts and no detailed retailer sourcing plans.
"""

    return call_gemini_api(prompt)


# ============================================================
# 16b. Weekly Rollup (주말 요약)
# ============================================================

WEEKLY_SUMMARY_WEEKDAY = 5  # Python date.weekday(): Mon=0 ... Sat=5, Sun=6


def is_weekly_summary_day() -> bool:
    return get_market_now().date().weekday() == WEEKLY_SUMMARY_WEEKDAY


def is_monthly_summary_day() -> bool:
    """그 달의 마지막 날에만 True (매일 도는 워크플로우 기준)."""
    today = get_market_now().date()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return today.day == last_day


def get_past_month_dates(signal_date: str) -> List[str]:
    """
    이번 달 1일부터 오늘(=월말)까지의 날짜 리스트를 반환한다.
    주간 롤업과 달리 요일 제한 없이 그 달에 실제로 수집된 모든 날짜를 포함한다.
    """
    today = datetime.date.fromisoformat(signal_date)
    first_day = today.replace(day=1)
    days_in_month = (today - first_day).days + 1
    return [
        (first_day + datetime.timedelta(days=i)).isoformat()
        for i in range(days_in_month)
    ]


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
You are a market-intelligence analyst for a Korean cosmetics (K-Beauty)
company selling into the Netherlands and Western Europe. Focus on TRENDS
and FLOWS — not retail merchandising or detailed sourcing plans.

Generate a WEEKLY K-BEAUTY / COSMETICS MARKET TREND & FLOW ROLLUP covering
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
- Which platform contributed the most this week, and what that implies
  (Amazon-heavy = purchase-stage; TikTok-heavy = early viral; etc.)
- Any Korea → West transfer patterns if visible in the data
- Keywords that spiked once but did not persist (low active_days,
  high peak_score) should be flagged as noise, not a trend.

Do not overstate small samples. Be honest about data limitations.
Do NOT write shelf/display concepts or detailed "order this SKU" plans.

========================================================
STRICT LANGUAGE & ORDER RULES
========================================================

The report MUST contain exactly THREE sections separated by
===SPLIT_SECTION===, in this order: KOREAN, ARABIC, ENGLISH.
Do not include Dutch or German.

--- SECTION 1 ---
Title: 📅 주간 화장품 & 스킨케어 트렌드 요약 ({date_list[0]} ~ {date_list[-1]})

1. 🏆 이번 주 TOP 5 지속 트렌드
2. 📊 플랫폼별 기여도 & 흐름 분석
3. ⚠️ 일시적 스파이크(노이즈) 주의 키워드
4. 📌 다음 주 추적 포인트 (트렌드 모니터링 관점, 2-4문장)

===SPLIT_SECTION===

--- SECTION 2 ---
Title: 📅 ملخص أسبوعي لاتجاهات مستحضرات التجميل والعناية بالبشرة

1. 🏆 أفضل 5 اتجاهات مستمرة هذا الأسبوع
2. 📊 تحليل مساهمة المنصات والتدفق
3. ⚠️ كلمات مفتاحية قد تكون ضجة مؤقتة فقط
4. 📌 نقاط المتابعة للأسبوع القادم

===SPLIT_SECTION===

--- SECTION 3 ---
Title: 📅 WEEKLY COSMETICS & SKINCARE TREND ROLLUP ({date_list[0]} ~ {date_list[-1]})

1. 🏆 TOP 5 PERSISTENT TRENDS THIS WEEK
2. 📊 PLATFORM CONTRIBUTION & FLOW ANALYSIS
3. ⚠️ KEYWORDS THAT LOOK LIKE ONE-DAY NOISE
4. 📌 NEXT-WEEK TRACKING POINTS (trend-monitoring only, 2-4 sentences)
"""

    return call_gemini_api(prompt)


# ============================================================
# 16c. Monthly Rollup (월말 요약)
# ============================================================

def build_monthly_rollup(date_list: List[str]) -> Tuple[str, str]:
    """
    trend_scores와 keyword_daily를 월 단위로 집계해서
    (키워드 랭킹 텍스트, 플랫폼별 집계 텍스트) 튜플로 반환한다.
    build_weekly_rollup과 동일한 구조이지만 집계 기간이 그 달 전체이고,
    상위 30개까지 보여준다 (월간은 노출 후보가 더 많을 수 있어서).
    """
    if not date_list:
        return "No data.", "No data."

    conn = get_db()
    placeholders = ",".join("?" for _ in date_list)
    total_days = len(date_list)

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
        LIMIT 30
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
            f"active_days={row['active_days']}/{total_days}"
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
        else "No monthly keyword data."
    )
    platform_text = (
        "\n".join(platform_lines)
        if platform_lines
        else "No monthly platform data."
    )

    return keyword_text, platform_text


def generate_monthly_summary_report(
    date_list: List[str],
    keyword_rollup: str,
    platform_rollup: str
) -> str:
    total_days = len(date_list)

    prompt = f"""
You are a market-intelligence analyst for a Korean cosmetics (K-Beauty)
company selling into the Netherlands and Western Europe. Focus on TRENDS
and FLOWS — not retail merchandising, shelf concepts, or detailed
sourcing plans.

Generate a MONTHLY K-BEAUTY / COSMETICS MARKET TREND & FLOW ROLLUP covering
{date_list[0]} to {date_list[-1]} ({total_days} days), based on
aggregated quantitative trend scores collected across the whole month.

MONTHLY KEYWORD RANKING (by aggregated trend_score, {total_days}-day window):
{keyword_rollup}

MONTHLY PLATFORM BREAKDOWN (TikTok / Amazon / Instagram / Google):
{platform_rollup}

========================================================
ANALYSIS TASK
========================================================

Summarize the month's overall direction:
- Which keywords held the strongest, most persistent signal across
  the WHOLE month (high active_days relative to {total_days}, not
  just a few good days)?
- Which platform contributed the most this month, and what that implies
  (Amazon-heavy = purchase-stage already converting; TikTok-heavy =
  early viral still unproven commercially).
- Any visible Korea → West transfer patterns over the month.
- Keywords that spiked briefly but did not persist (low active_days
  relative to {total_days}, high peak_score) — flag as noise/hype.
- Keywords that look fading (strong earlier, weak recently) versus
  accelerating (weak earlier, strong recently), only if the data
  supports that read. Do not invent trajectories.

Do not overstate small samples. Be honest about data limitations.
Do NOT write shelf/display concepts or detailed "order this SKU" plans.

========================================================
STRICT LANGUAGE & ORDER RULES
========================================================

The report MUST contain exactly THREE sections separated by
===SPLIT_SECTION===, in this order: KOREAN, ARABIC, ENGLISH.
Do not include Dutch or German.

--- SECTION 1 ---
Title: 🗓️ 월간 화장품 & 스킨케어 트렌드 요약 ({date_list[0]} ~ {date_list[-1]})

1. 🏆 이달의 TOP 5 지속 트렌드 (별점 ★★★/★★/★ 로 신뢰도 표시)
2. 📊 플랫폼별 기여도 & 흐름 분석
3. 📉 반짝 스파이크였던 노이즈 키워드
4. 📈 상승세 vs 하락세 키워드 (데이터로 확인되는 경우만)
5. 📌 다음 달 추적 포인트 (트렌드 모니터링 관점, 2-4문장)

===SPLIT_SECTION===

--- SECTION 2 ---
Title: 🗓️ ملخص شهري لاتجاهات مستحضرات التجميل والعناية بالبشرة

1. 🏆 أفضل 5 اتجاهات مستمرة هذا الشهر (تقييم بالنجوم ★★★/★★/★)
2. 📊 تحليل مساهمة المنصات والتدفق
3. 📉 كلمات مفتاحية كانت ضجة مؤقتة فقط
4. 📈 اتجاهات صاعدة مقابل اتجاهات هابطة
5. 📌 نقاط المتابعة للشهر القادم

===SPLIT_SECTION===

--- SECTION 3 ---
Title: 🗓️ MONTHLY COSMETICS & SKINCARE TREND ROLLUP ({date_list[0]} ~ {date_list[-1]})

1. 🏆 TOP 5 PERSISTENT TRENDS THIS MONTH (star rating ★★★/★★/★)
2. 📊 PLATFORM CONTRIBUTION & FLOW ANALYSIS
3. 📉 KEYWORDS THAT LOOK LIKE BRIEF NOISE/HYPE
4. 📈 RISING VS FADING KEYWORDS (only if the data supports it)
5. 📌 NEXT-MONTH TRACKING POINTS (trend-monitoring only, 2-4 sentences)
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
            "This week's dynamic keyword pool (%s): %s",
            get_iso_week_id(), get_weekly_dynamic_pool()
        )
        logging.info(
            "Today's TikTok queries: %s",
            get_today_tiktok_queries()
        )
        logging.info(
            "Today's Instagram Apify tags: %s",
            get_today_apify_instagram_tags()
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

        for region, items in google_data.items():
            logging.info(
                "Google autocomplete accepted signals [%s]: %d",
                region, len(items)
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

        logging.info("Fetching Instagram via Apify...")
        instagram_signals = fetch_instagram_apify()

        logging.info("Fetching K-Signal /v1/signals...")
        k_signal_signals = fetch_k_signal()
        k_signal_teaser = []  # timeout/추가 호출을 피하기 위해 teaser endpoint는 사용하지 않음

        logging.info("Fetching YouTube via official Data API v3...")
        youtube_signals = fetch_youtube_trends()

        all_signals = (
            tiktok_signals +
            amazon_signals +
            instagram_signals +
            k_signal_signals +
            k_signal_teaser +
            youtube_signals
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
            trend_scores,
            signal_date=signal_date
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

        # ----------------------------------------------------
        # 9. Monthly rollup (매월 말일에만 추가 발송, 데이터 수집은 계속됨)
        # ----------------------------------------------------
        if is_monthly_summary_day():
            try:
                logging.info(
                    "Today is the monthly summary day - "
                    "building monthly rollup..."
                )

                month_dates = get_past_month_dates(signal_date)
                keyword_rollup, platform_rollup = build_monthly_rollup(
                    month_dates
                )

                monthly_report = generate_monthly_summary_report(
                    month_dates, keyword_rollup, platform_rollup
                )

                monthly_sections = [
                    section.strip()
                    for section
                    in monthly_report.split("===SPLIT_SECTION===")
                    if section.strip()
                ]

                for index, section in enumerate(monthly_sections):
                    logging.info(
                        "Sending monthly report section %d/%d",
                        index + 1, len(monthly_sections)
                    )
                    send_telegram_message(section)

            except Exception as e:
                logging.error(
                    "Monthly rollup failed (daily report already sent): %s",
                    e, exc_info=True
                )
                send_telegram_error(
                    f"Monthly rollup failed: {str(e)} "
                    "(daily report was sent successfully)"
                )

        logging.info("Monthly API quota snapshot: %s", get_monthly_quota_snapshot())
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
