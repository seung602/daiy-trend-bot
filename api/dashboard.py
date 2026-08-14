from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from api.database import get_db_connection

router = APIRouter(prefix="/api", tags=["Dashboard"])


def _latest_date(conn):
    row = conn.execute("SELECT MAX(signal_date) AS d FROM trend_scores").fetchone()
    return row["d"] if row else None


def _status_from_row(row, history_count: int | None = None) -> str:
    """Mirror the collector's calculate_trend_status() using stored scores.

    trend_scores stores velocity_score after converting raw velocity from [-1, 1]
    to [0, 1] and multiplying by 100. Therefore the collector thresholds map to:
      RISING   >= 75
      EMERGING >= 55
      DECLINING <= 35
      ESTABLISHED when persistence >= 40
    """
    velocity = float(row["velocity_score"] or 0)
    persistence = float(row["persistence_score"] or 0)
    if history_count is not None and history_count < 2:
        return "INSUFFICIENT DATA"
    if velocity >= 75:
        return "RISING"
    if velocity >= 55:
        return "EMERGING"
    if velocity <= 35:
        return "DECLINING"
    if persistence >= 40:
        return "ESTABLISHED"
    return "EMERGING"


def _status_case_sql(status: str) -> tuple[str, tuple]:
    # SQL expression mirrors _status_from_row for filtering the latest snapshot.
    expr = """
        CASE
          WHEN velocity_score >= 75 THEN 'RISING'
          WHEN velocity_score >= 55 THEN 'EMERGING'
          WHEN velocity_score <= 35 THEN 'DECLINING'
          WHEN persistence_score >= 40 THEN 'ESTABLISHED'
          ELSE 'EMERGING'
        END
    """
    return expr, (status,)


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
        rising_count = conn.execute(
            "SELECT COUNT(*) AS n FROM trend_scores WHERE signal_date = ? AND velocity_score >= 75", (latest,)
        ).fetchone()["n"]
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


@router.get("/dashboard/trends")
def dashboard_trends(
    limit: int = Query(10, ge=1, le=100),
    status: str = Query("ALL"),
):
    conn = get_db_connection()
    try:
        latest = _latest_date(conn)
        if not latest:
            return {"date": None, "count": 0, "trends": []}

        allowed = {"ALL", "RISING", "EMERGING", "ESTABLISHED", "DECLINING"}
        status = status.upper()
        if status not in allowed:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        expr = """
            CASE
              WHEN velocity_score >= 75 THEN 'RISING'
              WHEN velocity_score >= 55 THEN 'EMERGING'
              WHEN velocity_score <= 35 THEN 'DECLINING'
              WHEN persistence_score >= 40 THEN 'ESTABLISHED'
              ELSE 'EMERGING'
            END
        """
        params = [latest]
        where_status = ""
        if status != "ALL":
            where_status = f"AND ({expr}) = ?"
            params.append(status)

        rows = conn.execute(f"""
            SELECT keyword, trend_score, volume_score, velocity_score,
                   persistence_score, cross_platform_score, regional_score,
                   platform_normalized_score,
                   {expr} AS status
            FROM trend_scores
            WHERE signal_date = ?
              {where_status}
            ORDER BY trend_score DESC
            LIMIT ?
        """, (*params, limit)).fetchall()
        return {"date": latest, "count": len(rows), "trends": [dict(r) for r in rows]}
    finally:
        conn.close()


# Backwards-compatible endpoint used by the original dashboard.
@router.get("/dashboard/today")
def dashboard_today(limit: int = Query(10, ge=1, le=100)):
    return dashboard_trends(limit=limit, status="ALL")


@router.get("/keywords/{keyword}")
def keyword_detail(keyword: str, days: int = Query(30, ge=2, le=365)):
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
              AND signal_date >= date(?, ?)
            ORDER BY signal_date ASC
        """, (keyword, latest, f"-{days - 1} day")).fetchall()

        history_count = conn.execute(
            "SELECT COUNT(*) AS n FROM trend_scores WHERE keyword = ?", (keyword,)
        ).fetchone()["n"]

        latest_dict = dict(latest_row)
        latest_dict["status"] = _status_from_row(latest_row, history_count)

        return {
            "keyword": keyword,
            "days": days,
            "latest": latest_dict,
            "history": [dict(r) for r in history],
        }
    finally:
        conn.close()


@router.get("/keywords/{keyword}/platforms")
def keyword_platforms(keyword: str, days: int = Query(30, ge=1, le=180)):
    conn = get_db_connection()
    try:
        latest = conn.execute("SELECT MAX(signal_date) AS d FROM keyword_daily WHERE keyword = ?", (keyword,)).fetchone()["d"]
        if not latest:
            return {"keyword": keyword, "days": days, "data": []}
        rows = conn.execute("""
            SELECT signal_date, platform, SUM(mentions) AS mentions
            FROM keyword_daily
            WHERE keyword = ?
              AND signal_date >= date(?, ?)
            GROUP BY signal_date, platform
            ORDER BY signal_date ASC, platform ASC
        """, (keyword, latest, f"-{days - 1} day")).fetchall()
        return {"keyword": keyword, "days": days, "data": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/keywords/{keyword}/regions")
def keyword_regions(keyword: str, days: int = Query(30, ge=1, le=180)):
    conn = get_db_connection()
    try:
        latest = conn.execute("SELECT MAX(signal_date) AS d FROM keyword_daily WHERE keyword = ?", (keyword,)).fetchone()["d"]
        if not latest:
            return {"keyword": keyword, "days": days, "data": []}
        rows = conn.execute("""
            SELECT region, SUM(mentions) AS mentions
            FROM keyword_daily
            WHERE keyword = ?
              AND signal_date >= date(?, ?)
            GROUP BY region
            ORDER BY mentions DESC
        """, (keyword, latest, f"-{days - 1} day")).fetchall()
        return {"keyword": keyword, "days": days, "data": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/keywords/{keyword}/signals")
def keyword_signals(
    keyword: str,
    limit: int = Query(40, ge=1, le=200),
    platform: str | None = Query(None),
    region: str | None = Query(None),
):
    conn = get_db_connection()
    try:
        clauses = [
            "(LOWER(COALESCE(tag, '')) = LOWER(?) OR LOWER(COALESCE(query, '')) LIKE '%' || LOWER(?) || '%' OR LOWER(COALESCE(text, '')) LIKE '%' || LOWER(?) || '%')"
        ]
        params: list = [keyword, keyword, keyword]
        if platform:
            clauses.append("LOWER(platform) = LOWER(?)")
            params.append(platform)
        if region:
            clauses.append("LOWER(COALESCE(region, '')) = LOWER(?)")
            params.append(region)
        params.append(limit)
        rows = conn.execute(f"""
            SELECT id, collected_at, signal_date, platform, query, tag, region, text
            FROM raw_signals
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC
            LIMIT ?
        """, params).fetchall()
        return {"keyword": keyword, "count": len(rows), "signals": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/keywords/{keyword}/insight")
def keyword_insight(keyword: str):
    """Generate a deterministic, DB-backed explanation without calling an LLM.

    This keeps the dashboard reliable and free of additional API calls. A Gemini
    insight layer can be added later without changing the existing data model.
    """
    conn = get_db_connection()
    try:
        latest = conn.execute("SELECT MAX(signal_date) AS d FROM trend_scores WHERE keyword = ?", (keyword,)).fetchone()["d"]
        if not latest:
            raise HTTPException(status_code=404, detail=f"Keyword not found: {keyword}")

        rows = conn.execute("""
            SELECT signal_date, trend_score, volume_score, velocity_score,
                   persistence_score, cross_platform_score, regional_score,
                   platform_normalized_score
            FROM trend_scores
            WHERE keyword = ?
            ORDER BY signal_date DESC
            LIMIT 2
        """, (keyword,)).fetchall()
        latest_row = rows[0]
        previous = rows[1] if len(rows) > 1 else None

        platforms = conn.execute("""
            SELECT platform, SUM(mentions) AS mentions
            FROM keyword_daily
            WHERE keyword = ? AND signal_date = ?
            GROUP BY platform ORDER BY mentions DESC
        """, (keyword, latest)).fetchall()
        regions = conn.execute("""
            SELECT region, SUM(mentions) AS mentions
            FROM keyword_daily
            WHERE keyword = ? AND signal_date = ?
            GROUP BY region ORDER BY mentions DESC
        """, (keyword, latest)).fetchall()

        score_delta = None if not previous else float(latest_row["trend_score"] or 0) - float(previous["trend_score"] or 0)
        top_platform = dict(platforms[0]) if platforms else None
        top_region = dict(regions[0]) if regions else None
        strongest_metric = max(
            [("volume", latest_row["volume_score"]), ("velocity", latest_row["velocity_score"]),
             ("persistence", latest_row["persistence_score"]), ("cross_platform", latest_row["cross_platform_score"]),
             ("regional", latest_row["regional_score"]), ("platform_normalized", latest_row["platform_normalized_score"])],
            key=lambda x: float(x[1] or 0)
        )
        status = _status_from_row(latest_row, len(rows))

        return {
            "keyword": keyword,
            "date": latest,
            "status": status,
            "score": round(float(latest_row["trend_score"] or 0), 1),
            "score_delta": None if score_delta is None else round(score_delta, 1),
            "strongest_metric": strongest_metric[0],
            "strongest_metric_score": round(float(strongest_metric[1] or 0), 1),
            "top_platform": top_platform,
            "top_region": top_region,
            "platform_count": len(platforms),
            "insight_key": "rising_velocity" if float(latest_row["velocity_score"] or 0) >= 75 else "cross_platform" if float(latest_row["cross_platform_score"] or 0) >= 75 else "persistence" if float(latest_row["persistence_score"] or 0) >= 60 else "volume",
        }
    finally:
        conn.close()
