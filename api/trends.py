from fastapi import APIRouter, HTTPException
from api.database import get_db_connection


router = APIRouter(
    prefix="/api",
    tags=["Trends"]
)


# ============================================================
# 오늘의 TOP 트렌드
# ============================================================

@router.get("/dashboard/today")
def get_today_dashboard(limit: int = 10):

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT MAX(signal_date)
            FROM trend_scores
        """)

        latest_date = cursor.fetchone()[0]

        if not latest_date:
            return {
                "date": None,
                "trends": []
            }

        cursor.execute("""
            SELECT
                t.keyword,
                t.trend_score,
                t.volume_score,
                t.velocity_score,
                t.persistence_score,
                t.cross_platform_score,
                t.regional_score,
                t.platform_normalized_score,
                (
                    SELECT GROUP_CONCAT(DISTINCT k.platform)
                    FROM keyword_daily k
                    WHERE k.keyword = t.keyword
                      AND k.signal_date = t.signal_date
                      AND k.mentions > 0
                ) AS platforms
            FROM trend_scores t
            WHERE t.signal_date = ?
            ORDER BY t.trend_score DESC
            LIMIT ?
        """, (latest_date, limit))

        rows = cursor.fetchall()
        trends = []
        for row in rows:
            item = dict(row)
            plats = item.pop("platforms", None) or ""
            item["platforms"] = [p for p in plats.split(",") if p]
            trends.append(item)

        return {
            "date": latest_date,
            "count": len(trends),
            "trends": trends
        }

    finally:
        conn.close()


# ============================================================
# 특정 키워드의 과거 추이
# ============================================================

@router.get("/trends/{keyword}/history")
def get_keyword_history(keyword: str):

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                signal_date,
                trend_score,
                volume_score,
                velocity_score,
                persistence_score,
                cross_platform_score,
                regional_score
            FROM trend_scores
            WHERE keyword = ?
            ORDER BY signal_date ASC
        """, (keyword,))

        rows = cursor.fetchall()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"Keyword not found: {keyword}"
            )

        return {
            "keyword": keyword,
            "history": [dict(row) for row in rows]
        }

    finally:
        conn.close()


# ============================================================
# 플랫폼 교차 신호
# ============================================================

@router.get("/cross-signal/{keyword}")
def get_cross_signal(keyword: str):

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                platform,
                SUM(mentions) AS total_mentions
            FROM keyword_daily
            WHERE keyword = ?
              AND signal_date = (
                  SELECT MAX(signal_date)
                  FROM keyword_daily
              )
            GROUP BY platform
            ORDER BY total_mentions DESC
        """, (keyword,))

        rows = cursor.fetchall()

        platform_data = {
            row["platform"]: row["total_mentions"]
            for row in rows
        }

        return {
            "keyword": keyword,
            "platform_signals": platform_data,
            "platform_count": len(platform_data),
            "cross_market_confirmed": len(platform_data) >= 3
        }

    finally:
        conn.close()


# ============================================================
# 전체 키워드 랭킹
# ============================================================

@router.get("/trends")
def get_trends(limit: int = 50):

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT MAX(signal_date)
            FROM trend_scores
        """)

        latest_date = cursor.fetchone()[0]

        if not latest_date:
            return {
                "date": None,
                "trends": []
            }

        cursor.execute("""
            SELECT *
            FROM trend_scores
            WHERE signal_date = ?
            ORDER BY trend_score DESC
            LIMIT ?
        """, (latest_date, limit))

        rows = cursor.fetchall()

        return {
            "date": latest_date,
            "trends": [dict(row) for row in rows]
        }

    finally:
        conn.close()
