"""
存储层：可扩展的数据存储抽象

使用方式：
    from core.storage import ConversationStore, ContentStore
    from core.storage import SQLiteConversationStore, SQLiteContentStore
    from core.storage import InMemoryConversationStore, InMemoryContentStore

注意：消息和记忆现在由 LangGraph checkpointer 管理，不再使用独立存储。
"""

from .base import (
    ConversationStore,
    ContentStore,
)
from .sqlite import (
    SQLiteConversationStore,
    SQLiteContentStore,
)
from .memory import (
    InMemoryConversationStore,
    InMemoryContentStore,
)

__all__ = [
    # 抽象接口
    "ConversationStore",
    "ContentStore",
    # SQLite 实现
    "SQLiteConversationStore",
    "SQLiteContentStore",
    # 内存实现
    "InMemoryConversationStore",
    "InMemoryContentStore",
]
