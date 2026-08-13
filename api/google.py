from fastapi import APIRouter
from api.database import get_db_connection


router = APIRouter(
    prefix="/api/google",
    tags=["Google"]
)


@router.get("/signals")
def get_google_signals(limit: int = 50):

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                signal_date,
                collected_at,
                region,
                seed_keyword,
                keyword,
                query_type,
                intent,
                interest_score,
                rising_score,
                comparison_group,
                source
            FROM google_signals
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()

        return {
            "count": len(rows),
            "signals": [dict(row) for row in rows]
        }

    finally:
        conn.close()


@router.get("/keywords")
def get_google_keywords(limit: int = 50):

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                keyword,
                COUNT(*) AS signal_count,
                AVG(interest_score) AS avg_interest,
                AVG(rising_score) AS avg_rising
            FROM google_signals
            GROUP BY keyword
            ORDER BY signal_count DESC
            LIMIT ?
        """, (limit,))

        rows = cursor.fetchall()

        return {
            "keywords": [dict(row) for row in rows]
        }

    finally:
        conn.close()
