"""
世界书（World Info）抽取器

从小说/设定文本中抽取世界观条目，输出格式兼容 SillyTavern。

提示词配置目录: extraction/prompts/
  - worldinfo_system.html   系统提示词
  - worldinfo_user.html     用户提示词模板
  - worldinfo_gleaning.html Gleaning 补漏提示词

输出格式:
[
    {
        "name": "实体名称",
        "key": "触发关键词1,关键词2",
        "content": "世界观设定内容...",
        "comment": "条目说明（可选）",
        "priority": 10,
        "enabled": true
    },
    ...
]
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .base import BaseExtractor


# 提示词目录
PROMPTS_DIR = Path(__file__).parent / "prompts"


def _extract_prompt_content(xml_content: str) -> str:
    """
    从 XML 文件中提取 <prompt> 标签内的内容
    
    保留内部的 XML 标签结构，只去掉外层 <prompt> 包装
    """
    # 匹配 <prompt>...</prompt> 内容
    match = re.search(r"<prompt>(.*)</prompt>", xml_content, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 如果没有 <prompt> 标签，返回去掉 XML 声明和注释后的内容
    content = re.sub(r"<\?xml[^>]*\?>", "", xml_content)
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    return content.strip()


@lru_cache()
def load_prompt_file(filename: str, prompts_dir: str = None) -> str:
    """
    加载单个提示词文件
    
    Args:
        filename: 文件名（如 worldinfo_system.xml）
        prompts_dir: 提示词目录路径，默认使用 extraction/prompts/
    
    Returns:
        提示词内容（去掉外层 <prompt> 标签）
    """
    if prompts_dir is None:
        prompt_path = PROMPTS_DIR / filename
    else:
        prompt_path = Path(prompts_dir) / filename
    
    if not prompt_path.exists():
        return ""
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    return _extract_prompt_content(content)


class WorldInfoExtractor(BaseExtractor):
    """
    世界书抽取器
    
    从文本中提取世界观设定，生成可用于 RAG 检索的条目。
    提示词从 prompts/ 目录下的 XML 文件加载，支持语法高亮和直观编辑。
    
    提示词文件:
        - prompts/worldinfo_system.html   系统提示词
        - prompts/worldinfo_user.html     用户提示词模板
        - prompts/worldinfo_gleaning.html Gleaning 补漏提示词
    
    用法:
        extractor = WorldInfoExtractor()
        
        # 单次抽取
        result = extractor.extract(text)
        if result.success:
            entries = result.data  # list[dict]
        
        # 从文件抽取
        result = extractor.extract_from_file("novel.txt")
        
        # 长文本分块抽取
        results = extractor.extract_chunks(long_text, chunk_size=6000)
        all_entries = []
        for r in results:
            if r.success:
                all_entries.extend(r.data)
        
        # 自定义提示词目录
        extractor = WorldInfoExtractor(prompts_dir="my_prompts/")
    """
    
    def __init__(
        self,
        system_prompt: str = None,
        user_prompt_template: str = None,
        gleaning_prompt: str = None,
        merge_prompt: str = None,
        enable_gleaning: bool = True,
        enable_llm_merge: bool = False,
        preserve_order: bool = False,
        prompts_dir: str = None,
        **kwargs
    ):
        """
        初始化世界书抽取器
        
        Args:
            system_prompt: 自定义系统提示词（覆盖配置文件）
            user_prompt_template: 自定义用户提示词模板（需包含 {text} 占位符）
            gleaning_prompt: 自定义 Gleaning 补漏提示词
            enable_gleaning: 是否启用 Gleaning 补漏（二次检查遗漏）
            prompts_dir: 提示词目录路径，默认使用 extraction/prompts/
            **kwargs: 传递给 BaseExtractor 的参数
        """
        super().__init__(**kwargs)
        
        # 优先使用传入参数，否则从 XML 文件加载，最后使用内置默认值
        self.system_prompt = (
            system_prompt 
            or load_prompt_file("worldinfo_system.html", prompts_dir) 
            or self._get_fallback_system_prompt()
        )
        self.user_prompt_template = (
            user_prompt_template 
            or load_prompt_file("worldinfo_user.html", prompts_dir) 
            or self._get_fallback_user_prompt()
        )
        self.gleaning_prompt_template = (
            gleaning_prompt 
            or load_prompt_file("worldinfo_gleaning.html", prompts_dir) 
            or self._get_fallback_gleaning_prompt()
        )
        self.merge_prompt_template = (
            merge_prompt
            or load_prompt_file("worldinfo_merge.html", prompts_dir)
            or self._get_fallback_merge_prompt()
        )
        self.enable_gleaning = enable_gleaning
        self.enable_llm_merge = enable_llm_merge
        # LLM 合并默认以顺序为时间线，启用时强制保序
        self.preserve_order = preserve_order or enable_llm_merge
    
    @staticmethod
    def _get_fallback_system_prompt() -> str:
        """内置默认系统提示词（XML 文件不存在时使用）"""
        return """<role>你是一名专业的世界观设定分析师。</role>
<task>从文本中提取世界观设定，输出 JSON 数组。</task>
<format>每个条目包含: key(关键词), content(内容), comment(类型), priority(1-100)</format>"""
    
    @staticmethod
    def _get_fallback_user_prompt() -> str:
        """内置默认用户提示词"""
        return """<input_text>{text}</input_text>
请提取世界观设定，输出 JSON 数组。"""
    
    @staticmethod
    def _get_fallback_gleaning_prompt() -> str:
        """内置默认 Gleaning 提示词"""
        return """<task>检查是否有遗漏的设定，只输出新增或补充的条目。</task>
<original_text>{text}</original_text>"""

    @staticmethod
    def _get_fallback_merge_prompt() -> str:
        """内置默认合并提示词（merge prompt 文件不存在时使用）"""
        return """<role>你是一名专业的世界观知识库编辑。</role>
<task>合并并去重一组 world_info 条目，必要时对同名做消歧，输出 JSON 数组。</task>
<rules>只输出 JSON 数组；每个条目必须包含 name,key,content,comment,priority,enabled；name 必须唯一。</rules>"""

    def _llm_merge_entries(self, entries: list[dict]) -> list[dict]:
        """
        使用 LLM 对跨 chunk 的条目进行合并/去重/同名消歧。
        输入/输出均为 world_info entry 列表。
        """
        if not entries:
            return []

        merge_prompt = [
            {"role": "system", "content": self.merge_prompt_template},
            {
                "role": "user",
                "content": (
                    "请合并以下 world_info 条目（JSON 数组），并按提示要求只输出合并后的 JSON 数组：\n"
                    + json.dumps(entries, ensure_ascii=False, indent=2)
                ),
            },
        ]

        raw_output = self.llm.invoke(merge_prompt)
        merged = self.parse_response(raw_output)
        return merged
    
    def build_prompt(self, text: str, **kwargs) -> list:
        """构建消息列表"""
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.user_prompt_template.format(text=text)},
        ]
    
    def extract(self, text: str, **kwargs):
        """
        从文本中抽取数据（支持 Gleaning 补漏）
        
        覆盖父类方法，添加二次抽取逻辑
        """
        # 第一次抽取
        result = super().extract(text, **kwargs)
        
        if not result.success or not self.enable_gleaning:
            return result
        
        # Gleaning: 第二次抽取补漏
        try:
            gleaning_prompt = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self.user_prompt_template.format(text=text)},
                {"role": "assistant", "content": result.raw_output},
                {"role": "user", "content": self.gleaning_prompt_template.format(text=text)},
            ]
            
            gleaning_output = self.llm.invoke(gleaning_prompt)
            gleaning_data = self.parse_response(gleaning_output)
            
            if gleaning_data:
                # 合并结果：Gleaning 的条目优先（可能是更完整的版本）
                merged = self._merge_entries(result.data, gleaning_data)
                result.data = merged
                result.metadata["gleaning_added"] = len(gleaning_data)
        
        except Exception as e:
            # Gleaning 失败不影响主结果
            result.metadata["gleaning_error"] = str(e)
        
        return result
    
    def _merge_entries(self, original: list[dict], gleaning: list[dict]) -> list[dict]:
        """
        合并原始结果和 Gleaning 结果
        
        策略：
        - 如果 key 的首关键词相同，比较 content 长度，保留更长的
        - 否则视为新条目
        """
        result = {self._get_primary_key(e): e for e in original}
        
        for entry in gleaning:
            primary_key = self._get_primary_key(entry)
            if primary_key in result:
                # 比较 content 长度，保留更详细的
                if len(entry.get("content", "")) > len(result[primary_key].get("content", "")):
                    result[primary_key] = entry
            else:
                result[primary_key] = entry
        
        return list(result.values())
    
    def _get_primary_key(self, entry: dict) -> str:
        """获取条目的主标识符（用于去重）"""
        # 优先使用 name，否则回退到 key 的第一个词
        name = entry.get("name", "")
        if name:
            return name.strip().lower()
        key = entry.get("key", "")
        return key.split(",")[0].strip().lower()
    
    def parse_response(self, response: str) -> list[dict]:
        """解析 JSON 响应"""
        data = self.extract_json(response)
        
        if not isinstance(data, list):
            raise ValueError(f"期望返回数组，实际返回: {type(data)}")
        
        # 验证并规范化每个条目
        entries = []
        for item in data:
            if not isinstance(item, dict):
                continue
            
            # 获取 name，如果没有则从 key 的第一个词提取
            name = str(item.get("name", "")).strip()
            key = str(item.get("key", item.get("keys", "")))
            if not name and key:
                name = key.split(",")[0].strip()
            
            entry = {
                "name": name,
                "key": key,
                "content": str(item.get("content", "")),
                "comment": str(item.get("comment", "")),
                "priority": int(item.get("priority", 10)),
                "enabled": True,
            }
            
            # 跳过空条目
            if not entry["name"] or not entry["content"]:
                continue
            
            entries.append(entry)
        
        return entries
    
    def postprocess(self, data: list[dict]) -> list[dict]:
        """后处理：去重并按优先级排序"""
        seen_keys = set()
        unique_entries = []
        
        for entry in data:
            primary_key = self._get_primary_key(entry)
            if primary_key not in seen_keys:
                seen_keys.add(primary_key)
                unique_entries.append(entry)
        
        # 按优先级排序（可选保留顺序）
        if not self.preserve_order:
            unique_entries.sort(key=lambda x: x["priority"], reverse=True)
        
        return unique_entries
    
    def merge_results(self, results: list) -> list[dict]:
        """
        合并多个分块的抽取结果
        
        Args:
            results: extract_chunks 返回的结果列表
        
        Returns:
            去重合并后的条目列表
        """
        all_entries = []
        for result in results:
            if result.success and result.data:
                all_entries.extend(result.data)

        # 可选：使用 LLM 做跨 chunk 合并/同名消歧（更稳，但会多一次调用）
        if self.enable_llm_merge and len(results) > 1 and all_entries:
            try:
                all_entries = self._llm_merge_entries(all_entries)
            except Exception as e:
                # LLM 合并失败则回退到本地去重逻辑
                # 这里不抛异常，避免影响主流程
                pass

        return self.postprocess(all_entries)
