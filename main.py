import os
import sys
import re
import json
import sqlite3
import logging
import datetime
import math
from collections import Counter
from typing import List, Dict, Tuple
from zoneinfo import ZoneInfo

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

DB_PATH = os.getenv(
    "TREND_DB_PATH",
    "beauty_trends.db"
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")


# ============================================================
# 1. HTTP Session
# ============================================================

def get_robust_session() -> requests.Session:
    """
    429는 재시도하지 않는다.
    무료 API quota 보호를 위해 rate-limit 응답을 재호출하지 않는다.
    """

    session = requests.Session()

    retries = Retry(
        total=2,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False
    )

    session.mount(
        "https://",
        HTTPAdapter(max_retries=retries)
    )

    return session


session = get_robust_session()


# ============================================================
# 2. Beauty Vocabulary
# ============================================================

INGREDIENTS_VOCAB = [
    "pdrn",
    "retinol",
    "cica",
    "niacinamide",
    "spicule",
    "reedle",
    "reedle shot",
    "peptide",
    "exosome",
    "exosomes",
    "azelaic",
    "salicylic",
    "panthenol",
    "hyaluronic",
    "collagen",
    "ceramide",
    "centella",
    "sunscreen",
    "sunstick",
    "sun stick",
    "glass skin",
    "barrier",
    "dark spot",
    "dark spots",
    "hyperpigmentation",
    "cleanser",
    "toner",
    "serum",
    "moisturizer",
    "moisturiser",
    "essence",
    "ampoule",
    "mask",
    "retinal",
    "bakuchiol",
    "vitamin c",
    "tranexamic",
    "kojic",
    "urea",
    "squalane",
    "snail",
    "snail mucin",
    "propolis",
    "fermented",
    "fermentation",
    "volufiline",
    "peeling",
    "aha",
    "bha",
    "pha",
    "spf",
    "sun care",
    "skin barrier",
    "barrier repair",
    "acne",
    "acneskincare",
    "antiaging",
    "anti-aging",
    "hydration",
    "hydrating",
    "brightening",
    "glow",
    "slugging",
    "skin cycling",
    "skin flooding",
]


# ============================================================
# 3. Instagram Rotation
# ============================================================

INSTAGRAM_ROTATION = {
    0: "kbeauty",
    1: "skincareingredients",
    2: "hyperpigmentation",
    3: "acneskincare",
    4: "skincareroutine",
    5: "antiaging",
    6: "skincare",
}


def get_market_now() -> datetime.datetime:
    return datetime.datetime.now(MARKET_TZ)


def get_today_iso() -> str:
    return get_market_now().date().isoformat()


def get_today_instagram_tag() -> str:
    weekday = get_market_now().weekday()
    return INSTAGRAM_ROTATION.get(
        weekday,
        "skincare"
    )


# ============================================================
# 4. SQLite Database
# ============================================================

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():

    conn = get_db()

    conn.execute(
        """
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
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS keyword_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date TEXT NOT NULL,
            keyword TEXT NOT NULL,
            platform TEXT NOT NULL,
            region TEXT NOT NULL,
            mentions INTEGER NOT NULL DEFAULT 0,
            UNIQUE(
                signal_date,
                keyword,
                platform,
                region
            )
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trend_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date TEXT NOT NULL,
            keyword TEXT NOT NULL,
            volume_score REAL NOT NULL,
            velocity_score REAL NOT NULL,
            persistence_score REAL NOT NULL,
            cross_platform_score REAL NOT NULL,
            regional_score REAL NOT NULL,
            trend_score REAL NOT NULL,
            UNIQUE(signal_date, keyword)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS google_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_date TEXT NOT NULL,
            region TEXT NOT NULL,
            rank INTEGER NOT NULL,
            term TEXT NOT NULL
        )
        """
    )

    conn.commit()
    conn.close()

    logging.info(
        "SQLite database initialized: %s",
        DB_PATH
    )


# ============================================================
# 5. Telegram Error
# ============================================================

def send_telegram_error(error_msg: str):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.error(
            "Telegram credentials missing."
        )
        return

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": (
            "🚨 Daily Trend Bot Error Alert\n\n"
            f"{error_msg}"
        )
    }

    try:

        session.post(
            url,
            json=payload,
            timeout=10
        )

    except Exception as e:

        logging.error(
            "Telegram error notification failed: %s",
            e
        )


# ============================================================
# 6. Google Trends
# ============================================================

def fetch_google_trends(
    geo: str = "NL",
    count: int = 15
) -> List[str]:

    url = (
        "https://trends.google.com/trends/"
        f"trendingsearches/daily/rss?geo={geo}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64)"
        )
    }

    try:

        res = session.get(
            url,
            headers=headers,
            timeout=15
        )

        if res.status_code != 200:

            logging.warning(
                "[%s] Google Trends HTTP %s",
                geo,
                res.status_code
            )

            return []

        root = ET.fromstring(
            res.content
        )

        titles = [
            item.text.strip()
            for item in root.findall(
                ".//item/title"
            )
            if item.text
        ]

        selected = titles[:count]

        logging.info(
            "[%s] Google Trends %d개 수집",
            geo,
            len(selected)
        )

        return selected

    except Exception as e:

        logging.error(
            "[%s] Google Trends failed: %s",
            geo,
            e
        )

        return []


def save_google_trends(
    signal_date: str,
    region: str,
    terms: List[str]
):

    if not terms:
        return

    conn = get_db()

    for rank, term in enumerate(
        terms,
        start=1
    ):

        conn.execute(
            """
            INSERT INTO google_trends
            (
                signal_date,
                region,
                rank,
                term
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                signal_date,
                region,
                rank,
                term
            )
        )

    conn.commit()
    conn.close()


# ============================================================
# 7. TikTok
# ============================================================

TIKTOK_QUERIES = [
    "skincare europe",
    "kbeauty germany",
    "viral skincare ingredient",
]


def fetch_tiktok_captions() -> List[Dict]:

    if not RAPIDAPI_KEY:

        logging.warning(
            "RAPIDAPI_KEY missing. TikTok skipped."
        )

        return []

    url = (
        "https://tiktok-api23.p.rapidapi.com/"
        "api/search/video"
    )

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host":
            "tiktok-api23.p.rapidapi.com"
    }

    results = []

    for query in TIKTOK_QUERIES:

        try:

            params = {
                "keyword": query,
                "count": "15",
                "cursor": "0"
            }

            res = session.get(
                url,
                headers=headers,
                params=params,
                timeout=15
            )

            if res.status_code != 200:

                logging.warning(
                    "TikTok query '%s' HTTP %s",
                    query,
                    res.status_code
                )

                continue

            data = res.json()

            items = []

            if isinstance(
                data.get("data"),
                list
            ):

                items = data["data"]

            elif isinstance(
                data.get("data"),
                dict
            ):

                items = (
                    data["data"].get(
                        "item_list"
                    )
                    or data["data"].get(
                        "videos"
                    )
                    or []
                )

            for item in items[:15]:

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

                desc = (
                    desc
                    .replace("\n", " ")
                    [:180]
                )

                region = "EU"

                if "germany" in query.lower():
                    region = "DE"

                results.append(
                    {
                        "platform": "tiktok",
                        "query": query,
                        "tag": "",
                        "region": region,
                        "text": desc
                    }
                )

        except Exception as e:

            logging.error(
                "TikTok query '%s' failed: %s",
                query,
                e
            )

    logging.info(
        "TikTok valid samples: %d / max 45",
        len(results)
    )

    return results


# ============================================================
# 8. Instagram
# ============================================================

def fetch_instagram_captions() -> List[Dict]:

    if not RAPIDAPI_KEY:

        logging.warning(
            "RAPIDAPI_KEY missing. Instagram skipped."
        )

        return []

    target_tag = (
        get_today_instagram_tag()
    )

    url = (
        "https://instagram-statistics-api."
        "p.rapidapi.com/tags"
    )

    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host":
            "instagram-statistics-api."
            "p.rapidapi.com"
    }

    results = []

    try:

        params = {
            "tag": target_tag
        }

        res = session.get(
            url,
            headers=headers,
            params=params,
            timeout=15
        )

        if res.status_code != 200:

            logging.warning(
                "Instagram #%s HTTP %s",
                target_tag,
                res.status_code
            )

            return []

        data = res.json()

        if isinstance(data, list):

            items = data

        elif isinstance(data, dict):

            items = (
                data.get("data", [])
            )

        else:

            items = []

        if not isinstance(items, list):
            items = []

        for item in items[:20]:

            if not isinstance(
                item,
                dict
            ):
                continue

            raw = (
                item.get("caption")
                or item.get("text")
                or ""
            )

            if isinstance(raw, dict):

                raw = raw.get(
                    "text",
                    ""
                )

            if not raw:
                continue

            raw = str(raw).strip()

            if len(raw) <= 10:
                continue

            clean = (
                raw
                .replace("\n", " ")
                [:180]
            )

            results.append(
                {
                    "platform": "instagram",
                    "query": "",
                    "tag": target_tag,
                    "region": "GLOBAL",
                    "text": clean
                }
            )

    except Exception as e:

        logging.error(
            "Instagram #%s failed: %s",
            target_tag,
            e
        )

    logging.info(
        "Instagram #%s valid samples: %d / max 20",
        target_tag,
        len(results)
    )

    return results


# ============================================================
# 9. Raw Signal 저장
# ============================================================

def save_raw_signals(
    signals: List[Dict]
):

    if not signals:
        return

    now = get_market_now().isoformat()
    signal_date = get_today_iso()

    conn = get_db()

    for signal in signals:

        conn.execute(
            """
            INSERT INTO raw_signals
            (
                collected_at,
                signal_date,
                platform,
                query,
                tag,
                region,
                text
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                signal_date,
                signal.get("platform", ""),
                signal.get("query", ""),
                signal.get("tag", ""),
                signal.get("region", ""),
                signal.get("text", "")
            )
        )

    conn.commit()
    conn.close()


# ============================================================
# 10. Keyword 추출
# ============================================================

def normalize_keyword(
    keyword: str
) -> str:

    return (
        keyword
        .lower()
        .strip()
    )


def count_keywords_in_text(
    text: str
) -> Counter:

    text = text.lower()

    counts = Counter()

    for keyword in INGREDIENTS_VOCAB:

        pattern = (
            r"(?<!\w)"
            + re.escape(
                keyword.lower()
            )
            + r"(?!\w)"
        )

        matches = re.findall(
            pattern,
            text
        )

        if matches:

            counts[
                normalize_keyword(
                    keyword
                )
            ] += len(matches)

    return counts


def build_daily_keyword_counts(
    signals: List[Dict]
) -> Dict[Tuple[str, str, str], int]:

    counts = Counter()

    for signal in signals:

        platform = signal["platform"]
        region = signal["region"]

        keyword_counts = (
            count_keywords_in_text(
                signal["text"]
            )
        )

        for keyword, amount in (
            keyword_counts.items()
        ):

            counts[
                (
                    keyword,
                    platform,
                    region
                )
            ] += amount

    return counts


def save_keyword_counts(
    signal_date: str,
    counts: Dict[
        Tuple[str, str, str],
        int
    ]
):

    if not counts:
        return

    conn = get_db()

    for (
        keyword,
        platform,
        region
    ), mentions in counts.items():

        conn.execute(
            """
            INSERT INTO keyword_daily
            (
                signal_date,
                keyword,
                platform,
                region,
                mentions
            )
            VALUES (?, ?, ?, ?, ?)

            ON CONFLICT(
                signal_date,
                keyword,
                platform,
                region
            )

            DO UPDATE SET
                mentions = excluded.mentions
            """,
            (
                signal_date,
                keyword,
                platform,
                region,
                mentions
            )
        )

    conn.commit()
    conn.close()


# ============================================================
# 11. Trend Calculation
# ============================================================

def get_keyword_daily_history(
    keyword: str,
    end_date: str,
    days: int
) -> List[Tuple[str, int]]:

    conn = get_db()

    rows = conn.execute(
        """
        SELECT
            signal_date,
            SUM(mentions) AS total_mentions

        FROM keyword_daily

        WHERE keyword = ?
          AND signal_date < ?
          AND signal_date >= date(?, ?)

        GROUP BY signal_date

        ORDER BY signal_date ASC
        """,
        (
            keyword,
            end_date,
            end_date,
            f"-{days} day"
        )
    ).fetchall()

    conn.close()

    return [
        (
            row["signal_date"],
            row["total_mentions"]
        )
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

    avg_previous = (
        sum(previous_values)
        / len(previous_values)
    )

    if avg_previous <= 0:

        return 0.0, False

    velocity = (
        today_mentions - avg_previous
    ) / avg_previous

    return velocity, True


def calculate_persistence(
    history: List[Tuple[str, int]],
    window_days: int = 7
) -> float:

    if not history:
        return 0.0

    active_days = sum(
        1
        for _, mentions in history
        if mentions > 0
    )

    return min(
        active_days / window_days,
        1.0
    )


def calculate_cross_platform(
    keyword: str,
    signal_date: str
) -> float:

    conn = get_db()

    rows = conn.execute(
        """
        SELECT DISTINCT platform

        FROM keyword_daily

        WHERE keyword = ?
          AND signal_date = ?
          AND mentions > 0
        """,
        (
            keyword,
            signal_date
        )
    ).fetchall()

    conn.close()

    platforms = {
        row["platform"]
        for row in rows
    }

    return min(
        len(platforms) / 2.0,
        1.0
    )


def calculate_regional_score(
    keyword: str,
    signal_date: str
) -> float:

    conn = get_db()

    rows = conn.execute(
        """
        SELECT DISTINCT region

        FROM keyword_daily

        WHERE keyword = ?
          AND signal_date = ?
          AND mentions > 0
        """,
        (
            keyword,
            signal_date
        )
    ).fetchall()

    conn.close()

    regions = {
        row["region"]
        for row in rows
    }

    return min(
        len(regions) / 3.0,
        1.0
    )


def calculate_volume_score(
    today_mentions: float
) -> float:

    if today_mentions <= 0:
        return 0.0

    return min(
        math.log1p(
            today_mentions
        )
        / math.log1p(30),
        1.0
    )


def calculate_trend_status(
    today_mentions: int,
    velocity: float,
    has_history: bool,
    persistence: float
) -> str:

    if not has_history:

        return (
            "INSUFFICIENT DATA"
        )

    if velocity >= 0.50:

        return "RISING"

    if velocity >= 0.10:

        return "EMERGING"

    if velocity <= -0.30:

        return "DECLINING"

    if persistence >= 0.40:

        return "ESTABLISHED"

    return "EMERGING"


def calculate_trend_scores(
    signal_date: str,
    daily_counts: Dict[
        Tuple[str, str, str],
        int
    ]
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
            for (
                kw,
                _platform,
                _region
            ), mentions in daily_counts.items()
            if kw == keyword
        )

        history = (
            get_keyword_daily_history(
                keyword,
                signal_date,
                7
            )
        )

        velocity, has_history = (
            calculate_velocity(
                today_mentions,
                history
            )
        )

        persistence = (
            calculate_persistence(
                history,
                7
            )
        )

        cross_platform = (
            calculate_cross_platform(
                keyword,
                signal_date
            )
        )

        regional = (
            calculate_regional_score(
                keyword,
                signal_date
            )
        )

        volume_score = (
            calculate_volume_score(
                today_mentions
            )
        )

        if has_history:

            velocity_clamped = max(
                -1.0,
                min(
                    velocity,
                    1.0
                )
            )

            velocity_score = (
                velocity_clamped + 1.0
            ) / 2.0

        else:

            # Cold-start를 상승으로 조작하지 않음.
            # 과거 데이터가 없으면 velocity 중립값.
            velocity_score = 0.5

        trend_score = (
            volume_score * 0.25
            + velocity_score * 0.30
            + persistence * 0.20
            + cross_platform * 0.15
            + regional * 0.10
        ) * 100

        status = calculate_trend_status(
            today_mentions,
            velocity,
            has_history,
            persistence
        )

        results.append(
            {
                "keyword": keyword,
                "today_mentions": today_mentions,
                "velocity": velocity,
                "has_history": has_history,
                "status": status,
                "volume_score":
                    volume_score * 100,
                "velocity_score":
                    velocity_score * 100,
                "persistence_score":
                    persistence * 100,
                "cross_platform_score":
                    cross_platform * 100,
                "regional_score":
                    regional * 100,
                "trend_score":
                    trend_score
            }
        )

    results.sort(
        key=lambda x:
            x["trend_score"],
        reverse=True
    )

    return results


def save_trend_scores(
    signal_date: str,
    scores: List[Dict]
):

    conn = get_db()

    for item in scores:

        conn.execute(
            """
            INSERT INTO trend_scores
            (
                signal_date,
                keyword,
                volume_score,
                velocity_score,
                persistence_score,
                cross_platform_score,
                regional_score,
                trend_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(
                signal_date,
                keyword
            )

            DO UPDATE SET

                volume_score =
                    excluded.volume_score,

                velocity_score =
                    excluded.velocity_score,

                persistence_score =
                    excluded.persistence_score,

                cross_platform_score =
                    excluded.cross_platform_score,

                regional_score =
                    excluded.regional_score,

                trend_score =
                    excluded.trend_score
            """,
            (
                signal_date,
                item["keyword"],
                item["volume_score"],
                item["velocity_score"],
                item["persistence_score"],
                item["cross_platform_score"],
                item["regional_score"],
                item["trend_score"]
            )
        )

    conn.commit()
    conn.close()


# ============================================================
# 12. Trend Summary
# ============================================================

def build_trend_summary(
    scores: List[Dict]
) -> str:

    if not scores:

        return (
            "No quantitative trend score "
            "available today."
        )

    lines = []

    for rank, item in enumerate(
        scores[:10],
        start=1
    ):

        if item["has_history"]:

            velocity_text = (
                f"{item['velocity'] * 100:+.1f}%"
            )

        else:

            velocity_text = (
                "INSUFFICIENT_HISTORY"
            )

        lines.append(
            f"{rank}. "
            f"{item['keyword']} | "
            f"status={item['status']} | "
            f"mentions="
            f"{item['today_mentions']} | "
            f"velocity="
            f"{velocity_text} | "
            f"persistence="
            f"{item['persistence_score']:.0f}/100 | "
            f"cross_platform="
            f"{item['cross_platform_score']:.0f}/100 | "
            f"regional="
            f"{item['regional_score']:.0f}/100 | "
            f"TREND_SCORE="
            f"{item['trend_score']:.1f}/100"
        )

    return "\n".join(lines)


# ============================================================
# 13. Google Trends → Gemini
# ============================================================

def format_google_trends(
    terms: List[str]
) -> str:

    if not terms:
        return "UNAVAILABLE TODAY"

    return " | ".join(terms)


# ============================================================
# 14. Gemini 3.6 Flash
# ============================================================

def generate_gemini_report(
    google_nl: List[str],
    google_de: List[str],
    social_data: List[Dict],
    freq_summary: str,
    trend_summary: str
) -> str:

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY is missing."
        )

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        "gemini-3.6-flash:generateContent"
    )

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }

    social_lines = []

    for item in social_data:

        platform = item.get(
            "platform",
            ""
        )

        query = item.get(
            "query",
            ""
        )

        tag = item.get(
            "tag",
            ""
        )

        region = item.get(
            "region",
            ""
        )

        text = item.get(
            "text",
            ""
        )

        source = platform

        if query:
            source += f"/{query}"

        if tag:
            source += f"/#{tag}"

        social_lines.append(
            f"[{source} | {region}] {text}"
        )

    social_text = "\n".join(
        social_lines
    )

    prompt = f"""
You are the CEO and Head of Sourcing for a
European cosmetics and skincare e-commerce platform
based in the Netherlands.

TARGET CUSTOMER SEGMENTS

1. Dutch / Western European customers

- barrier repair
- hydration
- sunscreen
- clean beauty
- sensitive skin

2. German cross-border customers

- DM / Rossmann style trends
- clinical ingredients
- affordable efficacy
- K-beauty

3. Arab / Middle Eastern customers living in Europe

- hyperpigmentation
- dark spots
- brightening
- halal / vegan
- high-potency skincare

4. K-Beauty / Asian Beauty enthusiasts

- glass skin
- PDRN
- spicule
- reedle
- sunsticks
- innovative textures


DATA QUALITY RULES

Frequency and Trend are NOT the same thing.

"Mentions" means today's observed volume.

"Velocity" means today's volume compared with
the available historical baseline.

"Persistence" means how consistently the signal
has appeared across recent days.

"Cross-platform" means whether the signal appears
across multiple platforms.

"Regional" means whether the signal appears across
multiple geographic segments.

Never claim that a keyword is rising merely because
it has a high mention count.

A high-volume keyword with negative velocity should
be described as established or declining.

If historical data is insufficient, explicitly say:

"Insufficient historical data for velocity."

Never invent missing data.

Never treat unavailable Google Trends data as a
real market signal.


GOOGLE TRENDS

Netherlands raw Google Trends:
{format_google_trends(google_nl)}

Germany raw Google Trends:
{format_google_trends(google_de)}


QUANTITATIVE TREND SCORES

{trend_summary}


KNOWN VOCABULARY FREQUENCY

{freq_summary}


LIVE SOCIAL SAMPLES

Total valid samples:
{len(social_data)}

{social_text}


NEW TREND DISCOVERY

Do NOT rely only on the known vocabulary list.

Scan the complete social sample for repeated unknown:

- ingredients
- molecules
- formulations
- textures
- product formats
- beauty treatments
- consumer problems
- product names
- emerging slang
- hashtags
- K-beauty terminology

Examples include:

Spicule
Reedle
Volufiline
Exosomes
skin cycling
slugging
skin flooding


SIGNAL CLASSIFICATION

Classify each signal as one of:

- EMERGING
- RISING
- ESTABLISHED
- DECLINING
- INSUFFICIENT DATA


IMPORTANT

A signal with insufficient history must NOT be
presented as statistically rising.

Use the exact phrase:

"Insufficient historical data for velocity."

when historical data is insufficient.


BUSINESS PRIORITY

Prioritize signals using:

1. High Trend Score
2. Positive velocity
3. Multi-platform presence
4. Regional relevance
5. Repeated appearance
6. Commercial sourcing potential


GOOGLE TRENDS FILTERING

First determine which Google Trends items are actually
related to cosmetics, skincare, beauty, ingredients,
consumer products or relevant retail behavior.

Do NOT assume every Google Trend is a beauty trend.


REPORT FORMAT

Generate a daily COSMETICS & SKINCARE MARKET TREND REPORT.

Use exactly three sections.

Separate sections with:

===SPLIT_SECTION===


SECTION 1 — ENGLISH

🌐 GLOBAL COSMETICS MARKET DAILY REPORT

1. 📈 TOP 5 TREND SIGNALS TODAY

For each:

- keyword / ingredient
- status
- Trend Score
- evidence
- commercial interpretation

2. 💡 CEO SOURCING & MARKETING STRATEGY

Cover:

- Netherlands
- Germany
- Arab / Middle Eastern Europe
- K-Beauty

3. 💄 VIRAL PRODUCT CONCEPT

Create one commercially realistic product concept
based on the strongest signals.

Include:

- ingredient
- texture
- format
- target customer
- retail price positioning
- marketing angle

===SPLIT_SECTION===

SECTION 2 — DUTCH

🌐 EUROPESE COSMETICA MARKT DAGRAPPORT

1. 📈 TOP 5 TRENDSIGNALEN VANDAAG
Voor elk:
- trefwoord / ingrediënt
- status
- Trendscore
- bewijs
- commerciële interpretatie

2. 💡 CEO INKOOP & MARKETING STRATEGIE
Behandel:
- Nederland
- Duitsland
- Arabisch / Midden-Oosten in Europa
- K-Beauty

3. 💄 VIRAAL PRODUCTCONCEPT
Creëer één commercieel realistisch productconcept op basis van de sterkste signalen.
Inclusief:
- ingrediënt
- textuur
- formaat
- doelgroep
- verkoopprijs-positionering
- marketinghoek

===SPLIT_SECTION===

SECTION 3 — GERMAN

🌐 EUROPÄISCHER KOSMETIK-MARKT TAGESBERICHT

1. 📈 TOP 5 TREND-SIGNALE HEUTE
Für jedes:
- Schlüsselwort / Inhaltsstoff
- Status
- Trend-Score
- Beweis
- kommerzielle Interpretation

2. 💡 CEO-EINKAUFS- & MARKETING-STRATEGIE
Abdecken:
- Niederlande
- Deutschland
- Arabisch / Naher Osten in Europa
- K-Beauty

3. 💄 VIRALES PRODUKTKONZEPT
Erstellen Sie ein kommerziell realistisches Produktkonzept basierend auf den stärksten Signalen.
Enthalten:
- Inhaltsstoff
- Textur
- Format
- Zielgruppe
- Verkaufspreis-Positionierung
- Marketing-Ansatz
"""

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
            "maxOutputTokens": 4096
        }
    }

    try:
        res = session.post(
            url,
            headers=headers,
            json=payload,
            timeout=45
        )

        if res.status_code != 200:
            logging.error("Gemini API HTTP %s: %s", res.status_code, res.text)
            raise RuntimeError(f"Gemini API failed with status {res.status_code}")

        data = res.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini API returned no candidates.")

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise RuntimeError("Gemini API response parts empty.")

        report_text = parts[0].get("text", "").strip()
        logging.info("Gemini report generated successfully (%d chars)", len(report_text))
        return report_text

    except Exception as e:
        logging.error("Gemini report generation failed: %s", e)
        raise


# ============================================================
# 15. Telegram Notification
# ============================================================

def send_telegram_message(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram credentials missing. Message not sent.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    max_length = 4000
    chunks = [message[i:i+max_length] for i in range(0, len(message), max_length)]

    for chunk in chunks:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown"
        }
        try:
            res = session.post(url, json=payload, timeout=15)
            if res.status_code != 200:
                logging.warning("Telegram message failed with status %s: %s", res.status_code, res.text)
        except Exception as e:
            logging.error("Telegram notification failed: %s", e)


# ============================================================
# 16. Main Pipeline
# ============================================================

def main():
    logging.info("=== Daily Cosmetics Trend Bot Started ===")
    
    try:
        init_database()
        signal_date = get_today_iso()
        region_nl = "NL"
        region_de = "DE"

        # 1. Fetch Google Trends
        logging.info("Fetching Google Trends for NL and DE...")
        trends_nl = fetch_google_trends(geo=region_nl, count=15)
        trends_de = fetch_google_trends(geo=region_de, count=15)

        save_google_trends(signal_date, region_nl, trends_nl)
        save_google_trends(signal_date, region_de, trends_de)

        # 2. Fetch Social Signals (TikTok & Instagram)
        logging.info("Fetching TikTok captions...")
        tiktok_signals = fetch_tiktok_captions()

        logging.info("Fetching Instagram captions...")
        instagram_signals = fetch_instagram_captions()

        all_signals = tiktok_signals + instagram_signals
        save_raw_signals(all_signals)

        # 3. Process Keyword Counts
        logging.info("Building daily keyword counts...")
        daily_counts = build_daily_keyword_counts(all_signals)
        save_keyword_counts(signal_date, daily_counts)

        # 4. Calculate Trend Scores
        logging.info("Calculating trend scores...")
        trend_scores = calculate_trend_scores(signal_date, daily_counts)
        save_trend_scores(signal_date, trend_scores)

        # 5. Build Summaries
        trend_summary_str = build_trend_summary(trend_scores)
        
        freq_lines = []
        for item in trend_scores[:20]:
            freq_lines.append(f"- {item['keyword']}: {item['today_mentions']} mentions")
        freq_summary_str = "\n".join(freq_lines) if freq_lines else "No vocabulary frequency data today."

        # 6. Generate Gemini Report
        logging.info("Generating Gemini market report...")
        report = generate_gemini_report(
            google_nl=trends_nl,
            google_de=trends_de,
            social_data=all_signals,
            freq_summary=freq_summary_str,
            trend_summary=trend_summary_str
        )

        # 7. Send Report via Telegram
        logging.info("Sending report via Telegram...")
        sections = report.split("===SPLIT_SECTION===")
        for section in sections:
            if section.strip():
                send_telegram_message(section.strip())

        logging.info("=== Daily Cosmetics Trend Bot Completed Successfully ===")

    except Exception as e:
        err_msg = f"Pipeline execution failed: {str(e)}"
        logging.error(err_msg, exc_info=True)
        send_telegram_error(err_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
