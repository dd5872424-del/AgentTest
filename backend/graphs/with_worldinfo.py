"""
世界观检索图：基于关键词检索 world_info 并注入对话

流程: prepare_keywords → search_world_info → respond → parse_output

关键词来源（混合策略）:
    1. 当前轮用户输入的空格分词（用户可主动控制）
    2. 上轮 LLM 提取的关键词（AI 理解的上下文）

LLM 输出格式（HTML 标签）:
    <reply>回复内容</reply>
    <keywords>关键词1,关键词2,关键词3</keywords>

消息处理架构:
    - raw_messages: 由 Runtime 追加用户输入，Node 追加 AI 回复
    - current_messages: 由 Node 构建，包含系统设定 + 检索到的世界观 + 历史对话
"""
import json
import re
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from core.tools import ChatTools
from core.state import ChatState
from core.utils import build_current_messages, append_to_raw


class State(ChatState, total=False):
    """
    世界观检索状态
    
    扩展字段:
    - keywords: 关键词列表（当前轮分词 + 上轮LLM提取，用于检索）
    - llm_keywords: LLM 提取的关键词（持久化，下轮使用）
    - matched_entries: 命中的 world_info 条目
    - llm_raw_output: LLM 原始输出（含 HTML 标签）
    """
    keywords: list
    llm_keywords: list
    matched_entries: list
    llm_raw_output: str


def build_graph(checkpointer: BaseCheckpointSaver = None):
    """构建世界观检索图"""
    tools = ChatTools()
    
    # ============================================================
    # 节点1: 准备关键词（合并当前输入分词 + 上轮LLM关键词）
    # ============================================================
    def prepare_keywords(state):
        """
        合并关键词来源:
        1. 当前轮用户输入 → 空格分词
        2. 上轮 LLM 提取的 llm_keywords
        """
        raw_messages = state.get("raw_messages", [])
        llm_keywords = state.get("llm_keywords", [])
        
        # 1. 从当前用户输入提取（空格分词）
        current_keywords = []
        if raw_messages:
            last_user_msg = None
            for msg in reversed(raw_messages):
                if msg.get("role") == "user":
                    last_user_msg = msg.get("content", "")
                    break
            
            if last_user_msg:
                current_keywords = _simple_tokenize(last_user_msg)
        
        # 2. 合并：当前分词（优先）+ 上轮LLM关键词
        merged = []
        seen = set()
        
        # 当前轮关键词优先
        for kw in current_keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen:
                seen.add(kw_lower)
                merged.append(kw)
        
        # 补充上轮 LLM 关键词
        for kw in llm_keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen:
                seen.add(kw_lower)
                merged.append(kw)
        
        return {"keywords": merged}
    
    # ============================================================
    # 节点2: 检索 world_info
    # ============================================================
    def search_world_info(state):
        """
        在 world_info 中搜索匹配的条目
        
        world_info 格式:
        [
            {
                "name": "实体名称",          # 用于唯一标识和去重
                "key": "关键词1,关键词2",    # 触发关键词
                "content": "世界观内容...",
                "comment": "类型标注",        # 可选
                "priority": 1,               # 可选
                "enabled": True              # 可选
            },
            ...
        ]
        """
        keywords = state.get("keywords", [])
        world_info = state.get("world_info", [])
        
        if not world_info or not keywords:
            return {"matched_entries": []}
        
        # 构建检索文本（关键词拼接）
        search_text = " ".join(keywords)
        
        matched = []
        for entry in world_info:
            if not entry.get("enabled", True):
                continue
            
            entry_keys = entry.get("key", entry.get("keys", ""))
            if isinstance(entry_keys, str):
                entry_keys = [k.strip() for k in entry_keys.split(",") if k.strip()]
            elif entry_keys is None:
                entry_keys = []
            else:
                entry_keys = [k for k in entry_keys if isinstance(k, str) and k.strip()]

            # 合并 name 到关键词列表，提升检索命中率
            entry_name = entry.get("name", "")
            if isinstance(entry_name, str) and entry_name.strip():
                entry_keys.append(entry_name.strip())
            
            if _match_keywords(search_text, keywords, entry_keys):
                matched.append({
                    "name": entry.get("name", ""),
                    "content": entry.get("content", ""),
                    "priority": entry.get("priority", 0),
                    "key": entry_keys
                })
        
        # 按优先级排序
        matched.sort(key=lambda x: x.get("priority", 0), reverse=True)
        
        return {"matched_entries": matched}
    
    # ============================================================
    # 节点3: 生成回复（LLM 输出 HTML 格式）
    # ============================================================
    def respond(state):
        """
        调用 LLM，要求输出 HTML 格式:
        <reply>回复内容</reply>
        <keywords>关键词1,关键词2</keywords>
        """
        raw_messages = state.get("raw_messages", [])
        matched_entries = state.get("matched_entries", [])
        preset = state.get("preset", {})
        
        # 1. 构建基础 system prompt
        base_prompt = preset.get(
            "system_prompt",
            "你是一个故事引擎，需要根据<worldinfo>和历史对话进行创作",
        )
        
        # 2. 构建世界观注入内容
        extra_system = []
        if matched_entries:
            wi_entries = []
            for e in matched_entries:
                name = (e.get("name") or "").strip()
                keys = e.get("key") or []
                if isinstance(keys, list):
                    key_text = ", ".join([k for k in keys if k])
                else:
                    key_text = str(keys)
                content = (e.get("content") or "").strip()
                if not (name or key_text or content):
                    continue
                wi_entries.append({
                    "name": name,
                    "key": key_text,
                    "content": content,
                })
            if wi_entries:
                wi_text = json.dumps(wi_entries, ensure_ascii=False)
                extra_system.append({
                    "role": "system",
                    "content": f"<worldinfo>\n{wi_text}\n</worldinfo>"
                })
        
        # 3. 添加输出格式指令
        format_instruction = """
【输出格式要求】
请严格按以下 HTML 格式输出：
<reply>
你的回复内容（自然对话，不要包含标签）
</reply>
<keywords>与对话相关的关键词,用逗号分隔,3-5个</keywords>

注意：关键词应该是对话中涉及的重要实体、概念、地点、人物等，用于后续检索相关信息。
"""
        extra_system.append({
            "role": "system",
            "content": format_instruction
        })
        
        # 4. 构建 current_messages
        current_messages = build_current_messages(
            raw_messages,
            system_prompt=base_prompt,
            max_history=20,
            extra_system=extra_system
        )
        
        # 5. 调用 LLM
        llm_raw_output = tools.call_llm(current_messages)
        
        return {
            "current_messages": current_messages,
            "llm_raw_output": llm_raw_output
        }
    
    # ============================================================
    # 节点4: 解析输出（分离回复和关键词）
    # ============================================================
    def parse_output(state):
        """
        解析 LLM 的 HTML 格式输出:
        - <reply>...</reply> → last_output, raw_messages
        - <keywords>...</keywords> → llm_keywords (下轮使用)
        """
        raw_messages = state.get("raw_messages", [])
        llm_raw_output = state.get("llm_raw_output", "")
        
        # 解析 <reply>
        reply_content = _extract_tag(llm_raw_output, "reply")
        if not reply_content:
            # 兜底：如果没有标签，整个输出作为回复
            reply_content = _strip_all_tags(llm_raw_output)
        
        # 解析 <keywords>
        keywords_str = _extract_tag(llm_raw_output, "keywords")
        llm_keywords = []
        if keywords_str:
            llm_keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        
        # 追加 AI 回复到 raw_messages
        new_raw_messages = append_to_raw(raw_messages, "assistant", reply_content)
        
        return {
            "raw_messages": new_raw_messages,
            "last_output": reply_content,
            "llm_keywords": llm_keywords
        }
    
    # ============================================================
    # 构建图
    # ============================================================
    graph = StateGraph(State)
    
    graph.add_node("prepare", prepare_keywords)
    graph.add_node("search", search_world_info)
    graph.add_node("respond", respond)
    graph.add_node("parse", parse_output)
    
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "search")
    graph.add_edge("search", "respond")
    graph.add_edge("respond", "parse")
    graph.add_edge("parse", END)
    
    return graph.compile(checkpointer=checkpointer)


def get_initial_state():
    """初始状态"""
    return {
        "memories": [],
        "world_info": [],
        "preset": {},
        "keywords": [],
        "llm_keywords": [],
        "matched_entries": [],
    }


# ============================================================
# 辅助函数
# ============================================================

def _simple_tokenize(text: str) -> list[str]:
    """
    简单空格分词
    
    用户可通过空格主动标记关键词:
    "告诉我 魔法森林 的秘密" → ["告诉我", "魔法森林", "的秘密"]
    """
    if not text:
        return []
    
    # 按空格分割
    tokens = text.split()
    
    # 过滤太短的词（单字）
    tokens = [t.strip() for t in tokens if len(t.strip()) >= 2]
    
    return tokens


def _match_keywords(search_text: str, extracted_keywords: list, entry_keys: list) -> bool:
    """
    判断是否匹配
    
    匹配策略：entry_keys 中任一关键词出现在 search_text 或 extracted_keywords 中
    """
    if not entry_keys:
        return False
    
    search_lower = search_text.lower()
    keywords_lower = [k.lower() for k in extracted_keywords]
    
    for key in entry_keys:
        key_lower = key.lower()
        # 在搜索文本中匹配
        if key_lower in search_lower:
            return True
        # 在关键词列表中匹配
        if key_lower in keywords_lower:
            return True
    
    return False


def _extract_tag(text: str, tag: str) -> str:
    """
    提取 HTML 标签内容
    
    示例: _extract_tag("<reply>你好</reply>", "reply") → "你好"
    """
    pattern = rf"<{tag}>(.*?)</{tag}>"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _strip_all_tags(text: str) -> str:
    """
    移除所有 HTML 标签，保留内容
    
    兜底用：当 LLM 没有按格式输出时
    """
    # 移除 <tag>...</tag> 格式，保留中间内容
    result = re.sub(r"<(\w+)>(.*?)</\1>", r"\2", text, flags=re.DOTALL)
    # 移除单独的标签
    result = re.sub(r"</?[\w]+>", "", result)
    return result.strip()
