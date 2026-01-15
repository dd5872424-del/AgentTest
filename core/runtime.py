"""
运行时：图加载、会话管理、执行

使用 LangGraph Checkpointer 管理状态，从 ContentStore 加载资产。
"""
import importlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Optional, Generator, Callable

import msgpack
from langgraph.checkpoint.sqlite import SqliteSaver

from .config import get_config
from .tools import set_stream_callback
from .storage import (
    ConversationStore, ContentStore,
    SQLiteConversationStore, SQLiteContentStore,
)


class Runtime:
    """
    运行时管理器
    
    职责：
    - 加载用户定义的图
    - 管理会话生命周期
    - 执行对话
    - 从资产库加载角色卡等内容
    
    数据存储：
    - app.db: 会话元数据 + LangGraph checkpoint（运行时状态）
    - content.db: 角色卡、预设等创作资产
    """
    
    def __init__(self, 
                 conversations: ConversationStore = None,
                 contents: ContentStore = None,
                 checkpointer: SqliteSaver = None):
        config = get_config()
        
        # 会话存储
        self.conversations = conversations or SQLiteConversationStore(
            config.database.app_path
        )
        
        # 内容资产存储
        self.contents = contents or SQLiteContentStore(
            config.database.content_path
        )
        
        # LangGraph Checkpointer（状态持久化）
        if checkpointer:
            self.checkpointer = checkpointer
            self._checkpoint_conn = checkpointer.conn
        else:
            # 创建 SQLite 连接用于 checkpointer
            db_path = config.database.app_path
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._checkpoint_conn = sqlite3.connect(db_path, check_same_thread=False)
            self.checkpointer = SqliteSaver(self._checkpoint_conn)
    
    # ============================================================
    # 会话管理
    # ============================================================
    
    def create_conversation(
        self, 
        graph_name: str, 
        title: str = None,
        content_refs: dict = None,
        config: dict = None
    ) -> str:
        """
        创建新会话
        
        Args:
            graph_name: 图名称（对应 graphs/ 目录下的文件名）
            title: 会话标题
            content_refs: 关联的内容引用，格式 {"character": "id", "preset": "id", "world_info": ["id1", ...]}
            config: 其他配置参数
        
        Returns:
            conversation_id
        """
        conv_id = str(uuid.uuid4())[:8]
        thread_id = conv_id  # thread_id 直接使用 conv_id
        
        self.conversations.create(
            id=conv_id,
            graph_name=graph_name,
            thread_id=thread_id,
            title=title or f"对话 {conv_id}",
            content_refs=content_refs,
            config=config
        )
        
        return conv_id
    
    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        """获取会话信息"""
        return self.conversations.get(conversation_id)
    
    def list_conversations(self) -> list[dict]:
        """列出所有会话"""
        return self.conversations.list_all()
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """
        删除会话及其所有 checkpoint
        
        Args:
            conversation_id: 会话 ID
            
        Returns:
            是否删除成功
        """
        conv = self.get_conversation(conversation_id)
        if not conv:
            return False
        
        # 删除 checkpoint（通过 thread_id）
        thread_id = conv.get("thread_id", conversation_id)
        try:
            self.checkpointer.delete_thread(thread_id)
        except Exception:
            pass  # checkpoint 可能不存在
        
        # 删除会话记录
        self.conversations.delete(conversation_id)
        return True
    
    def clear_all_conversations(self) -> int:
        """
        清空所有会话
        
        Returns:
            删除的会话数量
        """
        conversations = self.list_conversations()
        count = 0
        for conv in conversations:
            if self.delete_conversation(conv["id"]):
                count += 1
        return count
    
    # ============================================================
    # 资产加载
    # ============================================================
    
    def _build_initial_state(self, conv: dict) -> dict:
        """
        从资产库加载数据，构建初始状态
        
        Args:
            conv: 会话信息字典
        
        Returns:
            初始状态字典
        """
        state = {"messages": []}
        
        # 解析 content_refs
        content_refs = conv.get("content_refs")
        if content_refs:
            if isinstance(content_refs, str):
                content_refs = json.loads(content_refs)
            
            # 加载所有引用的内容
            for content_type, ref in content_refs.items():
                if ref is None:
                    continue
                    
                if isinstance(ref, list):
                    # 列表类型（如 world_info）
                    items = []
                    for item_id in ref:
                        item = self.contents.get(content_type, item_id)
                        if item:
                            items.append(item["data"])
                    if items:
                        state[content_type] = items
                else:
                    # 单值类型（如 character, preset）
                    item = self.contents.get(content_type, ref)
                    if item:
                        state[content_type] = item["data"]
        
        # 合并图的初始状态
        try:
            module = importlib.import_module(f"graphs.{conv['graph_name']}")
            if hasattr(module, "get_initial_state"):
                graph_state = module.get_initial_state()
                # 资产数据优先（覆盖图的默认值）
                for key, value in graph_state.items():
                    if key not in state:
                        state[key] = value
        except ImportError:
            pass
        
        return state
    
    # ============================================================
    # 图加载
    # ============================================================
    
    def load_graph(self, graph_name: str):
        """
        加载图
        
        传入 checkpointer，让图可以持久化状态
        """
        try:
            module = importlib.import_module(f"graphs.{graph_name}")
            importlib.reload(module)
        except ImportError as e:
            raise ValueError(f"找不到图定义: graphs/{graph_name}.py") from e
        
        if not hasattr(module, "build_graph"):
            raise ValueError(f"图模块 {graph_name} 缺少 build_graph 函数")
        
        # 传入 checkpointer
        return module.build_graph(self.checkpointer)
        
    # ============================================================
    # 执行对话
    # ============================================================
    
    def run(self, conversation_id: str, user_input: str, 
            stream_callback: Callable[[str], None] = None) -> dict:
        """
        执行一轮对话
        
        Args:
            conversation_id: 会话 ID
            user_input: 用户输入
            stream_callback: 可选的流式输出回调函数
        
        Returns:
            最终状态字典
        """
        conv = self.get_conversation(conversation_id)
        if not conv:
            raise ValueError(f"会话不存在: {conversation_id}")
        
        graph = self.load_graph(conv["graph_name"])
        thread_id = conv["thread_id"]
        config = {"configurable": {"thread_id": thread_id}}
        
        # 检查是否是首次对话（无历史状态）
        current_state = graph.get_state(config)
        
        if current_state.values:
            # 已有状态，追加用户消息
            messages = current_state.values.get("messages", [])
            messages.append({"role": "user", "content": user_input})
            input_state = {
                "messages": messages,
                "user_input": user_input,
                "raw_input": user_input,
            }
        else:
            # 首次对话，加载资产构建初始状态
            input_state = self._build_initial_state(conv)
            input_state["messages"] = [{"role": "user", "content": user_input}]
            input_state["user_input"] = user_input
            input_state["raw_input"] = user_input
        
        # 设置流式回调
        if stream_callback:
            set_stream_callback(stream_callback)
        
        try:
            result = graph.invoke(input_state, config=config)
        finally:
            if stream_callback:
                set_stream_callback(None)
        
        self.conversations.touch(conversation_id)
        return result
    
    def stream(self, conversation_id: str, user_input: str) -> Generator:
        """流式执行对话"""
        conv = self.get_conversation(conversation_id)
        if not conv:
            raise ValueError(f"会话不存在: {conversation_id}")
        
        graph = self.load_graph(conv["graph_name"])
        thread_id = conv["thread_id"]
        config = {"configurable": {"thread_id": thread_id}}
        
        # 检查是否是首次对话
        current_state = graph.get_state(config)
        
        if current_state.values:
            messages = current_state.values.get("messages", [])
            messages.append({"role": "user", "content": user_input})
            input_state = {
                "messages": messages,
                "user_input": user_input,
                "raw_input": user_input,
            }
        else:
            input_state = self._build_initial_state(conv)
            input_state["messages"] = [{"role": "user", "content": user_input}]
            input_state["user_input"] = user_input
            input_state["raw_input"] = user_input
        
        for state in graph.stream(input_state, config=config):
            yield state
        
        self.conversations.touch(conversation_id)
    
    # ============================================================
    # 历史与状态管理
    # ============================================================
    
    def get_history(self, conversation_id: str) -> list[dict]:
        """获取对话历史（从 checkpoint 读取）"""
        conv = self.get_conversation(conversation_id)
        if not conv:
            return []
        
        graph = self.load_graph(conv["graph_name"])
        config = {"configurable": {"thread_id": conv["thread_id"]}}
        
        state = graph.get_state(config)
        if state and state.values:
            return state.values.get("messages", [])
        return []
    
    def get_state(self, conversation_id: str) -> Optional[dict]:
        """获取完整的会话状态"""
        conv = self.get_conversation(conversation_id)
        if not conv:
            return None
        
        graph = self.load_graph(conv["graph_name"])
        config = {"configurable": {"thread_id": conv["thread_id"]}}
        
        state = graph.get_state(config)
        return state.values if state else None
    
    def get_state_history(self, conversation_id: str, limit: int = 10) -> list:
        """获取状态历史（用于时间旅行）"""
        conv = self.get_conversation(conversation_id)
        if not conv:
            return []
        
        graph = self.load_graph(conv["graph_name"])
        config = {"configurable": {"thread_id": conv["thread_id"]}}
        
        history = []
        for state in graph.get_state_history(config):
            history.append({
                "checkpoint_id": state.config.get("configurable", {}).get("checkpoint_id"),
                "step": state.metadata.get("step"),
                "values": state.values,
            })
            if len(history) >= limit:
                break
        
        return history
    
    def rollback_to(self, conversation_id: str, checkpoint_id: str) -> dict:
        """回滚到指定的历史状态"""
        conv = self.get_conversation(conversation_id)
        if not conv:
            raise ValueError(f"会话不存在: {conversation_id}")
        
        graph = self.load_graph(conv["graph_name"])
        config = {
            "configurable": {
                "thread_id": conv["thread_id"],
                "checkpoint_id": checkpoint_id,
            }
        }
        
        state = graph.get_state(config)
        return state.values if state else {}
    
    def regenerate(self, conversation_id: str) -> dict:
        """重新生成最后一条 AI 回复"""
        conv = self.get_conversation(conversation_id)
        if not conv:
            raise ValueError(f"会话不存在: {conversation_id}")
        
        graph = self.load_graph(conv["graph_name"])
        thread_id = conv["thread_id"]
        config = {"configurable": {"thread_id": thread_id}}
        
        # 获取历史状态
        history = list(graph.get_state_history(config))
        
        if len(history) < 2:
            raise ValueError("没有足够的历史记录来重新生成")
        
        # 回到上一个状态（用户消息之前）
        # 找到包含最后一条用户消息但没有 AI 回复的状态
        for state in history[1:]:  # 跳过最新的（包含 AI 回复）
            messages = state.values.get("messages", [])
            if messages and messages[-1].get("role") == "user":
                # 从这个状态重新执行
                result = graph.invoke(
                    None,  # 不传新输入，使用历史状态
                    config={
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_id": state.config["configurable"]["checkpoint_id"],
                        }
                    }
                )
                return result
        
        raise ValueError("找不到可以重新生成的状态")
    
    # ============================================================
    # 直接编辑 State（不创建新 checkpoint）
    # ============================================================
    
    def edit_state(self, conversation_id: str, updates: dict) -> bool:
        """
        直接修改最新 checkpoint 的 state，不创建新 checkpoint
        
        Args:
            conversation_id: 会话 ID
            updates: 要更新的字段，如 {"mood": "开心"} 或整个 messages 列表
        
        Returns:
            是否修改成功
        
        Example:
            # 修改情绪
            runtime.edit_state(conv_id, {"mood": "开心"})
            
            # 修改某条消息
            messages = runtime.get_history(conv_id)
            messages[2]["content"] = "修改后的内容"
            runtime.edit_state(conv_id, {"messages": messages})
        """
        conv = self.get_conversation(conversation_id)
        if not conv:
            return False
        
        thread_id = conv["thread_id"]
        
        # 读取最新 checkpoint
        cursor = self._checkpoint_conn.execute("""
            SELECT checkpoint_id, checkpoint 
            FROM checkpoints 
            WHERE thread_id = ? AND checkpoint_ns = ''
            ORDER BY checkpoint_id DESC
            LIMIT 1
        """, (thread_id,))
        row = cursor.fetchone()
        
        if not row:
            return False
        
        checkpoint_id, checkpoint_blob = row
        
        # 反序列化
        checkpoint_data = msgpack.unpackb(checkpoint_blob, raw=False)
        
        # 修改 channel_values
        channel_values = checkpoint_data.get("channel_values", {})
        channel_values.update(updates)
        checkpoint_data["channel_values"] = channel_values
        
        # 重新序列化
        new_blob = msgpack.packb(checkpoint_data, use_bin_type=True)
        
        # 写回数据库
        self._checkpoint_conn.execute("""
            UPDATE checkpoints 
            SET checkpoint = ?
            WHERE thread_id = ? AND checkpoint_ns = '' AND checkpoint_id = ?
        """, (new_blob, thread_id, checkpoint_id))
        self._checkpoint_conn.commit()
        
        return True
    
    def edit_message(self, conversation_id: str, message_index: int, 
                     new_content: str) -> bool:
        """
        编辑指定位置的消息内容
        
        Args:
            conversation_id: 会话 ID
            message_index: 消息索引（0-based）
            new_content: 新的消息内容
        
        Returns:
            是否修改成功
        """
        messages = self.get_history(conversation_id)
        if not messages or message_index < 0 or message_index >= len(messages):
            return False
        
        messages[message_index]["content"] = new_content
        return self.edit_state(conversation_id, {"messages": messages})
    
    def delete_message(self, conversation_id: str, message_index: int) -> bool:
        """
        删除指定位置的消息
        
        Args:
            conversation_id: 会话 ID
            message_index: 消息索引（0-based）
        
        Returns:
            是否删除成功
        """
        messages = self.get_history(conversation_id)
        if not messages or message_index < 0 or message_index >= len(messages):
            return False
        
        del messages[message_index]
        return self.edit_state(conversation_id, {"messages": messages})
    
    def delete_messages_after(self, conversation_id: str, message_index: int) -> bool:
        """
        删除指定位置之后的所有消息（保留该消息）
        
        Args:
            conversation_id: 会话 ID
            message_index: 消息索引（0-based），该消息会被保留
        
        Returns:
            是否删除成功
        """
        messages = self.get_history(conversation_id)
        if not messages or message_index < 0 or message_index >= len(messages):
            return False
        
        messages = messages[:message_index + 1]
        return self.edit_state(conversation_id, {"messages": messages})