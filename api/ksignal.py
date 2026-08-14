"""K-Signal ranking API — read-only from raw_signals."""
from __future__ import annotations

import datetime
import re
from collections import defaultdict
from urllib.parse import urlparse

from fastapi import APIRouter, Query

from api.database import get_db_connection

router = APIRouter(prefix="/api/ksignal", tags=["K-Signal"])

_META_RE = re.compile(
    r"^(?P<name>.+?)\s*\("
    r"velocity=(?P<velocity>[-+]?\d*\.?\d+),\s*"
    r"accel=(?P<accel>[-+]?\d*\.?\d+),\s*"
    r"score=(?P<score>[-+]?\d*\.?\d+),\s*"
    r"confidence=(?P<confidence>[-+]?\d*\.?\d+)"
    r"\)\s*(?:\[(?P<url>https?://[^\]]+)\])?\s*$",
    re.IGNORECASE | re.DOTALL,
)

_MALL_RULES = [
    ("oliveyoung", "Olive Young", "올리브영"),
    ("glowpick", "Glowpick", "글로우픽"),
    ("hwahae", "Hwahae", "화해"),
    ("zigzag", "Zigzag", "지그재그"),
    ("musinsa", "Musinsa", "무신사"),
    ("wconcept", "Wconcept", "W컨셉"),
    ("29cm", "29cm", "29CM"),
    ("ably", "Ably", "에이블리"),
]

# K-Signal feed mixes beauty + fashion. Prefer beauty for this dashboard.
_BEAUTY_MALLS = {"oliveyoung", "glowpick", "hwahae"}
_FASHION_NAME_RE = re.compile(
    r"("
    r"skirt|pants|trousers|jeans|denim|blazer|jacket|coat|cardigan|"
    r"knit|sweater|hoodie|shirt|blouse|dress|gown|tee|t-shirt|"
    r"cargo|midi|maxi|mini skirt|wool|cotton tee|ripstop|"
    r"sneakers|shoes|boots|bag|tote|wallet|belt|cap|hat|"
    r"스커트|바지|블레이저|자켓|재킷|코트|가디건|니트|후드|"
    r"원피스|셔츠|블라우스|청바지|스니커|가방"
    r")",
    re.IGNORECASE,
)
_BEAUTY_NAME_RE = re.compile(
    r"("
    r"toner|ampoule|serum|cream|essence|cleanser|lotion|mask|"
    r"sunscreen|sunstick|sun stick|moisturizer|moisturiser|"
    r"retinol|retinal|niacinamide|peptide|pdrn|cica|centella|"
    r"spf|skincare|skin care|beauty|cosmetic|"
    r"토너|앰플|세럼|크림|에센스|클렌저|선크림|선스틱|마스크|"
    r"스킨케어|미백|보습"
    r")",
    re.IGNORECASE,
)


def _is_beauty_item(item: dict) -> bool:
    """Keep beauty; drop obvious fashion when mixed feed appears."""
    mall_id = (item.get("mall") or {}).get("id") or ""
    name = item.get("product_name") or ""
    if mall_id in _BEAUTY_MALLS:
        return True
    if _FASHION_NAME_RE.search(name) and not _BEAUTY_NAME_RE.search(name):
        return False
    if _BEAUTY_NAME_RE.search(name):
        return True
    # Unknown mall + no clear fashion keywords: keep (avoid over-filtering)
    if mall_id in {"unknown", "other"}:
        return not bool(_FASHION_NAME_RE.search(name))
    # Fashion-leaning malls without beauty keywords → drop
    if mall_id in {"musinsa", "wconcept", "zigzag", "29cm", "ably"}:
        return bool(_BEAUTY_NAME_RE.search(name))
    return True


def _detect_mall(url: str | None) -> dict:
    if not url:
        return {"id": "unknown", "name_en": "Unknown", "name_ko": "기타"}
    host = urlparse(url).netloc.lower()
    path = (urlparse(url).path or "").lower()
    blob = host + path
    for key, en, ko in _MALL_RULES:
        if key in blob:
            return {"id": key, "name_en": en, "name_ko": ko}
    return {"id": "other", "name_en": host or "Other", "name_ko": host or "기타"}


def _parse_signal_text(text: str) -> dict | None:
    if not text or not text.strip():
        return None
    m = _META_RE.match(text.strip())
    if not m:
        url_m = re.search(r"\[(https?://[^\]]+)\]", text)
        return {
            "product_name": re.sub(r"\s*\(.*$", "", text).strip()[:200] or text[:200],
            "velocity": None,
            "accel": None,
            "score": None,
            "confidence": None,
            "url": url_m.group(1) if url_m else None,
            "parse_ok": False,
        }
    return {
        "product_name": m.group("name").strip(),
        "velocity": float(m.group("velocity")),
        "accel": float(m.group("accel")),
        "score": float(m.group("score")),
        "confidence": float(m.group("confidence")),
        "url": m.group("url"),
        "parse_ok": True,
    }


def _latest_ksignal_date(conn) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(signal_date) AS d
        FROM raw_signals
        WHERE LOWER(platform) = 'k_signal'
        """
    ).fetchone()
    return row["d"] if row and row["d"] else None


def _fetch_raw_rows(conn, dates: list[str]) -> list:
    if not dates:
        return []
    placeholders = ",".join("?" for _ in dates)
    return conn.execute(
        f"""
        SELECT id, collected_at, signal_date, region, text
        FROM raw_signals
        WHERE LOWER(platform) = 'k_signal'
          AND signal_date IN ({placeholders})
        ORDER BY signal_date DESC, id ASC
        """,
        dates,
    ).fetchall()


def _rows_to_items(rows) -> list[dict]:
    items = []
    for row in rows:
        parsed = _parse_signal_text(row["text"] or "")
        if not parsed:
            continue
        mall = _detect_mall(parsed.get("url"))
        items.append(
            {
                "id": row["id"],
                "signal_date": row["signal_date"],
                "collected_at": row["collected_at"],
                "region": row["region"],
                "product_name": parsed["product_name"],
                "velocity": parsed["velocity"],
                "accel": parsed["accel"],
                "score": parsed["score"],
                "confidence": parsed["confidence"],
                "url": parsed.get("url"),
                "mall": mall,
                "parse_ok": parsed["parse_ok"],
            }
        )
    return items


def _mall_counts(items: list[dict]) -> list[dict]:
    counts: dict[str, int] = {}
    meta: dict[str, dict] = {}
    for it in items:
        mid = it["mall"]["id"]
        counts[mid] = counts.get(mid, 0) + 1
        meta[mid] = it["mall"]
    malls = []
    for key, en, ko in _MALL_RULES:
        if key in counts:
            malls.append(
                {"id": key, "name_en": en, "name_ko": ko, "count": counts[key]}
            )
    for key, cnt in counts.items():
        if key not in {m[0] for m in _MALL_RULES}:
            m = meta.get(key, {})
            malls.append(
                {
                    "id": key,
                    "name_en": m.get("name_en", key),
                    "name_ko": m.get("name_ko", key),
                    "count": cnt,
                }
            )
    return malls


def _rank_daily(items: list[dict], limit: int) -> list[dict]:
    items = sorted(
        items,
        key=lambda x: (
            x["score"] is not None,
            x["score"] if x["score"] is not None else -1,
            x["velocity"] if x["velocity"] is not None else -1,
        ),
        reverse=True,
    )
    for i, it in enumerate(items[:limit], start=1):
        it["rank"] = i
        it["days_seen"] = 1
    return items[:limit]


def _aggregate_by_product(items: list[dict], limit: int) -> list[dict]:
    """Merge same product across days: max score, avg velocity/accel/confidence, days_seen."""
    buckets: dict[str, list] = defaultdict(list)
    for it in items:
        key = (it.get("url") or it["product_name"]).strip().lower()
        buckets[key].append(it)

    merged = []
    for group in buckets.values():
        scores = [g["score"] for g in group if g["score"] is not None]
        vels = [g["velocity"] for g in group if g["velocity"] is not None]
        accs = [g["accel"] for g in group if g["accel"] is not None]
        confs = [g["confidence"] for g in group if g["confidence"] is not None]
        best = max(
            group,
            key=lambda g: (g["score"] is not None, g["score"] or -1),
        )
        dates = sorted({g["signal_date"] for g in group})
        merged.append(
            {
                **best,
                "score": max(scores) if scores else None,
                "velocity": (sum(vels) / len(vels)) if vels else None,
                "accel": (sum(accs) / len(accs)) if accs else None,
                "confidence": (sum(confs) / len(confs)) if confs else None,
                "days_seen": len(dates),
                "first_seen": dates[0] if dates else None,
                "last_seen": dates[-1] if dates else None,
            }
        )

    merged.sort(
        key=lambda x: (
            x["score"] is not None,
            x["score"] if x["score"] is not None else -1,
            x["days_seen"],
            x["velocity"] if x["velocity"] is not None else -1,
        ),
        reverse=True,
    )
    for i, it in enumerate(merged[:limit], start=1):
        it["rank"] = i
    return merged[:limit]


def _date_window(end_date: str, days: int) -> list[str]:
    end = datetime.date.fromisoformat(end_date)
    return [
        (end - datetime.timedelta(days=i)).isoformat()
        for i in range(days)
    ]


@router.get("/ranking")
def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _latest_structured_date(conn) -> str | None:
    if not _table_exists(conn, "k_signal_items"):
        return None
    row = conn.execute(
        "SELECT MAX(signal_date) AS d FROM k_signal_items WHERE is_beauty = 1"
    ).fetchone()
    return row["d"] if row and row["d"] else None


def _fetch_structured_items(conn, dates: list[str]) -> list[dict]:
    if not dates or not _table_exists(conn, "k_signal_items"):
        return []
    placeholders = ",".join("?" for _ in dates)
    rows = conn.execute(
        f"""
        SELECT id, signal_date, collected_at, product_name, brand,
               mall_id, mall_name, score, velocity, accel, confidence, url
        FROM k_signal_items
        WHERE is_beauty = 1
          AND signal_date IN ({placeholders})
        """,
        dates,
    ).fetchall()
    items = []
    for r in rows:
        items.append(
            {
                "id": r["id"],
                "signal_date": r["signal_date"],
                "collected_at": r["collected_at"],
                "region": "KR",
                "product_name": r["product_name"],
                "velocity": r["velocity"],
                "accel": r["accel"],
                "score": r["score"],
                "confidence": r["confidence"],
                "url": r["url"],
                "mall": {
                    "id": r["mall_id"] or "unknown",
                    "name_en": r["mall_name"] or r["mall_id"] or "Unknown",
                    "name_ko": r["mall_name"] or r["mall_id"] or "기타",
                },
                "parse_ok": True,
            }
        )
    return items


def ksignal_ranking(
    period: str = Query("day", pattern="^(day|week|month)$"),
    limit: int = Query(50, ge=1, le=200),
):
    """
    period=day   → latest date only
    period=week  → last 7 calendar days from latest K-Signal date
    period=month → last 30 calendar days from latest K-Signal date

    Prefers structured k_signal_items when present; falls back to raw_signals parse.
    """
    conn = get_db_connection()
    try:
        structured_latest = _latest_structured_date(conn)
        latest = structured_latest or _latest_ksignal_date(conn)
        if not latest:
            return {
                "period": period,
                "date": None,
                "date_from": None,
                "date_to": None,
                "count": 0,
                "items": [],
                "malls": [],
                "message": "No K-Signal data yet",
                "source": None,
            }

        if period == "day":
            dates = [latest]
            date_from = date_to = latest
        elif period == "week":
            dates = _date_window(latest, 7)
            date_from, date_to = dates[-1], dates[0]
        else:
            dates = _date_window(latest, 30)
            date_from, date_to = dates[-1], dates[0]

        source = "structured"
        raw_items = _fetch_structured_items(conn, dates)
        if not raw_items:
            source = "raw_signals"
            raw_items = _rows_to_items(_fetch_raw_rows(conn, dates))
            raw_items = [x for x in raw_items if _is_beauty_item(x)]

        if period == "day":
            items = _rank_daily(raw_items, limit)
        else:
            items = _aggregate_by_product(raw_items, limit)

        return {
            "period": period,
            "date": latest,
            "date_from": date_from,
            "date_to": date_to,
            "count": len(items),
            "items": items,
            "malls": _mall_counts(items),
            "source": source,
        }
    finally:
        conn.close()


@router.get("/today")
def ksignal_today(limit: int = Query(50, ge=1, le=200)):
    """Backward-compatible alias for period=day. """
    return ksignal_ranking(period="day", limit=limit)


@router.get("/dates")
def ksignal_dates(limit: int = Query(30, ge=1, le=90)):
    conn = get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT signal_date, COUNT(*) AS n
            FROM raw_signals
            WHERE LOWER(platform) = 'k_signal'
            GROUP BY signal_date
            ORDER BY signal_date DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return {
            "dates": [{"date": r["signal_date"], "count": r["n"]} for r in rows]
        }
    finally:
        conn.close()
