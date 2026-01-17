"""
存储层抽象接口

定义存储的标准接口，具体实现可以是 SQLite、JSON、内存等。

注意：消息和记忆现在由 LangGraph checkpointer 管理，不再使用独立存储。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


# ============================================================
# 数据模型
# ============================================================

@dataclass
class Conversation:
    """会话数据模型"""
    id: str = ""
    graph_name: str = ""
    thread_id: str = ""
    title: str = ""
    content_refs: dict = None  # {"character": "id", "preset": "id", "world_info": ["id1", "id2"]}
    config: dict = None
    created_at: datetime = None
    updated_at: datetime = None


@dataclass
class Content:
    """
    通用内容数据模型
    
    用于存储角色卡、World Info、预设等结构化内容。
    
    Attributes:
        id: 用户指定的唯一标识（如 "luna", "magic_system"）
        type: 内容类型（character, world_info, preset, ...）
        data: JSON 格式的内容数据（不做 schema 验证）
        scope: 作用域，"global" 表示全局，或为 conversation_id
        tags: 可选标签列表，便于筛选
        created_at: 创建时间
        updated_at: 更新时间
    """
    id: str = ""
    type: str = ""
    data: dict = None
    scope: str = "global"
    tags: list = None
    created_at: datetime = None
    updated_at: datetime = None


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
               title: str = None, content_refs: dict = None,
               config: dict = None):
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


# ============================================================
# 内容存储接口
# ============================================================

class ContentStore(ABC):
    """
    通用内容存储抽象接口
    
    职责：存储角色卡、World Info、预设等结构化内容
    
    设计决策：
    - ID 策略：用户指定（可读性好、导入导出稳定）
    - 删除策略：硬删除（保持简单）
    - 冲突策略：Upsert（save 一个方法搞定）
    - Schema 验证：不验证（保持灵活，让 graph 层决定）
    
    使用示例::
    
        store = SQLiteContentStore("data/content.db")
        
        # 保存角色卡
        store.save("character", "luna", {
            "name": "Luna",
            "description": "A mysterious witch...",
        }, tags=["fantasy"])
        
        # 获取角色卡
        luna = store.get("character", "luna")
        
        # 列出所有角色
        characters = store.list("character")
    """
    
    @abstractmethod
    def save(self, type: str, id: str, data: dict,
             scope: str = "global", tags: list[str] = None) -> None:
        """
        保存内容（Upsert：存在则更新，不存在则创建）
        
        Args:
            type: 内容类型（如 "character", "world_info", "preset"）
            id: 用户指定的唯一标识
            data: 内容数据（dict，会被 JSON 序列化）
            scope: 作用域，默认 "global"，也可为 conversation_id
            tags: 可选标签列表
        """
        pass
    
    @abstractmethod
    def get(self, type: str, id: str, scope: str = "global") -> Optional[dict]:
        """
        获取单个内容
        
        Args:
            type: 内容类型
            id: 内容 ID
            scope: 作用域
            
        Returns:
            内容数据字典，不存在返回 None
        """
        pass
    
    @abstractmethod
    def list(self, type: str, scope: str = "global",
             tags: list[str] = None) -> list[dict]:
        """
        列出指定类型的所有内容
        
        Args:
            type: 内容类型
            scope: 作用域，默认 "global"
            tags: 可选，按标签筛选（包含任一标签即匹配）
            
        Returns:
            内容列表
        """
        pass
    
    @abstractmethod
    def delete(self, type: str, id: str, scope: str = "global") -> bool:
        """
        删除内容（硬删除）
        
        Args:
            type: 内容类型
            id: 内容 ID
            scope: 作用域
            
        Returns:
            是否删除成功（内容存在且被删除返回 True）
        """
        pass
    
    @abstractmethod
    def exists(self, type: str, id: str, scope: str = "global") -> bool:
        """
        检查内容是否存在
        
        Args:
            type: 内容类型
            id: 内容 ID
            scope: 作用域
            
        Returns:
            是否存在
        """
        pass
    
    @abstractmethod
    def search(self, type: str, keyword: str, 
               scope: str = "global") -> list[dict]:
        """
        在 data 中搜索关键词
        
        Args:
            type: 内容类型
            keyword: 搜索关键词
            scope: 作用域
            
        Returns:
            匹配的内容列表
        """
        pass
