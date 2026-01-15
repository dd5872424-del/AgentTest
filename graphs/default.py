"""
默认对话图：最简单的对话流程
用户输入 → 构建 current_messages → LLM 回复 → 写回 raw_messages

消息处理架构:
    - raw_messages: 由 Runtime 追加用户输入，Node 追加 AI 回复
    - current_messages: 由 Node 构建，包含 system prompt + 历史对话
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from core.tools import ChatTools
from core.state import ChatState
from core.utils import build_current_messages, append_to_raw


def build_graph(checkpointer: BaseCheckpointSaver = None):
    """
    构建默认对话图
    
    Args:
        checkpointer: LangGraph checkpointer（状态持久化）
    """
    tools = ChatTools()
    
    # 唯一节点：构建 current_messages + 调用 LLM + 写回 raw_messages
    def respond(state: dict) -> dict:
        raw_messages = state.get("raw_messages", [])
        
        # 1. 构建 current_messages：系统提示 + 最近对话
        current_messages = build_current_messages(
            raw_messages,
            system_prompt="你是一个友好的助手。",
            max_history=20
        )
        
        # 2. 调用 LLM
        response = tools.call_llm(current_messages)
        
        # 3. 追加 AI 回复到 raw_messages
        new_raw_messages = append_to_raw(raw_messages, "assistant", response)
        
        return {
            "raw_messages": new_raw_messages,
            "current_messages": current_messages,
            "last_output": response
        }
    
    # 构建图：只有一个节点
    graph = StateGraph(ChatState)
    graph.add_node("respond", respond)
    
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    
    return graph.compile(checkpointer=checkpointer)
