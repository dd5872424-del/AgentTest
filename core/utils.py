"""
消息处理工具函数

用于在节点内部处理消息格式、合并等操作。
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


def merge_messages(state: dict) -> list:
    """
    合并 messages 和 extra_messages，生成最终 LLM 输入
    
    extra_messages 中的消息可以通过 position 字段指定插入位置：
    - "start": 插入到开头
    - "end": 插入到末尾（默认）
    - 数字: 插入到指定索引位置（支持负数）
    
    Returns:
        合并后的 API 格式消息列表
    """
    messages = state.get("messages", [])
    extras = state.get("extra_messages", [])
    
    if not extras:
        return to_api_messages(messages)
    
    final_list = []
    
    # 1. 处理 position="start"
    start_extras = [m for m in extras if m.get("position") == "start"]
    final_list.extend(start_extras)
    
    # 2. 插入中间消息
    msg_len = len(messages)
    for i, msg in enumerate(messages):
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
    合并 messages + renderers 生成的额外消息
    
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
