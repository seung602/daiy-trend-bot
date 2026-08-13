# api/reports.py
from fastapi import APIRouter
from api.database import get_db_connection

router = APIRouter(prefix="/api/reports", tags=["Reports"])

@router.get("/summary")
def get_reports_summary():
    """최근 생성된 요약 리포트 내역"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # google_keyword_history 등 요약 관련 최신 테이블에서 조회
    cursor.execute("SELECT MAX(signal_date) FROM keyword_daily")
    latest_date = cursor.fetchone()[0]
    conn.close()
    
    return {
        "latest_date": latest_date,
        "status": "active"
    }

