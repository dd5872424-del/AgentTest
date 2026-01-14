"""
预置节点库：常用节点的闭包封装
"""
import re
from typing import Callable, Iterable


# ============================================================
# 消息工具函数
# ============================================================

def to_api_messages(messages: list) -> list:
    """
    将内部消息格式转换为 LLM API 格式
    只保留 role 和 content，过滤掉 id、turn 等元数据
    
    Args:
        messages: 内部消息列表
        
    Returns:
        纯净的 API 格式消息列表
        
    示例:
        >>> msgs = [{"role": "user", "content": "你好", "id": 1, "turn": 1}]
        >>> to_api_messages(msgs)
        [{"role": "user", "content": "你好"}]
    """
    return [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if "role" in m and "content" in m
    ]


def create_message(role: str, content: str, state: dict) -> dict:
    """
    创建带元数据的消息
    
    Args:
        role: 消息角色
        content: 消息内容
        state: 当前状态（用于获取 id 计数器）
        
    Returns:
        带元数据的消息字典
    """
    msg_id = state.get("message_id_counter", 0) + 1
    
    return {
        "role": role,
        "content": content,
        "id": msg_id,
    }


def get_current_turn(state: dict) -> int:
    """
    从消息列表计算当前轮次
    
    轮次 = 用户消息数量
    
    Args:
        state: 当前状态
        
    Returns:
        当前轮次
    """
    messages = state.get("messages", [])
    return sum(1 for m in messages if m.get("role") == "user")


def next_message_state(state: dict, new_message: dict) -> dict:
    """
    返回添加新消息后的状态更新
    
    Args:
        state: 当前状态
        new_message: 新消息（由 create_message 创建）
        
    Returns:
        状态更新字典
    """
    messages = state.get("messages", []).copy()
    messages.append(new_message)
    
    return {
        "messages": messages,
        "message_id_counter": new_message.get("id", len(messages)),
    }


def merge_messages(state: dict) -> list:
    """
    合并 messages 和 extra_messages，生成最终 LLM 输入
    
    Args:
        state: 包含 messages 和 extra_messages 的状态
        
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
        # 检查是否有插入到当前 index 的 extra 消息
        # 支持负数 index (e.g. -1 表示倒数第一条之前)
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
    合并 messages + (state.extra_messages + renderers(state) 生成的额外消息)，生成最终 LLM 输入。
    
    renderers（也可叫“字段渲染器/转换器”）用于把结构化字段渲染成可插入消息：
        renderer(state) -> [{"role": "...", "content": "...", "position": int | "start" | "end"}, ...]
    
    Args:
        state: 当前状态
        renderers: 一组 renderer 函数
    
    Returns:
        合并后的 API 格式消息列表（仅含 role/content）
    """
    base_extras = (state.get("extra_messages") or [])
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


# ============================================================
# 记忆相关节点
# ============================================================

def retrieve_memory(tools, top_k: int = 5):
    """
    检索记忆节点
    
    Args:
        tools: ChatTools 实例
        top_k: 返回的记忆条数
    
    Returns:
        node 函数
    """
    def node(state: dict) -> dict:
        messages = state.get("messages", [])
        if not messages:
            return {"memories": []}
        
        query = messages[-1].get("content", "")
        memories = tools.search_memory(query, top_k)
        return {"memories": memories}
    
    return node


def _format_exchange(messages: list, n: int = 2) -> str:
    """格式化最后 n 条消息为文本"""
    if len(messages) < n:
        return ""
    return "\n".join([f"{m['role']}: {m['content']}" for m in messages[-n:]])


def save_memory(tools, type: str = "default", condition: Callable[[dict], bool] = None):
    """
    保存记忆节点
    
    Args:
        tools: ChatTools 实例
        type: 记忆类型
        condition: 可选条件函数，返回 True 时才保存
    
    示例:
        # 每次都保存
        save_memory(tools)
        
        # 条件保存
        save_memory(tools, condition=lambda s: len(s["messages"]) % 5 == 0)
    """
    def node(state: dict) -> dict:
        # 检查条件
        if condition is not None and not condition(state):
            return {}
        
        content = _format_exchange(state.get("messages", []))
        if content:
            tools.save_memory(content, type=type)
        return {}
    
    return node


# 保持向后兼容的别名
def save_memory_if(tools, condition: Callable[[dict], bool], type: str = "default"):
    """向后兼容：推荐使用 save_memory(tools, condition=...)"""
    return save_memory(tools, type=type, condition=condition)


def clear_memory(tools):
    """清空记忆节点"""
    def node(state: dict) -> dict:
        tools.memory.clear()
        return {}
    return node


# ============================================================
# LLM 相关节点
# ============================================================

def llm_call(tools, prompt_builder: Callable[[dict], str | list]):
    """
    LLM 调用节点
    
    Args:
        tools: ChatTools 实例
        prompt_builder: 构建 prompt 的函数，接收 state 返回 str 或 messages list
    """
    def node(state: dict) -> dict:
        prompt = prompt_builder(state)
        response = tools.call_llm(prompt)
        
        # 追加到消息列表
        messages = state.get("messages", []).copy()
        messages.append({"role": "assistant", "content": response})
        
        return {
            "messages": messages,
            "last_output": response
        }
    
    return node


def llm_analyze(tools, question_template: str, output_field: str = "analysis"):
    """
    LLM 分析节点（不追加到消息列表）
    
    Args:
        tools: ChatTools 实例
        question_template: 问题模板，可用 {field} 引用 state 字段
        output_field: 输出字段名
    """
    def node(state: dict) -> dict:
        # 简单模板替换
        question = question_template
        for key, value in state.items():
            question = question.replace(f"{{{key}}}", str(value))
        
        response = tools.call_llm(question)
        return {output_field: response}
    
    return node


def llm_extract(tools, instruction: str, output_field: str = "extracted"):
    """
    LLM 提取信息节点
    
    Args:
        tools: ChatTools 实例
        instruction: 提取指令
        output_field: 输出字段名
    """
    def node(state: dict) -> dict:
        messages = state.get("messages", [])
        if not messages:
            return {output_field: ""}
        
        recent = messages[-4:] if len(messages) >= 4 else messages
        context = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
        
        prompt = f"{instruction}\n\n对话内容：\n{context}"
        response = tools.call_llm(prompt)
        return {output_field: response}
    
    return node


# ============================================================
# 输入处理节点
# ============================================================

def parse_commands(pattern: str = r'/(\w+)\s+([^|/]+)'):
    """
    解析指令节点
    
    Args:
        pattern: 指令匹配正则
    """
    def node(state: dict) -> dict:
        raw_input = state.get("raw_input", "")
        if not raw_input:
            messages = state.get("messages", [])
            if messages:
                raw_input = messages[-1].get("content", "")
        
        # 匹配指令
        commands = re.findall(pattern, raw_input)
        command_list = [{"cmd": c[0], "arg": c[1].strip()} for c in commands]
        
        # 剩余对话内容
        chat_content = re.sub(pattern + r'\|?', '', raw_input).strip()
        
        return {
            "commands": command_list,
            "chat_content": chat_content
        }
    
    return node


def split_input(delimiter: str = "|"):
    """
    分割输入节点
    
    Args:
        delimiter: 分隔符
    """
    def node(state: dict) -> dict:
        raw_input = state.get("raw_input", "")
        if not raw_input:
            messages = state.get("messages", [])
            if messages:
                raw_input = messages[-1].get("content", "")
        
        parts = [p.strip() for p in raw_input.split(delimiter)]
        return {"input_parts": parts}
    
    return node


def add_user_message():
    """添加用户消息到列表"""
    def node(state: dict) -> dict:
        user_input = state.get("user_input", "")
        messages = state.get("messages", []).copy()
        messages.append({"role": "user", "content": user_input})
        return {"messages": messages, "last_input": user_input}
    
    return node


# ============================================================
# 状态更新节点
# ============================================================

def update_field(field: str, value_fn: Callable[[dict], any]):
    """
    更新字段节点
    
    Args:
        field: 字段名
        value_fn: 计算新值的函数
    """
    def node(state: dict) -> dict:
        new_value = value_fn(state)
        return {field: new_value}
    
    return node


def set_fields(**fields):
    """
    设置多个字段
    
    Args:
        **fields: 字段名=值
    """
    def node(state: dict) -> dict:
        return fields
    
    return node


def merge_fields(output_field: str, fields: list[str], separator: str = "\n\n"):
    """
    合并多个字段
    
    Args:
        output_field: 输出字段名
        fields: 要合并的字段列表
        separator: 分隔符
    """
    def node(state: dict) -> dict:
        parts = []
        for f in fields:
            value = state.get(f)
            if value:
                parts.append(str(value))
        
        return {output_field: separator.join(parts)}
    
    return node


# ============================================================
# 条件判断函数（用于 conditional_edges）
# ============================================================

def has_field(field: str):
    """检查字段是否有值"""
    def check(state: dict) -> bool:
        value = state.get(field)
        if isinstance(value, list):
            return len(value) > 0
        return bool(value)
    return check


def field_equals(field: str, expected):
    """检查字段是否等于某值"""
    def check(state: dict) -> bool:
        return state.get(field) == expected
    return check


def message_count_gt(n: int):
    """消息数量是否大于 n"""
    def check(state: dict) -> bool:
        return len(state.get("messages", [])) > n
    return check


def message_count_mod(n: int, remainder: int = 0):
    """消息数量模 n 是否等于 remainder"""
    def check(state: dict) -> bool:
        return len(state.get("messages", [])) % n == remainder
    return check


def contains_keyword(field: str, keywords: list[str]):
    """字段是否包含关键词"""
    def check(state: dict) -> bool:
        value = str(state.get(field, ""))
        return any(kw in value for kw in keywords)
    return check


# ============================================================
# 工具节点
# ============================================================

def log_state(prefix: str = "STATE"):
    """调试：打印状态"""
    def node(state: dict) -> dict:
        print(f"[{prefix}] {state}")
        return {}
    return node


def noop():
    """空操作节点"""
    def node(state: dict) -> dict:
        return {}
    return node
