from fastapi import APIRouter
from api.database import get_db_connection


router = APIRouter(
    prefix="/api/platforms",
    tags=["Platforms"]
)


# ============================================================
# 플랫폼별 최근 원본 데이터
# ============================================================

@router.get("/{platform_name}")
def get_platform_signals(
    platform_name: str,
    limit: int = 50
):

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id,
                collected_at,
                signal_date,
                platform,
                query,
                tag,
                region,
                text
            FROM raw_signals
            WHERE LOWER(platform) = LOWER(?)
            ORDER BY id DESC
            LIMIT ?
        """, (platform_name, limit))

        rows = cursor.fetchall()

        return {
            "platform": platform_name,
            "count": len(rows),
            "signals": [dict(row) for row in rows]
        }

    finally:
        conn.close()


# ============================================================
# 플랫폼별 일간 집계
# ============================================================

@router.get("/{platform_name}/daily")
def get_platform_daily(
    platform_name: str,
    days: int = 30
):

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                signal_date,
                SUM(mentions) AS mentions
            FROM keyword_daily
            WHERE LOWER(platform) = LOWER(?)
            GROUP BY signal_date
            ORDER BY signal_date DESC
            LIMIT ?
        """, (platform_name, days))

        rows = cursor.fetchall()

        return {
            "platform": platform_name,
            "days": len(rows),
            "data": [dict(row) for row in rows]
        }

    finally:
        conn.close()


# ============================================================
# 플랫폼별 인기 키워드
# ============================================================

@router.get("/{platform_name}/keywords")
def get_platform_keywords(
    platform_name: str,
    limit: int = 30
):

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                keyword,
                SUM(mentions) AS mentions
            FROM keyword_daily
            WHERE LOWER(platform) = LOWER(?)
            GROUP BY keyword
            ORDER BY mentions DESC
            LIMIT ?
        """, (platform_name, limit))

        rows = cursor.fetchall()

        return {
            "platform": platform_name,
            "keywords": [dict(row) for row in rows]
        }

    finally:
        conn.close()
