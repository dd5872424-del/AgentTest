"""
存储层抽象接口

定义三种存储的标准接口，具体实现可以是 SQLite、JSON、内存等
"""
from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime


# ============================================================
# 数据模型
# ============================================================

@dataclass
class Message:
    """消息数据模型"""
    id: int = None
    conversation_id: str = ""
    role: str = ""           # user / assistant / system
    content: str = ""
    metadata: dict = None
    created_at: datetime = None


@dataclass
class Memory:
    """记忆数据模型"""
    id: int = None
    conversation_id: str = ""
    type: str = "default"
    content: str = ""
    metadata: dict = None
    embedding: list = None   # 向量（可选）
    created_at: datetime = None


@dataclass
class Conversation:
    """会话数据模型"""
    id: str = ""
    graph_name: str = ""
    thread_id: str = ""
    title: str = ""
    config: dict = None
    created_at: datetime = None
    updated_at: datetime = None


# ============================================================
# 消息存储接口
# ============================================================

class MessageStore(ABC):
    """
    消息存储抽象接口
    
    职责：存储对话消息历史
    """
    
    @abstractmethod
    def add(self, conversation_id: str, role: str, content: str, 
            metadata: dict = None) -> int:
        """添加消息，返回消息 ID"""
        pass
    
    @abstractmethod
    def get_by_conversation(self, conversation_id: str, 
                           limit: int = 100) -> list[dict]:
        """获取会话的所有消息"""
        pass
    
    @abstractmethod
    def get_recent(self, conversation_id: str, n: int = 5) -> list[dict]:
        """获取最近 n 条消息"""
        pass
    
    @abstractmethod
    def update(self, message_id: int, new_content: str):
        """更新消息内容"""
        pass
    
    @abstractmethod
    def delete(self, message_id: int):
        """删除单条消息"""
        pass
    
    @abstractmethod
    def delete_after(self, conversation_id: str, message_id: int):
        """删除某条消息之后的所有消息"""
        pass
    
    @abstractmethod
    def clear(self, conversation_id: str):
        """清空会话的所有消息"""
        pass


# ============================================================
# 记忆存储接口
# ============================================================

class MemoryStore(ABC):
    """
    记忆存储抽象接口
    
    职责：存储长期记忆，支持检索
    """
    
    @abstractmethod
    def add(self, conversation_id: str, content: str, 
            type: str = "default", metadata: dict = None) -> int:
        """添加记忆，返回记忆 ID"""
        pass
    
    @abstractmethod
    def search(self, conversation_id: str, query: str = None, 
               top_k: int = 5) -> list[dict]:
        """
        检索记忆
        
        Args:
            conversation_id: 会话 ID
            query: 查询文本（用于语义检索，可选）
            top_k: 返回条数
        """
        pass
    
    @abstractmethod
    def delete_by_keyword(self, conversation_id: str, keyword: str):
        """删除包含关键词的记忆"""
        pass
    
    @abstractmethod
    def clear(self, conversation_id: str):
        """清空会话的所有记忆"""
        pass


# ============================================================
# 会话存储接口
# ============================================================

class ConversationStore(ABC):
    """
    会话存储抽象接口
    
    职责：管理会话元信息
    """
    
    @abstractmethod
    def create(self, id: str, graph_name: str, thread_id: str,
               title: str = None, config: dict = None):
        """创建会话"""
        pass
    
    @abstractmethod
    def get(self, conversation_id: str) -> Optional[dict]:
        """获取会话信息"""
        pass
    
    @abstractmethod
    def update(self, conversation_id: str, **fields):
        """更新会话字段"""
        pass
    
    @abstractmethod
    def delete(self, conversation_id: str):
        """删除会话"""
        pass
    
    @abstractmethod
    def list_all(self) -> list[dict]:
        """列出所有会话"""
        pass
    
    @abstractmethod
    def touch(self, conversation_id: str):
        """更新会话的最后访问时间"""
        pass
