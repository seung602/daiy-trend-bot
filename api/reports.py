from fastapi import APIRouter
from api.database import get_db_connection


router = APIRouter(
    prefix="/api/reports",
    tags=["Reports"]
)


@router.get("/status")
def get_report_status():

    conn = get_db_connection()

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT MAX(signal_date)
            FROM trend_scores
        """)

        latest_trend_date = cursor.fetchone()[0]

        cursor.execute("""
            SELECT MAX(signal_date)
            FROM keyword_daily
        """)

        latest_signal_date = cursor.fetchone()[0]

        return {
            "status": "active",
            "latest_trend_date": latest_trend_date,
            "latest_signal_date": latest_signal_date
        }

    finally:
        conn.close()
