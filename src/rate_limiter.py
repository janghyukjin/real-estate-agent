"""
SQLite 기반 Rate Limiter

- IP별 일일 질문 횟수 제한
- 질문/답변 내용은 저장하지 않음 (개인정보 보호)
"""

import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "usage.db"

DAILY_LIMIT = 10


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_count (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', '+9 hours'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_ip_date
        ON usage_count (ip, created_at)
    """)
    conn.commit()
    return conn


_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _get_conn()
    return _conn


def get_today_count(ip: str) -> int:
    """오늘 해당 IP의 질문 횟수 조회"""
    today = date.today().isoformat()
    row = _db().execute(
        "SELECT COUNT(*) FROM usage_count WHERE ip = ? AND created_at >= ?",
        (ip, today),
    ).fetchone()
    return row[0] if row else 0


def check_limit(ip: str) -> tuple[bool, int]:
    """제한 확인. (허용 여부, 남은 횟수) 반환"""
    count = get_today_count(ip)
    remaining = max(0, DAILY_LIMIT - count)
    return remaining > 0, remaining


def log_question(ip: str) -> None:
    """사용 횟수만 기록 (질문/답변 내용 저장 안 함)"""
    _db().execute(
        "INSERT INTO usage_count (ip) VALUES (?)",
        (ip,),
    )
    _db().commit()


def get_stats() -> dict:
    """간단한 사용 통계"""
    today = date.today().isoformat()
    db = _db()
    today_total = db.execute(
        "SELECT COUNT(*) FROM usage_count WHERE created_at >= ?", (today,)
    ).fetchone()[0]
    total = db.execute("SELECT COUNT(*) FROM usage_count").fetchone()[0]
    unique_ips = db.execute(
        "SELECT COUNT(DISTINCT ip) FROM usage_count"
    ).fetchone()[0]
    return {
        "today_questions": today_total,
        "total_questions": total,
        "unique_users": unique_ips,
    }
