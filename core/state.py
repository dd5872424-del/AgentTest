"""
State 基类定义

所有图的 State 都应继承这些基类，确保接口一致性。

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
    - messages: 对话消息列表
    - user_input: 当前轮用户输入
    - raw_input: 原始输入（未处理）
    - last_output: 最后一条 AI 输出
    - message_id_counter: 消息 ID 计数器
    
    messages 消息格式:
        必须字段（LLM API 需要）:
        - role: "user" | "assistant" | "system"
        - content: 消息内容
        
        可选字段（内部元数据，不发送给 API）:
        - id: 消息唯一标识，用于编辑/回滚
        
        示例:
        {"role": "user", "content": "你好", "id": 1}
        {"role": "assistant", "content": "你好！", "id": 2}
    
    使用 to_api_messages() 转换为纯净的 API 格式
    轮次可通过 get_current_turn(state) 计算
    """
    messages: list
    user_input: str
    raw_input: str
    last_output: str
    message_id_counter: int
    
    # 额外消息列表，用于单轮注入（如 RAG 检索结果、System Prompt、Few-Shot 示例）
    # 这些消息会在 merge_messages() 时动态插入，但不会永久保存在 messages 历史中
    # 格式: [{"role": "...", "content": "...", "position": int | "start" | "end"}]
    extra_messages: list


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
