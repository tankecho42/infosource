"""
InfoSource — 统一多源信息推荐系统
数据库初始化与连接管理。

Tables:
  sources       — 信息来源注册表（领研网/Twitter/...）
  articles      — 所有来源的文章统一存储
  pushed        — 推送记录与反馈
  preferences   — 推荐偏好（KV存储，JSON值）
"""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path.home() / ".hermes" / "scripts" / "infosource" / "feeds.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    key             TEXT PRIMARY KEY,       -- 'linkresearcher', 'twitter'
    name            TEXT NOT NULL,          -- '领研网', 'Twitter'
    prefix          TEXT NOT NULL,          -- 'lr', 'tw' — UID前缀
    enabled         INTEGER DEFAULT 1,      -- 0=关 1=开
    check_interval  INTEGER DEFAULT 30,     -- 检查间隔（分钟）
    last_check      TEXT,                   -- ISO timestamp
    config          TEXT,                   -- JSON: 来源特定配置
    total_pushed    INTEGER DEFAULT 0,
    total_feedback  INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uid         TEXT UNIQUE NOT NULL,        -- 'lr:abc-123', 'tw:98765'
    source      TEXT NOT NULL,              -- sources.key
    title       TEXT NOT NULL,
    url         TEXT,
    content     TEXT,                       -- 正文摘要
    domains     TEXT,                       -- JSON array: 匹配到的领域
    published_at TEXT,                      -- 原始发布时间（各来源自填，可能为NULL）
    fetched_at  TEXT DEFAULT (datetime('now', 'localtime')),
    pushed      INTEGER DEFAULT 0,          -- 0=未推 1=已推
    FOREIGN KEY (source) REFERENCES sources(key)
);

CREATE TABLE IF NOT EXISTS pushed (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    uid          TEXT NOT NULL,
    source       TEXT NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT,
    summary      TEXT,                      -- Echo的摘要
    score        REAL,
    pushed_at    TEXT DEFAULT (datetime('now', 'localtime')),
    feedback     INTEGER,                   -- NULL=未反馈 1=好 -1=差 0=一般
    feedback_at  TEXT
);

CREATE TABLE IF NOT EXISTS preferences (
    key   TEXT PRIMARY KEY,
    value TEXT                              -- JSON
);

CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_pushed ON articles(pushed);
CREATE INDEX IF NOT EXISTS idx_pushed_uid ON pushed(uid);
CREATE INDEX IF NOT EXISTS idx_pushed_source ON pushed(source);
"""


def get_db() -> sqlite3.Connection:
    """获取数据库连接（启用WAL模式，提高并发读性能）"""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    conn.executescript(_SCHEMA)
    conn.close()


def safe_commit(conn):
    """带重试的commit（应对SQLite锁）"""
    for attempt in range(5):
        try:
            conn.commit()
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e) or "busy" in str(e):
                time.sleep(0.3 * (2 ** attempt))
            else:
                raise


def pref_get(conn, key, default=None):
    """读取偏好值（JSON自动反序列化）"""
    row = conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
    if row is None:
        return default
    return json.loads(row["value"])


def pref_set(conn, key, value):
    """写入偏好值（JSON自动序列化）"""
    conn.execute(
        "INSERT INTO preferences (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )


if __name__ == "__main__":
    init_db()
    print(f"✓ Database initialized at {DB_PATH}")
