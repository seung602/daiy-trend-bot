# api/database.py
import sqlite3
import os

# 루트 경로의 beauty_trends.db 가리키기
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "beauty_trends.db")

def get_db_connection():
    """
    SQLite DB를 Read-Only URI 모드로 안전하게 연결합니다.
    """
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"DB 파일을 찾을 수 없습니다: {DB_PATH}")
        
    # mode=ro 설정으로 GitHub Actions의 DB 쓰기 작업과 충돌을 방지합니다.
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row  # 결과를 딕셔너리 형태로 반환
    return conn

