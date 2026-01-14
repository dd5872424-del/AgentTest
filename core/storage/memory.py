"""
内存存储实现

适用场景：测试、临时会话、不需要持久化的场景
"""
from typing import Optional
from datetime import datetime
from collections import defaultdict

from .base import MessageStore, MemoryStore, ConversationStore


class InMemoryMessageStore(MessageStore):
    """内存消息存储"""
    
    def __init__(self):
        self._messages: dict[str, list[dict]] = defaultdict(list)
        self._id_counter = 0
    
    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter
    
    def add(self, conversation_id: str, role: str, content: str,
            metadata: dict = None) -> int:
        msg_id = self._next_id()
        self._messages[conversation_id].append({
            "id": msg_id,
            "role": role,
            "content": content,
            "metadata": metadata,
            "created_at": datetime.now().isoformat()
        })
        return msg_id
    
    def get_by_conversation(self, conversation_id: str,
                           limit: int = 100) -> list[dict]:
        messages = self._messages.get(conversation_id, [])
        return messages[:limit]
    
    def get_recent(self, conversation_id: str, n: int = 5) -> list[dict]:
        messages = self._messages.get(conversation_id, [])
        return messages[-n:] if messages else []
    
    def update(self, message_id: int, new_content: str):
        for messages in self._messages.values():
            for msg in messages:
                if msg["id"] == message_id:
                    msg["content"] = new_content
                    return
    
    def delete(self, message_id: int):
        for conv_id, messages in self._messages.items():
            self._messages[conv_id] = [
                m for m in messages if m["id"] != message_id
            ]
    
    def delete_after(self, conversation_id: str, message_id: int):
        messages = self._messages.get(conversation_id, [])
        # 找到目标消息的索引
        idx = None
        for i, msg in enumerate(messages):
            if msg["id"] == message_id:
                idx = i
                break
        if idx is not None:
            self._messages[conversation_id] = messages[:idx + 1]
    
    def clear(self, conversation_id: str):
        self._messages[conversation_id] = []


class InMemoryMemoryStore(MemoryStore):
    """内存记忆存储"""
    
    def __init__(self):
        self._memories: dict[str, list[dict]] = defaultdict(list)
        self._id_counter = 0
    
    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter
    
    def add(self, conversation_id: str, content: str,
            type: str = "default", metadata: dict = None) -> int:
        mem_id = self._next_id()
        self._memories[conversation_id].append({
            "id": mem_id,
            "type": type,
            "content": content,
            "metadata": metadata,
            "created_at": datetime.now().isoformat()
        })
        return mem_id
    
    def search(self, conversation_id: str, query: str = None,
               top_k: int = 5) -> list[dict]:
        memories = self._memories.get(conversation_id, [])
        # 简单实现：返回最近的 top_k 条
        # 如需语义检索，可在此扩展
        return memories[-top_k:] if memories else []
    
    def delete_by_keyword(self, conversation_id: str, keyword: str):
        memories = self._memories.get(conversation_id, [])
        self._memories[conversation_id] = [
            m for m in memories if keyword not in m["content"]
        ]
    
    def clear(self, conversation_id: str):
        self._memories[conversation_id] = []


class InMemoryConversationStore(ConversationStore):
    """内存会话存储"""
    
    def __init__(self):
        self._conversations: dict[str, dict] = {}
    
    def create(self, id: str, graph_name: str, thread_id: str,
               title: str = None, config: dict = None):
        now = datetime.now().isoformat()
        self._conversations[id] = {
            "id": id,
            "graph_name": graph_name,
            "thread_id": thread_id,
            "title": title,
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
