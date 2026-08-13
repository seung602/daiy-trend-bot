# api/platforms.py
from fastapi import APIRouter
from api.database import get_db_connection

router = APIRouter(prefix="/api/platforms", tags=["Platforms"])

@router.get("/{platform_name}")
def get_platform_signals(platform_name: str, limit: int = 20):
    """특정 플랫폼(youtube, tiktok, amazon 등)의 최근 원본 신호 데이터"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT collected_at, signal_date, tag, region, text
        FROM raw_signals
        WHERE platform = ?
        ORDER BY id DESC
        LIMIT ?
    """
    cursor.execute(query, (platform_name.lower(), limit))
    rows = cursor.fetchall()
    conn.close()
    
    return {
        "platform": platform_name,
        "count": len(rows),
        "signals": [dict(row) for row in rows]
    }

