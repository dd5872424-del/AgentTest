"""
节点工厂

用于 graph.add_node() 的预置节点。
所有函数都返回一个 (state) -> dict 的节点函数。
"""
import re
from functools import lru_cache
from typing import Callable, Optional

from .storage import ContentStore


# ============================================================
# 正则工具函数
# ============================================================

@lru_cache(maxsize=256)
def get_regex(pattern: str, flags: str = "") -> re.Pattern:
    """
    获取编译后的正则（带 LRU 缓存）
    
    避免重复编译正则表达式，提升性能。
    
    Args:
        pattern: 正则表达式字符串
        flags: 标志字符串，如 "gi"
            - g: 全局匹配（Python re.sub 默认全局，此标志仅作标记）
            - i: 忽略大小写
            - m: 多行模式
            - s: dotall 模式（. 匹配换行符）
    
    Returns:
        编译后的 re.Pattern 对象
    
    示例:
        regex = get_regex(r"\\*+([^*]+)\\*+", "gi")
        result = regex.sub(r"\\1", text)
    """
    flag_map = {
        'i': re.IGNORECASE,
        'm': re.MULTILINE,
        's': re.DOTALL,
    }
    re_flags = 0
    for f in flags.lower():
        if f in flag_map:
            re_flags |= flag_map[f]
    
    return re.compile(pattern, re_flags)


def _load_and_sort_scripts(
    contents: ContentStore,
    script_ids: list[str] = None,
    tags: list[str] = None,
) -> list[dict]:
    """
    加载并排序正则脚本
    
    Args:
        contents: ContentStore 实例
        script_ids: 指定脚本 ID 列表，None 则加载所有
        tags: 按标签筛选
    
    Returns:
        按 priority 排序的脚本列表
    """
    if script_ids:
        # 按指定 ID 加载
        scripts = [contents.get("regex", sid) for sid in script_ids]
        scripts = [s for s in scripts if s and s["data"].get("enabled", True)]
    else:
        # 按 tags 加载所有启用脚本
        all_scripts = contents.list("regex", tags=tags)
        scripts = [s for s in all_scripts if s["data"].get("enabled", True)]
    
    # 按 priority 排序（数字越小越先执行）
    scripts.sort(key=lambda x: x["data"].get("priority", 0))
    return scripts


def _apply_regex(text: str, script_data: dict) -> str:
    """
    对文本应用单个正则脚本
    
    Args:
        text: 输入文本
        script_data: 脚本的 data 字典
    
    Returns:
        替换后的文本
    """
    pattern = script_data.get("find_regex", "")
    if not pattern:
        return text
    
    replacement = script_data.get("replace_string", "")
    flags = script_data.get("flags", "g")
    
    try:
        regex = get_regex(pattern, flags)
        return regex.sub(replacement, text)
    except re.error:
        # 正则语法错误，返回原文本
        return text


# ============================================================
# 输入处理节点
# ============================================================

def parse_commands(pattern: str = r'/(\w+)\s+([^|/]+)'):
    """
    解析指令节点
    
    从 raw_input 或最后一条消息中解析 /cmd arg 格式的指令
    
    Args:
        pattern: 指令匹配正则，默认匹配 /指令 参数
    
    Returns:
        node 函数，输出 commands 和 chat_content
    
    示例:
        graph.add_node("parse", parse_commands())
        
        # 输入: "/设定 心情：开心 你好啊"
        # 输出: {
        #     "commands": [{"cmd": "设定", "arg": "心情：开心"}],
        #     "chat_content": "你好啊"
        # }
    """
    def node(state: dict) -> dict:
        raw_input = state.get("raw_input", "")
        if not raw_input:
            messages = state.get("messages", [])
            if messages:
                raw_input = messages[-1].get("content", "")
        
        commands = re.findall(pattern, raw_input)
        command_list = [{"cmd": c[0], "arg": c[1].strip()} for c in commands]
        chat_content = re.sub(pattern + r'\|?', '', raw_input).strip()
        
        return {
            "commands": command_list,
            "chat_content": chat_content
        }
    
    return node


# ============================================================
# 工具节点
# ============================================================

def log_state(prefix: str = "STATE", fields: list[str] = None):
    """
    调试：打印状态
    
    Args:
        prefix: 日志前缀
        fields: 只打印指定字段，None 表示全部
    
    示例:
        graph.add_node("debug", log_state("BEFORE_LLM", ["messages", "mood"]))
    """
    def node(state: dict) -> dict:
        if fields:
            filtered = {k: state.get(k) for k in fields}
            print(f"[{prefix}] {filtered}")
        else:
            print(f"[{prefix}] {state}")
        return {}
    return node


def noop():
    """
    空操作节点
    
    用于条件分支中的占位
    
    示例:
        graph.add_node("skip", noop())
    """
    def node(state: dict) -> dict:
        return {}
    return node


def set_field(field: str, value):
    """
    设置字段为固定值
    
    Args:
        field: 字段名
        value: 固定值
    
    示例:
        graph.add_node("init_mood", set_field("mood", "平静"))
    """
    def node(state: dict) -> dict:
        return {field: value}
    return node


def copy_field(source: str, target: str):
    """
    复制字段
    
    Args:
        source: 源字段名
        target: 目标字段名
    
    示例:
        graph.add_node("backup", copy_field("messages", "messages_backup"))
    """
    def node(state: dict) -> dict:
        value = state.get(source)
        if value is not None:
            # 深拷贝列表和字典
            if isinstance(value, list):
                value = value.copy()
            elif isinstance(value, dict):
                value = value.copy()
        return {target: value}
    return node


# ============================================================
# 正则替换节点
# ============================================================

def regex_replace(
    input_field: str = "raw_input",
    output_field: str = None,
    script_ids: list[str] = None,
    tags: list[str] = None,
    contents: ContentStore = None,
) -> Callable:
    """
    正则替换节点 - 处理单个 state 字段
    
    从 ContentStore 加载正则脚本，对指定字段进行正则替换。
    脚本在 node 创建时加载（缓存），运行时不再查库。
    
    Args:
        input_field: 读取的 state 字段，默认 "raw_input"
        output_field: 输出字段，None 则覆盖 input_field
        script_ids: 指定脚本 ID 列表，None 则使用所有启用脚本
        tags: 按标签筛选脚本
        contents: ContentStore 实例，必须提供
    
    Returns:
        node 函数
    
    示例:
        from core.storage import SQLiteContentStore
        
        contents = SQLiteContentStore("data/content.db")
        
        # 添加正则脚本
        contents.save("regex", "remove_asterisks", {
            "name": "移除星号",
            "find_regex": r"\\*+([^*]+)\\*+",
            "replace_string": r"\\1",
            "flags": "gi",
            "enabled": True,
            "priority": 0,
        }, tags=["input"])
        
        # 在图中使用
        graph.add_node("clean", regex_replace(
            input_field="raw_input",
            output_field="clean_input",
            tags=["input"],
            contents=contents,
        ))
    """
    if contents is None:
        raise ValueError("contents 参数是必须的，请传入 ContentStore 实例")
    
    # 创建 node 时加载脚本（只查一次库）
    scripts = _load_and_sort_scripts(contents, script_ids, tags)
    out_field = output_field or input_field
    
    def node(state: dict) -> dict:
        text = state.get(input_field, "")
        if not isinstance(text, str):
            return {out_field: text}
        
        # 依次应用所有脚本
        for script in scripts:
            text = _apply_regex(text, script["data"])
        
        return {out_field: text}
    
    return node


def regex_replace_messages(
    messages_field: str = "messages",
    output_field: str = None,
    script_ids: list[str] = None,
    tags: list[str] = None,
    contents: ContentStore = None,
) -> Callable:
    """
    正则替换节点 - 处理 messages 列表，自动应用 depth 条件
    
    遍历 messages 列表，根据每个脚本的 min_depth/max_depth 条件
    决定是否对该消息应用正则替换。
    
    Depth 说明：
        - depth=0 表示最新一条消息
        - depth=1 表示倒数第二条
        - 以此类推...
    
    Args:
        messages_field: messages 列表的 state 字段名，默认 "messages"
        output_field: 输出字段，None 则覆盖 messages_field
        script_ids: 指定脚本 ID 列表，None 则使用所有启用脚本
        tags: 按标签筛选脚本
        contents: ContentStore 实例，必须提供
    
    Returns:
        node 函数
    
    示例:
        contents.save("regex", "recent_format", {
            "name": "最近消息格式化",
            "find_regex": r"\\*\\*(.+?)\\*\\*",
            "replace_string": r"【\\1】",
            "flags": "g",
            "enabled": True,
            "priority": 0,
            "min_depth": 0,    # 从最新消息开始
            "max_depth": 4,    # 只处理最近 5 条
        }, tags=["output"])
        
        graph.add_node("format", regex_replace_messages(
            messages_field="raw_messages",
            output_field="formatted_messages",
            tags=["output"],
            contents=contents,
        ))
    """
    if contents is None:
        raise ValueError("contents 参数是必须的，请传入 ContentStore 实例")
    
    # 创建 node 时加载脚本（只查一次库）
    scripts = _load_and_sort_scripts(contents, script_ids, tags)
    out_field = output_field or messages_field
    
    def node(state: dict) -> dict:
        messages = state.get(messages_field, [])
        if not isinstance(messages, list):
            return {out_field: messages}
        
        result = []
        total = len(messages)
        
        for i, msg in enumerate(messages):
            # 计算 depth（0 = 最新消息）
            depth = total - 1 - i
            
            # 获取消息内容
            content = msg.get("content", "") if isinstance(msg, dict) else ""
            
            # 依次应用符合 depth 条件的脚本
            for script in scripts:
                data = script["data"]
                min_d = data.get("min_depth")
                max_d = data.get("max_depth")
                
                # 检查 depth 条件
                if min_d is not None and depth < min_d:
                    continue
                if max_d is not None and depth > max_d:
                    continue
                
                content = _apply_regex(content, data)
            
            # 保留原消息的其他字段，只更新 content
            if isinstance(msg, dict):
                result.append({**msg, "content": content})
            else:
                result.append(msg)
        
        return {out_field: result}
    
    return node
