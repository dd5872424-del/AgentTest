"""
SQLite 存储实现

使用线程本地存储管理连接，避免频繁创建连接的开销。
"""
import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional
from datetime import datetime
from contextlib import contextmanager

from .base import MessageStore, MemoryStore, ConversationStore


class SQLiteConnectionMixin:
    """
    SQLite 连接管理混入类
    
    使用线程本地存储复用连接，提升性能。
    """
    db_path: str
    _local: threading.local
    
    def _init_connection(self):
        """初始化连接管理"""
        self._local = threading.local()
    
    @property
    def conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path, 
                check_same_thread=False,
                timeout=30.0
            )
            self._local.conn.row_factory = sqlite3.Row
            # 启用 WAL 模式提升并发性能
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn
    
    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        conn = self.conn
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def close(self):
        """关闭当前线程的连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


class SQLiteMessageStore(SQLiteConnectionMixin, MessageStore):
    """SQLite 消息存储"""
    
    def __init__(self, db_path: str = "data/messages.db"):
        self.db_path = db_path
        self._init_connection()
        self._ensure_table()
    
    def _ensure_table(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conv 
                ON messages(conversation_id)
            """)
    
    def add(self, conversation_id: str, role: str, content: str,
            metadata: dict = None) -> int:
        with self.transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO messages (conversation_id, role, content, metadata)
                VALUES (?, ?, ?, ?)
            """, (conversation_id, role, content, 
                  json.dumps(metadata) if metadata else None))
            return cursor.lastrowid
    
    def get_by_conversation(self, conversation_id: str, 
                           limit: int = 100) -> list[dict]:
        cursor = self.conn.execute("""
            SELECT id, role, content, metadata, created_at
            FROM messages 
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            LIMIT ?
        """, (conversation_id, limit))
        return [dict(row) for row in cursor.fetchall()]
    
    def get_recent(self, conversation_id: str, n: int = 5) -> list[dict]:
        cursor = self.conn.execute("""
            SELECT id, role, content, metadata, created_at
            FROM messages 
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (conversation_id, n))
        rows = [dict(row) for row in cursor.fetchall()]
        return list(reversed(rows))
    
    def update(self, message_id: int, new_content: str):
        with self.transaction() as conn:
            conn.execute(
                "UPDATE messages SET content = ? WHERE id = ?",
                (new_content, message_id)
            )
    
    def delete(self, message_id: int):
        with self.transaction() as conn:
            conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    
    def delete_after(self, conversation_id: str, message_id: int):
        with self.transaction() as conn:
            conn.execute("""
                DELETE FROM messages 
                WHERE conversation_id = ? AND id > ?
            """, (conversation_id, message_id))
    
    def clear(self, conversation_id: str):
        with self.transaction() as conn:
            conn.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,)
            )


class SQLiteMemoryStore(SQLiteConnectionMixin, MemoryStore):
    """SQLite 记忆存储"""
    
    def __init__(self, db_path: str = "data/memories.db"):
        self.db_path = db_path
        self._init_connection()
        self._ensure_table()
    
    def _ensure_table(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    type TEXT DEFAULT 'default',
                    content TEXT NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_conv 
                ON memories(conversation_id)
            """)
    
    def add(self, conversation_id: str, content: str,
            type: str = "default", metadata: dict = None) -> int:
        with self.transaction() as conn:
            cursor = conn.execute("""
                INSERT INTO memories (conversation_id, type, content, metadata)
                VALUES (?, ?, ?, ?)
            """, (conversation_id, type, content,
                  json.dumps(metadata) if metadata else None))
            return cursor.lastrowid
    
    def search(self, conversation_id: str, query: str = None,
               top_k: int = 5) -> list[dict]:
        # 简单实现：返回最近的 top_k 条
        # 可扩展：添加向量检索
        cursor = self.conn.execute("""
            SELECT id, type, content, metadata, created_at
            FROM memories 
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (conversation_id, top_k))
        return [dict(row) for row in cursor.fetchall()]
    
    def delete_by_keyword(self, conversation_id: str, keyword: str):
        with self.transaction() as conn:
            conn.execute("""
                DELETE FROM memories 
                WHERE conversation_id = ? AND content LIKE ?
            """, (conversation_id, f"%{keyword}%"))
    
    def clear(self, conversation_id: str):
        with self.transaction() as conn:
            conn.execute(
                "DELETE FROM memories WHERE conversation_id = ?",
                (conversation_id,)
            )


class SQLiteConversationStore(SQLiteConnectionMixin, ConversationStore):
    """SQLite 会话存储"""
    
    def __init__(self, db_path: str = "data/app.db"):
        self.db_path = db_path
        self._init_connection()
        self._ensure_table()
    
    def _ensure_table(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    graph_name TEXT NOT NULL,
                    thread_id TEXT UNIQUE NOT NULL,
                    title TEXT,
                    config TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    def create(self, id: str, graph_name: str, thread_id: str,
               title: str = None, config: dict = None):
        with self.transaction() as conn:
            conn.execute("""
                INSERT INTO conversations (id, graph_name, thread_id, title, config)
                VALUES (?, ?, ?, ?, ?)
            """, (id, graph_name, thread_id, title,
                  json.dumps(config) if config else None))
    
    def get(self, conversation_id: str) -> Optional[dict]:
        cursor = self.conn.execute(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def update(self, conversation_id: str, **fields):
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [conversation_id]
        with self.transaction() as conn:
            conn.execute(f"""
                UPDATE conversations SET {set_clause} WHERE id = ?
            """, values)
    
    def delete(self, conversation_id: str):
        with self.transaction() as conn:
            conn.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,)
            )
    
    def list_all(self) -> list[dict]:
        cursor = self.conn.execute("""
            SELECT id, graph_name, title, created_at, updated_at
            FROM conversations
            ORDER BY updated_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    def touch(self, conversation_id: str):
        with self.transaction() as conn:
            conn.execute("""
                UPDATE conversations 
                SET updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (conversation_id,))
