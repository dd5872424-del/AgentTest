"""
内存存储实现

适用场景：测试、临时会话、不需要持久化的场景

注意：消息和记忆现在由 LangGraph checkpointer 管理，不再使用独立存储。
"""
from __future__ import annotations

from typing import Optional
from datetime import datetime

from .base import ConversationStore, ContentStore


class InMemoryConversationStore(ConversationStore):
    """内存会话存储"""
    
    def __init__(self):
        self._conversations: dict[str, dict] = {}
    
    def create(self, id: str, graph_name: str, thread_id: str,
               title: str = None, content_refs: dict = None,
               config: dict = None):
        now = datetime.now().isoformat()
        self._conversations[id] = {
            "id": id,
            "graph_name": graph_name,
            "thread_id": thread_id,
            "title": title,
            "content_refs": content_refs,
            "config": config,
            "created_at": now,
            "updated_at": now
        }
    
    def get(self, conversation_id: str) -> Optional[dict]:
        return self._conversations.get(conversation_id)
    
    def update(self, conversation_id: str, **fields):
        if conversation_id in self._conversations:
            self._conversations[conversation_id].update(fields)
    
    def delete(self, conversation_id: str):
        self._conversations.pop(conversation_id, None)
    
    def list_all(self) -> list[dict]:
        return sorted(
            self._conversations.values(),
            key=lambda x: x.get("updated_at", ""),
            reverse=True
        )
    
    def touch(self, conversation_id: str):
        if conversation_id in self._conversations:
            self._conversations[conversation_id]["updated_at"] = \
                datetime.now().isoformat()


class InMemoryContentStore(ContentStore):
    """
    内存内容存储
    
    适用场景：测试、临时会话、不需要持久化的场景
    """
    
    def __init__(self):
        # 使用 (type, id, scope) 作为 key
        self._contents: dict[tuple[str, str, str], dict] = {}
    
    def _make_key(self, type: str, id: str, scope: str) -> tuple:
        return (type, id, scope)
    
    def save(self, type: str, id: str, data: dict,
             scope: str = "global", tags: list[str] = None) -> None:
        """保存内容（Upsert：存在则更新，不存在则创建）"""
        key = self._make_key(type, id, scope)
        now = datetime.now().isoformat()
        
        existing = self._contents.get(key)
        created_at = existing["created_at"] if existing else now
        
        self._contents[key] = {
            "id": id,
            "type": type,
            "scope": scope,
            "data": data,
            "tags": tags,
            "created_at": created_at,
            "updated_at": now,
        }
    
    def get(self, type: str, id: str, scope: str = "global") -> Optional[dict]:
        """获取单个内容，不存在返回 None"""
        key = self._make_key(type, id, scope)
        return self._contents.get(key)
    
    def list(self, type: str, scope: str = "global",
             tags: list[str] = None) -> list[dict]:
        """列出指定类型的所有内容，可按 tags 筛选"""
        results = []
        
        for key, item in self._contents.items():
            item_type, _, item_scope = key
            if item_type != type or item_scope != scope:
                continue
            
            # 按标签筛选（包含任一标签即匹配）
            if tags:
                item_tags = item.get("tags") or []
                if not any(t in item_tags for t in tags):
                    continue
            
            results.append(item)
        
        # 按更新时间降序排序
        results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return results
    
    def delete(self, type: str, id: str, scope: str = "global") -> bool:
        """删除内容（硬删除），返回是否删除成功"""
        key = self._make_key(type, id, scope)
        if key in self._contents:
            del self._contents[key]
            return True
        return False
    
    def exists(self, type: str, id: str, scope: str = "global") -> bool:
        """检查内容是否存在"""
        key = self._make_key(type, id, scope)
        return key in self._contents
    
    def search(self, type: str, keyword: str,
               scope: str = "global") -> list[dict]:
        """在 data 中搜索关键词"""
        import json
        results = []
        
        for key, item in self._contents.items():
            item_type, _, item_scope = key
            if item_type != type or item_scope != scope:
                continue
            
            # 在 data 的 JSON 字符串中搜索
            data_str = json.dumps(item.get("data", {}), ensure_ascii=False)
            if keyword in data_str:
                results.append(item)
        
        # 按更新时间降序排序
        results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return results
