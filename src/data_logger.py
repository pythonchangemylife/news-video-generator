"""Data logger module - SQLite storage for publish records and metrics."""

import os
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "news_data.db")


def get_conn():
    """获取数据库连接"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表结构。"""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS publications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT UNIQUE NOT NULL,
            news_date TEXT NOT NULL,
            title TEXT,
            main_topic TEXT,
            is_exploration INTEGER DEFAULT 0,
            video_path TEXT,
            content_type TEXT DEFAULT 'summary',
            title_template TEXT DEFAULT 'main',
            publish_time TEXT,
            status TEXT DEFAULT 'pending',
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', '+8 hours'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS metrics_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            check_time TEXT NOT NULL,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            FOREIGN KEY (video_id) REFERENCES publications(video_id)
        )
    """)
    conn.commit()
    conn.close()


def log_publish(video_id, news_date, title="", main_topic="",
                is_exploration=False, video_path="",
                content_type="summary", title_template="main"):
    """记录发布信息到数据库。"""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO publications
                (video_id, news_date, title, main_topic, is_exploration,
                 video_path, content_type, title_template)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video_id, news_date, title, main_topic,
            1 if is_exploration else 0,
            video_path, content_type, title_template
        ))
        conn.commit()
    except Exception as e:
        print(f"[DB] Log error: {e}")
    finally:
        conn.close()


def update_publish_time(video_id):
    """更新发布时间为当前时间。"""
    conn = get_conn()
    now = (datetime.utcnow() + timedelta(hours=8)).isoformat()
    conn.execute(
        "UPDATE publications SET publish_time = ?, status = 'published' WHERE video_id = ?",
        (now, video_id)
    )
    conn.commit()
    conn.close()


def get_pending_metrics_videos(hours=48):
    """获取待回填指标的视频。"""
    conn = get_conn()
    threshold = (datetime.utcnow() + timedelta(hours=8) - timedelta(hours=hours)).isoformat()
    rows = conn.execute("""
        SELECT video_id, title, publish_time
        FROM publications
        WHERE publish_time > ? AND status = 'published'
        ORDER BY publish_time DESC
    """, (threshold,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
