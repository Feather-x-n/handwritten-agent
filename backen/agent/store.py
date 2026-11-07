#负责将agent的记忆存在SQLite数据库中，提供增删改查接口
from __future__ import annotations
import contextlib
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
#用于建表
SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, seq)
);
"""
#获取当前时间
def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
class SessionStore:
    def __init__(self,path:str = "data/app.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        #使用数据库示例对象建表
        with contextlib.closing(self._connect()) as conn:
            with conn:
                conn.executescript(SCHEMA)
    def _connect(self):
        #创建并返回一个sqlite3数据库连接，设置row_factory为sqlite3.Row以便按列名访问
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn
    #创建新绘话
    def create(self,title:str)->str:
        """创建一个新会话，返回会话ID"""
        session_id = uuid.uuid4().hex[:12]
        now = _now()
        with contextlib.closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    "INSERT INTO sessions(id, title, created_at, updated_at) VALUES(?, ?, ?, ?)",
                    (session_id, title, now, now),
                )
        return session_id
    #获取会话列表，按更新时间降序排列
    def list(self) -> list[dict]:
        with contextlib.closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]
    #判断某个会话 id 在 sessions 表里是否存在，存在返回 True，不存在返回 False
    def exists(self, session_id: str) -> bool:
        with contextlib.closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return row is not None
    #加载某个会话的历史消息 
    def load(self, session_id: str) -> list[dict]:
        with contextlib.closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT payload FROM messages WHERE session_id = ? ORDER BY seq",
                (session_id,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]
    #给某个会话追加消息
    def append(self, session_id: str, messages: list[dict]) -> None:
        if not messages:
            return
        now = _now()
        with contextlib.closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            start = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM messages WHERE session_id = ?",
                (session_id,),
            ).fetchone()[0]
            for offset, message in enumerate(messages, 1):
                conn.execute(
                    "INSERT INTO messages(session_id, seq, payload, created_at) VALUES(?, ?, ?, ?)",
                    (session_id, start + offset, json.dumps(message, ensure_ascii=False), now),
                )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )
    #删除某个会话
    def delete(self, session_id: str) -> None:
        with contextlib.closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))