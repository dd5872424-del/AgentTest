"""
消息处理工具函数

用于在节点内部处理消息格式、合并等操作。

消息管理架构:
    - raw_messages: 持久化的实际对话（user + assistant）
    - current_messages: 处理中的消息，由 Node 构建
    - extra_messages: 动态注入内容，由 Node 生成
"""
from typing import Callable, Iterable


def to_api_messages(messages: list) -> list:
    """
    将内部消息格式转换为 LLM API 格式
    只保留 role 和 content，过滤掉 id、turn 等元数据
    
    示例:
        >>> msgs = [{"role": "user", "content": "你好", "id": 1}]
        >>> to_api_messages(msgs)
        [{"role": "user", "content": "你好"}]
    """
    return [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if "role" in m and "content" in m
    ]


# ============================================================
# 新架构工具函数
# ============================================================

def build_current_messages(
    raw_messages: list,
    system_prompt: str = None,
    max_history: int = None,
    extra_system: list[dict] = None
) -> list:
    """
    从 raw_messages 构建 current_messages
    
    Args:
        raw_messages: 原始对话消息列表（user + assistant）
        system_prompt: 可选的系统提示词，会插入到开头
        max_history: 可选的历史消息数量限制
        extra_system: 可选的额外系统消息列表（如角色设定、场景描述）
    
    Returns:
        构建好的 current_messages 列表
    
    示例:
        # 基础用法
        current = build_current_messages(
            state["raw_messages"],
            system_prompt="你是一个友好的助手。"
        )
        
        # 带历史限制
        current = build_current_messages(
            state["raw_messages"],
            system_prompt="你是一个友好的助手。",
            max_history=20
        )
        
        # 带额外系统消息
        current = build_current_messages(
            state["raw_messages"],
            extra_system=[
                {"role": "system", "content": f"角色：{character['name']}"},
                {"role": "system", "content": f"当前情绪：{mood}"}
            ]
        )
    """
    current = []
    
    # 1. 添加系统提示词
    if system_prompt:
        current.append({"role": "system", "content": system_prompt})
    
    # 2. 添加额外系统消息
    if extra_system:
        for msg in extra_system:
            if isinstance(msg, dict) and "content" in msg:
                current.append({
                    "role": msg.get("role", "system"),
                    "content": msg["content"]
                })
    
    # 3. 添加历史消息（可选裁剪）
    history = raw_messages or []
    if max_history is not None and len(history) > max_history:
        history = history[-max_history:]
    
    current.extend(to_api_messages(history))
    
    return current


def merge_extra_messages(current_messages: list, extra_messages: list) -> list:
    """
    将 extra_messages 按 position 合并到 current_messages
    
    Args:
        current_messages: 当前消息列表
        extra_messages: 要合并的消息列表，每条消息可包含 position 字段
    
    position 字段支持:
        - "start": 插入到开头
        - "end": 插入到末尾（默认）
        - int: 插入到指定索引位置（支持负数）
    
    Returns:
        合并后的消息列表
    
    示例:
        extra = [
            {"role": "system", "content": "RAG 结果...", "position": 1},
            {"role": "system", "content": "Few-shot 示例...", "position": "end"}
        ]
        merged = merge_extra_messages(current, extra)
    """
    if not extra_messages:
        return current_messages.copy()
    
    result = []
    msg_len = len(current_messages)
    
    # 1. 处理 position="start"
    start_extras = [m for m in extra_messages if m.get("position") == "start"]
    for m in start_extras:
        result.append({"role": m.get("role", "system"), "content": m["content"]})
    
    # 2. 插入中间消息
    for i, msg in enumerate(current_messages):
        # 找到要插入到当前位置的 extra 消息
        current_extras = [
            m for m in extra_messages 
            if m.get("position") == i or 
               (isinstance(m.get("position"), int) and m.get("position") < 0 and m.get("position") == i - msg_len)
        ]
        for m in current_extras:
            result.append({"role": m.get("role", "system"), "content": m["content"]})
        result.append(msg)
    
    # 3. 处理 position="end" 或无 position
    end_extras = [
        m for m in extra_messages 
        if m.get("position") == "end" or m.get("position") is None
    ]
    for m in end_extras:
        result.append({"role": m.get("role", "system"), "content": m["content"]})
    
    return result


def append_to_raw(raw_messages: list, role: str, content: str, **metadata) -> list:
    """
    追加消息到 raw_messages（返回新列表，不修改原列表）
    
    Args:
        raw_messages: 原始消息列表
        role: 消息角色 ("user" | "assistant")
        content: 消息内容
        **metadata: 可选的元数据（如 id）
    
    Returns:
        新的消息列表
    
    示例:
        # 追加 AI 回复
        new_raw = append_to_raw(state["raw_messages"], "assistant", response)
        return {"raw_messages": new_raw, "last_output": response}
    """
    new_list = (raw_messages or []).copy()
    message = {"role": role, "content": content}
    if metadata:
        message.update(metadata)
    new_list.append(message)
    return new_list


# ============================================================
# 旧版兼容函数（使用 raw_messages）
# ============================================================

def merge_messages(state: dict) -> list:
    """
    合并 raw_messages 和 extra_messages，生成最终 LLM 输入
    
    注意：此函数为旧版兼容，建议使用 build_current_messages + merge_extra_messages
    
    extra_messages 中的消息可以通过 position 字段指定插入位置：
    - "start": 插入到开头
    - "end": 插入到末尾（默认）
    - 数字: 插入到指定索引位置（支持负数）
    
    Returns:
        合并后的 API 格式消息列表
    """
    raw_messages = state.get("raw_messages", [])
    extras = state.get("extra_messages", [])
    
    if not extras:
        return to_api_messages(raw_messages)
    
    final_list = []
    
    # 1. 处理 position="start"
    start_extras = [m for m in extras if m.get("position") == "start"]
    final_list.extend(start_extras)
    
    # 2. 插入中间消息
    msg_len = len(raw_messages)
    for i, msg in enumerate(raw_messages):
        current_extras = [
            m for m in extras 
            if m.get("position") == i or (isinstance(m.get("position"), int) and m.get("position") == i - msg_len)
        ]
        final_list.extend(current_extras)
        final_list.append(msg)
        
    # 3. 处理 position="end"
    end_extras = [m for m in extras if m.get("position") == "end"]
    final_list.extend(end_extras)
    
    return to_api_messages(final_list)


def merge_messages_with(state: dict, renderers: Iterable[Callable[[dict], list[dict]]]) -> list:
    """
    合并 raw_messages + renderers 生成的额外消息
    
    注意：此函数为旧版兼容，建议使用新架构的工具函数
    
    renderers 用于把结构化字段渲染成可插入消息：
        renderer(state) -> [{"role": "...", "content": "...", "position": "start"|"end"|int}, ...]
    
    Returns:
        合并后的 API 格式消息列表
    """
    base_extras = state.get("extra_messages") or []
    extras: list[dict] = list(base_extras)
    
    for renderer in renderers:
        produced = renderer(state) or []
        extras.extend(produced)
    
    # 归一化：没有 position 的默认为 "end"
    normalized = []
    for m in extras:
        if not isinstance(m, dict):
            continue
        if "role" not in m or "content" not in m:
            continue
        if "position" not in m:
            m = {**m, "position": "end"}
        normalized.append(m)
    
    merged_state = dict(state)
    merged_state["extra_messages"] = normalized
    return merge_messages(merged_state)
