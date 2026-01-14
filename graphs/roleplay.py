"""
角色扮演图：带情绪追踪和角色设定
"""
from langgraph.graph import StateGraph, START, END

from core.tools import ChatTools
from core.state import RoleplayState
from core.storage import MemoryStore
from core.nodes import retrieve_memory, save_memory_if


def build_graph(conversation_id: str, memory_store: MemoryStore):
    """构建角色扮演图"""
    tools = ChatTools(conversation_id, memory_store=memory_store)
    
    # 角色内心思考
    def think(state):
        character = state.get("character", {})
        mood = state.get("mood", "平静")
        memories = state.get("memories", [])
        messages = state.get("messages", [])
        
        if not messages:
            return {"inner_thought": ""}
        
        user_said = messages[-1].get("content", "")
        memory_text = "\n".join([m["content"] for m in memories[:2]]) if memories else "无"
        
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
        messages = state.get("messages", [])
        
        prompt = [
            {
                "role": "system",
                "content": f"""你是 {character.get('name', '角色')}
性格：{character.get('personality', '友好')}
场景：{character.get('scenario', '日常对话')}
当前情绪：{mood}
内心想法：{thought}

请以角色身份自然地回复，保持性格一致。"""
            }
        ]
        prompt.extend(messages[-10:])
        
        response = tools.call_llm(prompt)
        new_messages = state.get("messages", []).copy()
        new_messages.append({"role": "assistant", "content": response})
        
        return {"messages": new_messages, "last_output": response}
    
    # 更新情绪
    def update_mood(state):
        messages = state.get("messages", [])
        current_mood = state.get("mood", "平静")
        
        if len(messages) < 2:
            return {}
        
        recent = messages[-2:]
        context = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
        
        prompt = f"""
之前情绪：{current_mood}
最近对话：
{context}

根据对话内容，角色现在的情绪是什么？（只输出一个情绪词，如：开心、难过、生气、平静、好奇等）
"""
        new_mood = tools.call_llm(prompt).strip()
        return {"mood": new_mood}
    
    # 条件：每5轮保存一次
    def should_save(state):
        return len(state.get("messages", [])) % 5 == 0
    
    # 构建图
    graph = StateGraph(RoleplayState)
    
    graph.add_node("retrieve", retrieve_memory(tools, top_k=3))
    graph.add_node("think", think)
    graph.add_node("respond", respond)
    graph.add_node("mood", update_mood)
    graph.add_node("save", save_memory_if(tools, should_save, type="roleplay"))
    
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "think")
    graph.add_edge("think", "respond")
    graph.add_edge("respond", "mood")
    graph.add_edge("mood", "save")
    graph.add_edge("save", END)
    
    return graph.compile()


def get_initial_state():
    """初始状态"""
    return {
        "memories": [],
        "mood": "平静",
        "character": {
            "name": "小雪",
            "personality": "温柔、善解人意、有点害羞",
            "scenario": "咖啡厅的下午",
        }
    }
