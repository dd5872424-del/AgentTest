"""
SQLite 存储实现

使用线程本地存储管理连接，避免频繁创建连接的开销。

注意：消息和记忆现在由 LangGraph checkpointer 管理，不再使用独立存储。
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from .base import ConversationStore, ContentStore


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
                    content_refs TEXT,
                    config TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    def create(self, id: str, graph_name: str, thread_id: str,
               title: str = None, content_refs: dict = None,
               config: dict = None):
        with self.transaction() as conn:
            conn.execute("""
                INSERT INTO conversations 
                (id, graph_name, thread_id, title, content_refs, config)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (id, graph_name, thread_id, title,
                  json.dumps(content_refs) if content_refs else None,
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


class SQLiteContentStore(SQLiteConnectionMixin, ContentStore):
    """
    SQLite 内容存储
    
    存储角色卡、World Info、预设等结构化内容。
    """
    
    def __init__(self, db_path: str = "data/content.db"):
        self.db_path = db_path
        self._init_connection()
        self._ensure_table()
    
    def _ensure_table(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contents (
                    id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    scope TEXT DEFAULT 'global',
                    data TEXT NOT NULL,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (type, id, scope)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_contents_type_scope 
                ON contents(type, scope)
            """)
    
    def save(self, type: str, id: str, data: dict,
             scope: str = "global", tags: list[str] = None) -> None:
        """保存内容（Upsert：存在则更新，不存在则创建）"""
        with self.transaction() as conn:
            conn.execute("""
                INSERT INTO contents (type, id, scope, data, tags, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(type, id, scope) DO UPDATE SET
                    data = excluded.data,
                    tags = excluded.tags,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                type, id, scope,
                json.dumps(data, ensure_ascii=False),
                json.dumps(tags, ensure_ascii=False) if tags else None
            ))
    
    def get(self, type: str, id: str, scope: str = "global") -> Optional[dict]:
        """获取单个内容，不存在返回 None"""
        cursor = self.conn.execute("""
            SELECT id, type, scope, data, tags, created_at, updated_at
            FROM contents
            WHERE type = ? AND id = ? AND scope = ?
        """, (type, id, scope))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_dict(row)
    
    def list(self, type: str, scope: str = "global",
             tags: list[str] = None) -> list[dict]:
        """列出指定类型的所有内容，可按 tags 筛选"""
        cursor = self.conn.execute("""
            SELECT id, type, scope, data, tags, created_at, updated_at
            FROM contents
            WHERE type = ? AND scope = ?
            ORDER BY updated_at DESC
        """, (type, scope))
        
        results = []
        for row in cursor.fetchall():
            item = self._row_to_dict(row)
            # 按标签筛选（包含任一标签即匹配）
            if tags:
                item_tags = item.get("tags") or []
                if not any(t in item_tags for t in tags):
                    continue
            results.append(item)
        
        return results
    
    def delete(self, type: str, id: str, scope: str = "global") -> bool:
        """删除内容（硬删除），返回是否删除成功"""
        with self.transaction() as conn:
            cursor = conn.execute("""
                DELETE FROM contents
                WHERE type = ? AND id = ? AND scope = ?
            """, (type, id, scope))
            return cursor.rowcount > 0
    
    def exists(self, type: str, id: str, scope: str = "global") -> bool:
        """检查内容是否存在"""
        cursor = self.conn.execute("""
            SELECT 1 FROM contents
            WHERE type = ? AND id = ? AND scope = ?
        """, (type, id, scope))
        return cursor.fetchone() is not None
    
    def search(self, type: str, keyword: str,
               scope: str = "global") -> list[dict]:
        """在 data 中搜索关键词"""
        cursor = self.conn.execute("""
            SELECT id, type, scope, data, tags, created_at, updated_at
            FROM contents
            WHERE type = ? AND scope = ? AND data LIKE ?
            ORDER BY updated_at DESC
        """, (type, scope, f"%{keyword}%"))
        
        return [self._row_to_dict(row) for row in cursor.fetchall()]
    
    def _row_to_dict(self, row) -> dict:
        """将数据库行转换为字典"""
        return {
            "id": row["id"],
            "type": row["type"],
            "scope": row["scope"],
            "data": json.loads(row["data"]) if row["data"] else {},
            "tags": json.loads(row["tags"]) if row["tags"] else None,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
