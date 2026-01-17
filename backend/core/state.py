"""
State 基类定义

所有图的 State 都应继承这些基类，确保接口一致性。

消息管理架构:
    - raw_messages: 持久化的实际对话（user + assistant），用于前端显示、用户编辑
    - current_messages: 处理中的消息，由 Node 构建，用于 LLM 调用
    - extra_messages: 动态注入内容，由 Node 生成（RAG、System Prompt 等）

使用示例:
    from core.state import BaseState, ChatState
    
    # 方式1：直接使用预定义状态
    def build_graph(...):
        graph = StateGraph(ChatState)
        ...
    
    # 方式2：继承扩展
    class MyState(ChatState, total=False):
        custom_field: str
"""
from typing import TypedDict


class BaseState(TypedDict, total=False):
    """
    基础状态类，所有自定义 State 应继承此类
    
    核心字段:
    - raw_messages: 持久化的实际对话列表（仅 user + assistant）
    - current_messages: 处理中的消息列表（由 Node 构建，可包含 system 等）
    - extra_messages: 动态注入的消息列表（由 Node 生成）
    - user_input: 当前轮用户输入
    - raw_input: 原始输入（未处理）
    - last_output: 最后一条 AI 输出
    - message_id_counter: 消息 ID 计数器
    
    raw_messages 消息格式（前端显示用）:
        必须字段:
        - role: "user" | "assistant"
        - content: 消息内容
        
        可选字段（内部元数据）:
        - id: 消息唯一标识，用于编辑/回滚
        
        示例:
        {"role": "user", "content": "你好", "id": 1}
        {"role": "assistant", "content": "你好！", "id": 2}
    
    current_messages 消息格式（LLM 调用用）:
        - role: "user" | "assistant" | "system"
        - content: 消息内容
        
        由 Node 从 raw_messages + extra_messages 构建
        可包含 system prompt、历史裁剪、注入内容等
    
    extra_messages 消息格式（动态注入用）:
        - role: "system" | "user" | "assistant"
        - content: 消息内容
        - position: int | "start" | "end"（可选，合并位置）
        
        由 Node 生成（RAG 检索、System Prompt 构建等）
    
    职责划分:
        - Runtime: 把用户输入追加到 raw_messages，调用 graph
        - Node: 完全管理 extra_messages、current_messages，写回 AI 回复到 raw_messages
    """
    raw_messages: list
    current_messages: list
    extra_messages: list
    user_input: str
    raw_input: str
    last_output: str
    message_id_counter: int


class ChatState(BaseState, total=False):
    """
    标准聊天状态
    
    扩展字段:
    - memories: 会话记忆列表 [{"type": "...", "content": "..."}]
    - preset: 预设配置（从 content_refs 加载）
    - world_info: 世界观列表（从 content_refs 加载）
    """
    memories: list
    preset: dict
    world_info: list


class RoleplayState(ChatState, total=False):
    """
    角色扮演状态
    
    扩展字段:
    - character: 角色信息（从 content_refs 加载）
        {"name": "...", "personality": "...", "scenario": "...", "first_message": "..."}
    - mood: 角色当前情绪
    - inner_thought: 角色内心想法（调试用）
    """
    character: dict
    mood: str
    inner_thought: str


class CommandState(ChatState, total=False):
    """
    带指令解析的状态
    
    扩展字段:
    - commands: 解析出的指令列表 [{"cmd": "...", "arg": "..."}]
    - chat_content: 剔除指令后的对话内容
    - command_results: 指令执行结果列表
    """
    commands: list
    chat_content: str
    command_results: list
