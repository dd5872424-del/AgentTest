"""
默认对话图：最简单的对话流程
用户输入 → 拼合历史 → LLM 回复
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from core.tools import ChatTools
from core.state import ChatState


def build_graph(checkpointer: BaseCheckpointSaver = None):
    """
    构建默认对话图
    
    Args:
        checkpointer: LangGraph checkpointer（状态持久化）
    """
    tools = ChatTools()
    
    # 唯一节点：拼合历史 + 调用 LLM
    def respond(state: dict) -> dict:
        messages = state.get("messages", [])
        
        # 构建 prompt：系统提示 + 最近对话
        prompt = [
            {"role": "system", "content": "你是一个友好的助手。"}
        ]
        
        # 拼合历史对话（最近20条）
        prompt.extend(messages[-20:])
        
        # 调用 LLM
        response = tools.call_llm(prompt)
        
        # 追加回复到消息列表
        new_messages = messages.copy()
        new_messages.append({"role": "assistant", "content": response})
        
        return {
            "messages": new_messages,
            "last_output": response
        }
    
    # 构建图：只有一个节点
    graph = StateGraph(ChatState)
    graph.add_node("respond", respond)
    
    graph.add_edge(START, "respond")
    graph.add_edge("respond", END)
    
    return graph.compile(checkpointer=checkpointer)
