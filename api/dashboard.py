from fastapi import APIRouter, HTTPException, Query
from api.database import get_db_connection

router = APIRouter(prefix="/api", tags=["Dashboard"])


def _latest_date(conn):
    row = conn.execute("SELECT MAX(signal_date) AS d FROM trend_scores").fetchone()
    return row["d"] if row else None


@router.get("/dashboard/summary")
def dashboard_summary():
    conn = get_db_connection()
    try:
        latest = _latest_date(conn)
        if not latest:
            return {"date": None, "keyword_count": 0, "avg_score": 0, "rising_count": 0, "raw_signal_count": 0}

        keyword_count = conn.execute(
            "SELECT COUNT(*) AS n FROM trend_scores WHERE signal_date = ?", (latest,)
        ).fetchone()["n"]
        avg_score = conn.execute(
            "SELECT COALESCE(AVG(trend_score),0) AS n FROM trend_scores WHERE signal_date = ?", (latest,)
        ).fetchone()["n"]
        rising_count = conn.execute("""
            SELECT COUNT(*) AS n
            FROM trend_scores t
            WHERE t.signal_date = ?
              AND t.velocity_score >= 70
        """, (latest,)).fetchone()["n"]
        raw_signal_count = conn.execute(
            "SELECT COUNT(*) AS n FROM raw_signals WHERE signal_date = ?", (latest,)
        ).fetchone()["n"]
        return {
            "date": latest,
            "keyword_count": keyword_count,
            "avg_score": round(float(avg_score or 0), 1),
            "rising_count": rising_count,
            "raw_signal_count": raw_signal_count,
        }
    finally:
        conn.close()


@router.get("/keywords/{keyword}")
def keyword_detail(keyword: str):
    conn = get_db_connection()
    try:
        latest = conn.execute(
            "SELECT MAX(signal_date) AS d FROM trend_scores WHERE keyword = ?", (keyword,)
        ).fetchone()["d"]
        if not latest:
            raise HTTPException(status_code=404, detail=f"Keyword not found: {keyword}")

        latest_row = conn.execute("""
            SELECT signal_date, keyword, volume_score, velocity_score,
                   persistence_score, cross_platform_score, regional_score,
                   platform_normalized_score, trend_score
            FROM trend_scores
            WHERE keyword = ? AND signal_date = ?
        """, (keyword, latest)).fetchone()

        history = conn.execute("""
            SELECT signal_date, trend_score, volume_score, velocity_score,
                   persistence_score, cross_platform_score, regional_score,
                   platform_normalized_score
            FROM trend_scores
            WHERE keyword = ?
            ORDER BY signal_date ASC
        """, (keyword,)).fetchall()

        return {
            "keyword": keyword,
            "latest": dict(latest_row),
            "history": [dict(r) for r in history],
        }
    finally:
        conn.close()


@router.get("/keywords/{keyword}/platforms")
def keyword_platforms(keyword: str, days: int = Query(30, ge=1, le=180)):
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT signal_date, platform, SUM(mentions) AS mentions
            FROM keyword_daily
            WHERE keyword = ?
              AND signal_date >= date((SELECT MAX(signal_date) FROM keyword_daily), ?)
            GROUP BY signal_date, platform
            ORDER BY signal_date ASC, platform ASC
        """, (keyword, f"-{days - 1} day")).fetchall()
        return {"keyword": keyword, "days": days, "data": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/keywords/{keyword}/regions")
def keyword_regions(keyword: str, days: int = Query(30, ge=1, le=180)):
    conn = get_db_connection()
    try:
        rows = conn.execute("""
            SELECT region, SUM(mentions) AS mentions
            FROM keyword_daily
            WHERE keyword = ?
              AND signal_date >= date((SELECT MAX(signal_date) FROM keyword_daily), ?)
            GROUP BY region
            ORDER BY mentions DESC
        """, (keyword, f"-{days - 1} day")).fetchall()
        return {"keyword": keyword, "days": days, "data": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/keywords/{keyword}/signals")
def keyword_signals(keyword: str, limit: int = Query(40, ge=1, le=200)):
    conn = get_db_connection()
    try:
        # Match the keyword in the normalized fields and raw text. This is intentionally
        # read-only and returns the most recent matching source signals first.
        rows = conn.execute("""
            SELECT id, collected_at, signal_date, platform, query, tag, region, text
            FROM raw_signals
            WHERE LOWER(COALESCE(tag, '')) = LOWER(?)
               OR LOWER(COALESCE(query, '')) LIKE '%' || LOWER(?) || '%'
               OR LOWER(COALESCE(text, '')) LIKE '%' || LOWER(?) || '%'
            ORDER BY id DESC
            LIMIT ?
        """, (keyword, keyword, keyword, limit)).fetchall()
        return {"keyword": keyword, "count": len(rows), "signals": [dict(r) for r in rows]}
    finally:
        conn.close()
