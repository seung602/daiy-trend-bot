import sqlite3
import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "beauty_trends.db")


def get_db_connection():
    """
    beauty_trends.db를 읽기 전용으로 연결한다.
    """

    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    conn = sqlite3.connect(
        f"file:{DB_PATH}?mode=ro",
        uri=True,
        timeout=10
    )

    conn.row_factory = sqlite3.Row

    return conn
