"""
存储层：可扩展的数据存储抽象

使用方式：
    from core.storage import MessageStore, MemoryStore, ConversationStore
    from core.storage import SQLiteMessageStore, InMemoryMessageStore
"""

from .base import (
    MessageStore,
    MemoryStore, 
    ConversationStore,
)
from .sqlite import (
    SQLiteMessageStore,
    SQLiteMemoryStore,
    SQLiteConversationStore,
)
from .memory import (
    InMemoryMessageStore,
    InMemoryMemoryStore,
    InMemoryConversationStore,
)

__all__ = [
    # 抽象接口
    "MessageStore",
    "MemoryStore",
    "ConversationStore",
    # SQLite 实现
    "SQLiteMessageStore",
    "SQLiteMemoryStore",
    "SQLiteConversationStore",
    # 内存实现
    "InMemoryMessageStore",
    "InMemoryMemoryStore",
    "InMemoryConversationStore",
]
