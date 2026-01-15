"""
角色扮演图：带情绪追踪和角色设定

状态会通过 checkpointer 自动持久化，包括：
- raw_messages: 对话历史（user + assistant）
- character: 角色设定（首次从资产库加载）
- mood: 情绪状态（跨轮次保持）
- memories: 相关记忆

消息处理架构:
    - raw_messages: 由 Runtime 追加用户输入，Node 追加 AI 回复
    - current_messages: 由 Node 构建，包含角色设定 + 历史对话
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from core.tools import ChatTools
from core.state import RoleplayState
from core.utils import build_current_messages, append_to_raw, to_api_messages


def build_graph(checkpointer: BaseCheckpointSaver = None):
    """
    构建角色扮演图
    
    Args:
        checkpointer: LangGraph checkpointer（状态持久化）
    """
    tools = ChatTools()
    
    # 角色内心思考
    def think(state):
        character = state.get("character", {})
        mood = state.get("mood", "平静")
        memories = state.get("memories", [])
        raw_messages = state.get("raw_messages", [])
        
        if not raw_messages:
            return {"inner_thought": ""}
        
        user_said = raw_messages[-1].get("content", "")
        memory_text = "\n".join([m.get("content", str(m)) for m in memories[:2]]) if memories else "无"
        
        prompt = f"""
你是 {character.get('name', '角色')}，性格：{character.get('personality', '友好')}
当前情绪：{mood}
相关记忆：{memory_text}
用户说：{user_said}

请用一句话描述角色此刻的内心想法（第一人称）：
"""
        thought = tools.call_llm(prompt)
        return {"inner_thought": thought}
    
    # 生成回复
    def respond(state):
        character = state.get("character", {})
        mood = state.get("mood", "平静")
        thought = state.get("inner_thought", "")
        raw_messages = state.get("raw_messages", [])
        
        # 1. 构建 current_messages：角色设定 + 历史对话
        system_prompt = f"""你是 {character.get('name', '角色')}
性格：{character.get('personality', '友好')}
场景：{character.get('scenario', '日常对话')}
当前情绪：{mood}
内心想法：{thought}

请以角色身份自然地回复，保持性格一致。"""
        
        current_messages = build_current_messages(
            raw_messages,
            system_prompt=system_prompt,
            max_history=10
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
    
    # 更新情绪
    def update_mood(state):
        raw_messages = state.get("raw_messages", [])
        current_mood = state.get("mood", "平静")
        
        if len(raw_messages) < 2:
            return {}
        
        recent = raw_messages[-2:]
        context = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
        
        prompt = f"""
之前情绪：{current_mood}
最近对话：
{context}

根据对话内容，角色现在的情绪是什么？（只输出一个情绪词，如：开心、难过、生气、平静、好奇等）
"""
        new_mood = tools.call_llm(prompt).strip()
        return {"mood": new_mood}
    
    # 构建图
    graph = StateGraph(RoleplayState)
    
    graph.add_node("think", think)
    graph.add_node("respond", respond)
    graph.add_node("mood", update_mood)
    
    graph.add_edge(START, "think")
    graph.add_edge("think", "respond")
    graph.add_edge("respond", "mood")
    graph.add_edge("mood", END)
    
    return graph.compile(checkpointer=checkpointer)


def get_initial_state():
    """
    默认初始状态
    
    注意：如果会话关联了角色卡，Runtime 会用资产库的数据覆盖这里的默认值
    """
    return {
        "memories": [],
        "mood": "平静",
        "character": {
            "name": "小雪",
            "personality": "温柔、善解人意、有点害羞",
            "scenario": "咖啡厅的下午",
        }
    }
