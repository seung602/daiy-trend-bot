# api/trends.py
from fastapi import APIRouter, HTTPException
from api.database import get_db_connection

router = APIRouter(prefix="/api", tags=["Trends"])

@router.get("/dashboard/today")
def get_today_dashboard():
    """오늘 날짜 기준 Trend Score TOP 10 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 가장 최근 수집 날짜 구하기
    cursor.execute("SELECT MAX(signal_date) FROM trend_scores")
    latest_date = cursor.fetchone()[0]
    
    if not latest_date:
        conn.close()
        return {"date": None, "trends": []}

    query = """
        SELECT keyword, trend_score, volume_score, velocity_score, 
               persistence_score, cross_platform_score, regional_score
        FROM trend_scores
        WHERE signal_date = ?
        ORDER BY trend_score DESC
        LIMIT 10
    """
    cursor.execute(query, (latest_date,))
    rows = cursor.fetchall()
    conn.close()
    
    return {
        "date": latest_date,
        "trends": [dict(row) for row in rows]
    }

@router.get("/trends/{keyword}/history")
def get_keyword_history(keyword: str):
    """특정 키워드의 과거 점수 추이 (상승 그래프용)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT signal_date, trend_score, volume_score, velocity_score
        FROM trend_scores
        WHERE keyword = ?
        ORDER BY signal_date ASC
    """
    cursor.execute(query, (keyword,))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        raise HTTPException(status_code=404, detail="해당 키워드의 기록을 찾을 수 없습니다.")
        
    return {
        "keyword": keyword,
        "history": [dict(row) for row in rows]
    }

@router.get("/cross-signal/{keyword}")
def get_cross_signal(keyword: str):
    """플랫폼별 교차 검증 신호 데이터 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 가장 최근 날짜의 플랫폼별 mention 수 집계
    query = """
        SELECT platform, SUM(mentions) as total_mentions
        FROM keyword_daily
        WHERE keyword = ? AND signal_date = (SELECT MAX(signal_date) FROM keyword_daily)
        GROUP BY platform
    """
    cursor.execute(query, (keyword,))
    rows = cursor.fetchall()
    conn.close()
    
    platform_data = {row["platform"]: row["total_mentions"] for row in rows}
    
    return {
        "keyword": keyword,
        "platform_signals": platform_data,
        "cross_market_confirmed": len(platform_data) >= 3  # 3개 이상 플랫폼 감지 시 True
    }

