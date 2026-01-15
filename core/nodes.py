"""
节点工厂

用于 graph.add_node() 的预置节点。
所有函数都返回一个 (state) -> dict 的节点函数。
"""
import re


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
