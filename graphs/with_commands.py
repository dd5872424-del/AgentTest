"""
带指令解析的对话图：支持 /设定 /记住 等指令
"""
import re
from langgraph.graph import StateGraph, START, END

from core.tools import ChatTools
from core.state import CommandState, RoleplayState
from core.storage import MemoryStore
from core.nodes import retrieve_memory, save_memory, parse_commands


class State(CommandState, RoleplayState, total=False):
    """
    带指令的对话状态
    
    组合了 CommandState（指令解析）和 RoleplayState（角色扮演）的能力
    """
    pass


def build_graph(conversation_id: str, memory_store: MemoryStore):
    """构建带指令的对话图"""
    tools = ChatTools(conversation_id, memory_store=memory_store)
    
    # 执行指令（纯逻辑，非 LLM）
    def execute_commands(state):
        commands = state.get("commands", [])
        results = []
        updates = {}
        
        for cmd in commands:
            command = cmd.get("cmd", "")
            arg = cmd.get("arg", "")
            
            if command == "设定":
                match = re.match(r'(\w+)[：:](.+)', arg)
                if match:
                    key, value = match.groups()
                    key = key.strip()
                    value = value.strip()
                    
                    if key in ["心情", "情绪", "mood"]:
                        updates["mood"] = value
                        results.append(f"✓ 心情已设为：{value}")
                    elif key in ["场景", "scene"]:
                        updates["scene"] = value
                        results.append(f"✓ 场景已设为：{value}")
                    elif key in ["名字", "name"]:
                        char = state.get("character", {}).copy()
                        char["name"] = value
                        updates["character"] = char
                        results.append(f"✓ 角色名已设为：{value}")
                    else:
                        results.append(f"✗ 未知设定项：{key}")
                else:
                    results.append(f"✗ 格式错误，应为：/设定 字段：值")
            
            elif command == "记住":
                tools.save_memory(arg, type="user_note")
                results.append(f"✓ 已记住：{arg}")
            
            elif command == "忘记":
                tools.memory.delete(arg)
                results.append(f"✓ 已尝试忘记关于「{arg}」的记忆")
            
            elif command == "清空记忆":
                tools.memory.clear()
                results.append("✓ 已清空所有记忆")
            
            else:
                results.append(f"✗ 未知指令：/{command}")
        
        return {"command_results": results, **updates}
    
    # 处理对话
    def process_chat(state):
        chat_content = state.get("chat_content", "")
        if not chat_content:
            return {"last_output": ""}
        
        memories = state.get("memories", [])
        mood = state.get("mood", "平静")
        scene = state.get("scene", "")
        character = state.get("character", {})
        
        prompt = []
        
        system_parts = ["你是一个友好的助手。"]
        if character.get("name"):
            system_parts[0] = f"你是 {character['name']}。"
        if mood:
            system_parts.append(f"当前情绪：{mood}")
        if scene:
            system_parts.append(f"场景：{scene}")
        
        prompt.append({"role": "system", "content": " ".join(system_parts)})
        
        if memories:
            memory_text = "\n".join([m["content"] for m in memories[:3]])
            prompt.append({"role": "system", "content": f"相关记忆：\n{memory_text}"})
        
        messages = state.get("messages", [])
        prompt.extend(messages[-8:])
        prompt.append({"role": "user", "content": chat_content})
        
        response = tools.call_llm(prompt)
        
        new_messages = messages.copy()
        new_messages.append({"role": "user", "content": chat_content})
        new_messages.append({"role": "assistant", "content": response})
        
        return {
            "messages": new_messages,
            "last_output": response
        }
    
    # 合并输出
    def merge_output(state):
        parts = []
        
        command_results = state.get("command_results", [])
        if command_results:
            parts.append("【系统】\n" + "\n".join(command_results))
        
        chat_response = state.get("last_output", "")
        if chat_response:
            parts.append(chat_response)
        
        final = "\n\n".join(parts) if parts else "（无操作）"
        return {"last_output": final}
    
    # 条件判断
    def has_commands(state):
        return len(state.get("commands", [])) > 0
    
    def has_chat(state):
        return bool(state.get("chat_content", "").strip())
    
    def noop(state):
        return {}
    
    # 构建图
    graph = StateGraph(State)
    
    graph.add_node("parse", parse_commands())
    graph.add_node("exec_cmd", execute_commands)
    graph.add_node("retrieve", retrieve_memory(tools, top_k=3))
    graph.add_node("chat", process_chat)
    graph.add_node("merge", merge_output)
    graph.add_node("save", save_memory(tools, type="chat"))
    graph.add_node("noop_cmd", noop)
    graph.add_node("noop_chat", lambda s: {"last_output": ""})
    
    graph.add_edge(START, "parse")
    
    graph.add_conditional_edges(
        "parse",
        has_commands,
        {True: "exec_cmd", False: "noop_cmd"}
    )
    
    graph.add_conditional_edges(
        "exec_cmd",
        has_chat,
        {True: "retrieve", False: "merge"}
    )
    
    graph.add_conditional_edges(
        "noop_cmd",
        has_chat,
        {True: "retrieve", False: "merge"}
    )
    
    graph.add_edge("retrieve", "chat")
    graph.add_edge("chat", "merge")
    graph.add_edge("merge", "save")
    graph.add_edge("save", END)
    
    return graph.compile()


def get_initial_state():
    """初始状态"""
    return {
        "memories": [],
        "commands": [],
        "command_results": [],
        "mood": "平静",
        "scene": "",
        "character": {},
    }
