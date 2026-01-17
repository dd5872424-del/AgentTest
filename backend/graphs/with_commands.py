"""
带指令解析的对话图：支持 /设定 /记住 等指令

记忆存储在 state.memories 中，由 checkpointer 自动持久化。

消息处理架构:
    - raw_messages: 由 Runtime 追加用户输入，Node 追加 AI 回复
    - current_messages: 由 Node 构建，包含系统设定 + 记忆 + 历史对话
    - chat_content: 剔除指令后的用户输入，用于 LLM 调用
"""
import re
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from core.tools import ChatTools
from core.state import CommandState, RoleplayState
from core.nodes import parse_commands
from core.utils import build_current_messages, append_to_raw, to_api_messages


class State(CommandState, RoleplayState, total=False):
    """
    带指令的对话状态
    
    组合了 CommandState（指令解析）和 RoleplayState（角色扮演）的能力
    """
    pass


def build_graph(checkpointer: BaseCheckpointSaver = None):
    """构建带指令的对话图"""
    tools = ChatTools()
    
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
                # 将记忆添加到 state.memories
                memories = state.get("memories", []).copy()
                memories.append({"type": "user_note", "content": arg})
                updates["memories"] = memories
                results.append(f"✓ 已记住：{arg}")
            
            elif command == "忘记":
                # 从 state.memories 中删除包含关键词的记忆
                memories = state.get("memories", [])
                filtered = [m for m in memories if arg not in m.get("content", "")]
                updates["memories"] = filtered
                results.append(f"✓ 已尝试忘记关于「{arg}」的记忆")
            
            elif command == "清空记忆":
                updates["memories"] = []
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
        raw_messages = state.get("raw_messages", [])
        
        # 1. 构建系统提示
        system_parts = ["你是一个友好的助手。"]
        if character.get("name"):
            system_parts[0] = f"你是 {character['name']}。"
        if mood:
            system_parts.append(f"当前情绪：{mood}")
        if scene:
            system_parts.append(f"场景：{scene}")
        
        system_prompt = " ".join(system_parts)
        
        # 2. 构建额外系统消息（记忆）
        extra_system = []
        if memories:
            memory_text = "\n".join([m.get("content", str(m)) for m in memories[:3]])
            extra_system.append({"role": "system", "content": f"相关记忆：\n{memory_text}"})
        
        # 3. 构建 current_messages
        # 使用 raw_messages 历史（不含最后一条用户消息，因为那可能包含指令）
        history = raw_messages[:-1] if raw_messages else []
        current_messages = build_current_messages(
            history,
            system_prompt=system_prompt,
            max_history=8,
            extra_system=extra_system
        )
        # 追加剔除指令后的用户输入
        current_messages.append({"role": "user", "content": chat_content})
        
        # 4. 调用 LLM
        response = tools.call_llm(current_messages)
        
        # 5. 追加 AI 回复到 raw_messages
        new_raw_messages = append_to_raw(raw_messages, "assistant", response)
        
        return {
            "raw_messages": new_raw_messages,
            "current_messages": current_messages,
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
    graph.add_node("chat", process_chat)
    graph.add_node("merge", merge_output)
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
        {True: "chat", False: "merge"}
    )
    
    graph.add_conditional_edges(
        "noop_cmd",
        has_chat,
        {True: "chat", False: "merge"}
    )
    
    graph.add_edge("chat", "merge")
    graph.add_edge("merge", END)
    
    return graph.compile(checkpointer=checkpointer)


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
