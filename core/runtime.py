"""
运行时：图加载、会话管理、执行
"""
import importlib
import uuid
from typing import Optional, Generator

from .config import get_config
from .storage import (
    MessageStore, MemoryStore, ConversationStore,
    SQLiteMessageStore, SQLiteMemoryStore, SQLiteConversationStore,
)


class Runtime:
    """
    运行时管理器
    
    职责：
    - 加载用户定义的图
    - 管理会话生命周期
    - 执行对话
    
    存储层可替换：
        runtime = Runtime(
            messages=SQLiteMessageStore("data/msg.db"),
            memories=SQLiteMemoryStore("data/mem.db"),
            conversations=SQLiteConversationStore("data/conv.db"),
        )
        
        # 或使用内存存储（测试用）
        from core.storage import InMemoryMessageStore, ...
        runtime = Runtime(
            messages=InMemoryMessageStore(),
            ...
        )
    """
    
    def __init__(self, 
                 messages: MessageStore = None,
                 memories: MemoryStore = None,
                 conversations: ConversationStore = None):
        config = get_config()
        # 使用传入的存储或从配置读取默认路径
        self.messages = messages or SQLiteMessageStore(config.database.messages_path)
        self.memories = memories or SQLiteMemoryStore(config.database.memories_path)
        self.conversations = conversations or SQLiteConversationStore(config.database.path)
    
    def create_conversation(self, graph_name: str, title: str = None,
                           config: dict = None) -> str:
        """
        创建新会话
        
        Args:
            graph_name: 图名称（对应 graphs/ 目录下的文件名）
            title: 会话标题
            config: 配置参数
        
        Returns:
            conversation_id
        """
        conv_id = str(uuid.uuid4())[:8]
        thread_id = f"thread_{conv_id}"
        
        self.conversations.create(
            id=conv_id,
            graph_name=graph_name,
            thread_id=thread_id,
            title=title or f"对话 {conv_id}",
            config=config
        )
        
        return conv_id
    
    def get_conversation(self, conversation_id: str) -> Optional[dict]:
        """获取会话信息"""
        return self.conversations.get(conversation_id)
    
    def load_graph(self, graph_name: str, conversation_id: str):
        """
        加载图
        
        传入记忆存储，让图可以使用
        """
        try:
            module = importlib.import_module(f"graphs.{graph_name}")
            importlib.reload(module)
        except ImportError as e:
            raise ValueError(f"找不到图定义: graphs/{graph_name}.py") from e
        
        if not hasattr(module, "build_graph"):
            raise ValueError(f"图模块 {graph_name} 缺少 build_graph 函数")
        
        # 传入记忆存储，让图可以使用
        return module.build_graph(conversation_id, self.memories)
    
    def _prepare_execution(self, conversation_id: str, user_input: str) -> tuple:
        """
        准备执行上下文（公共逻辑提取）
        
        Returns:
            tuple: (conv, graph, initial_state)
        """
        conv = self.get_conversation(conversation_id)
        if not conv:
            raise ValueError(f"会话不存在: {conversation_id}")
        
        graph = self.load_graph(conv["graph_name"], conversation_id)
        
        # 从消息存储获取历史
        history = self.messages.get_by_conversation(conversation_id)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": user_input})
        
        # 保存用户消息
        self.messages.add(conversation_id, "user", user_input)
        
        # 构建初始状态
        initial_state = {
            "messages": messages,
            "user_input": user_input,
            "raw_input": user_input,
        }
        
        # 合并图的初始状态
        try:
            module = importlib.import_module(f"graphs.{conv['graph_name']}")
            if hasattr(module, "get_initial_state"):
                initial_state.update(module.get_initial_state())
        except:
            pass
        
        return conv, graph, initial_state
    
    def _save_response(self, conversation_id: str, result: dict):
        """保存 AI 回复（公共逻辑提取）"""
        if result.get("last_output"):
            self.messages.add(conversation_id, "assistant", result["last_output"])
        elif result.get("messages"):
            last_msg = result["messages"][-1]
            if last_msg.get("role") == "assistant":
                self.messages.add(conversation_id, "assistant", last_msg["content"])
        
        self.conversations.touch(conversation_id)
    
    def run(self, conversation_id: str, user_input: str) -> dict:
        """执行一轮对话"""
        conv, graph, initial_state = self._prepare_execution(conversation_id, user_input)
        
        result = graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": conv["thread_id"]}}
        )
        
        self._save_response(conversation_id, result)
        return result
    
    def stream(self, conversation_id: str, user_input: str) -> Generator:
        """流式执行对话"""
        conv, graph, initial_state = self._prepare_execution(conversation_id, user_input)
        
        final_state = None
        for state in graph.stream(
            initial_state,
            config={"configurable": {"thread_id": conv["thread_id"]}}
        ):
            yield state
            final_state = state
        
        # 从流式结果中提取最终输出
        if final_state:
            for node_output in final_state.values():
                if isinstance(node_output, dict) and node_output.get("last_output"):
                    self.messages.add(
                        conversation_id, "assistant", node_output["last_output"]
                    )
                    break
        
        self.conversations.touch(conversation_id)
    
    def get_history(self, conversation_id: str) -> list[dict]:
        """获取对话历史"""
        return self.messages.get_by_conversation(conversation_id)
    
    def list_conversations(self) -> list[dict]:
        """列出所有会话"""
        return self.conversations.list_all()
    
    # ============================================================
    # 消息编辑功能
    # ============================================================
    
    def get_recent_messages(self, conversation_id: str, n: int = 5) -> list[dict]:
        """获取最近 n 条消息（带 ID）"""
        return self.messages.get_recent(conversation_id, n)
    
    def edit_message(self, message_id: int, new_content: str):
        """编辑指定消息"""
        self.messages.update(message_id, new_content)
    
    def delete_message(self, message_id: int):
        """删除指定消息"""
        self.messages.delete(message_id)
    
    def rollback_to(self, conversation_id: str, message_id: int):
        """回滚到指定消息"""
        self.messages.delete_after(conversation_id, message_id)
    
    def regenerate(self, conversation_id: str) -> dict:
        """重新生成最后一条 AI 回复"""
        recent = self.messages.get_recent(conversation_id, 5)
        
        if not recent:
            raise ValueError("没有消息可以重新生成")
        
        last_ai_msg = None
        last_user_msg = None
        
        for msg in reversed(recent):
            if msg["role"] == "assistant" and last_ai_msg is None:
                last_ai_msg = msg
            elif msg["role"] == "user" and last_user_msg is None:
                last_user_msg = msg
        
        if not last_ai_msg:
            raise ValueError("没有 AI 消息可以重新生成")
        
        self.messages.delete(last_ai_msg["id"])
        
        if last_user_msg:
            conv = self.get_conversation(conversation_id)
            graph = self.load_graph(conv["graph_name"], conversation_id)
            
            history = self.messages.get_by_conversation(conversation_id)
            messages = [{"role": m["role"], "content": m["content"]} for m in history]
            
            initial_state = {
                "messages": messages,
                "user_input": last_user_msg["content"],
                "raw_input": last_user_msg["content"],
            }
            
            result = graph.invoke(
                initial_state,
                config={"configurable": {"thread_id": conv["thread_id"]}}
            )
            
            if result.get("last_output"):
                self.messages.add(conversation_id, "assistant", result["last_output"])
            
            return result
        
        return {}
