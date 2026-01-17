"""
抽取器基类

定义统一的抽取接口，子类实现具体的 prompt 和解析逻辑。
"""
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from core.tools import LLMClient


@dataclass
class ExtractionResult:
    """抽取结果"""
    success: bool
    data: Any = None                    # 抽取到的结构化数据
    raw_output: str = ""                # LLM 原始输出
    error: Optional[str] = None         # 错误信息
    source: Optional[str] = None        # 来源（文件路径或文本片段）
    metadata: dict = field(default_factory=dict)  # 额外元数据


class BaseExtractor(ABC):
    """
    抽取器基类
    
    子类需要实现:
    - build_prompt(): 构建发给 LLM 的提示词
    - parse_response(): 解析 LLM 返回的内容
    
    可选覆盖:
    - preprocess(): 预处理输入文本
    - postprocess(): 后处理抽取结果
    """
    
    def __init__(
        self,
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        **llm_kwargs
    ):
        """
        初始化抽取器
        
        Args:
            model: LLM 模型名称，None 使用配置默认值
            temperature: 生成温度，抽取任务建议低一些
            max_tokens: 最大输出 token
            **llm_kwargs: 其他 LLM 参数
        """
        self.llm = LLMClient(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,  # 抽取任务不需要流式
            **llm_kwargs
        )
    
    # ============================================================
    # 核心抽取方法
    # ============================================================
    
    def extract(self, text: str, **kwargs) -> ExtractionResult:
        """
        从文本中抽取数据
        
        Args:
            text: 输入文本
            **kwargs: 传递给 build_prompt 的额外参数
        
        Returns:
            ExtractionResult
        """
        try:
            # 1. 预处理
            processed_text = self.preprocess(text)
            
            # 2. 构建 prompt
            prompt = self.build_prompt(processed_text, **kwargs)
            
            # 3. 调用 LLM
            raw_output = self.llm.invoke(prompt)
            
            # 4. 解析响应
            data = self.parse_response(raw_output)
            
            # 5. 后处理
            data = self.postprocess(data)
            
            return ExtractionResult(
                success=True,
                data=data,
                raw_output=raw_output,
                source=text[:100] + "..." if len(text) > 100 else text,
            )
        
        except Exception as e:
            return ExtractionResult(
                success=False,
                error=str(e),
                source=text[:100] + "..." if len(text) > 100 else text,
            )
    
    def extract_from_file(
        self, 
        file_path: str | Path,
        encoding: str = "utf-8",
        **kwargs
    ) -> ExtractionResult:
        """
        从文件中抽取数据
        
        Args:
            file_path: 文件路径
            encoding: 文件编码
            **kwargs: 传递给 extract 的额外参数
        
        Returns:
            ExtractionResult
        """
        path = Path(file_path)
        
        if not path.exists():
            return ExtractionResult(
                success=False,
                error=f"文件不存在: {path}",
                source=str(path),
            )
        
        try:
            text = path.read_text(encoding=encoding)
        except Exception as e:
            return ExtractionResult(
                success=False,
                error=f"读取文件失败: {e}",
                source=str(path),
            )
        
        result = self.extract(text, **kwargs)
        result.source = str(path)
        return result
    
    def extract_chunks(
        self,
        text: str,
        chunk_size: int = 8000,
        overlap: int = 500,
        chunk_strategy: Literal["auto", "fixed", "chapters"] = "auto",
        chapter_max_chars: int = 20000,
        **kwargs
    ) -> list[ExtractionResult]:
        """
        分块抽取（处理长文本）
        
        Args:
            text: 输入文本
            chunk_size: 每块大小（字符数）
            overlap: 块之间的重叠（避免截断实体）
            chunk_strategy: 分块策略
                - auto: 有明显章节标题则按章节，否则按固定长度
                - fixed: 固定长度 + overlap
                - chapters: 按 Markdown 章节标题分块（超长章节再按 chapter_max_chars 切分）
            chapter_max_chars: 章节块最大字符数（仅在 chapters/auto 生效）
            **kwargs: 传递给 extract 的额外参数
        
        Returns:
            每块的抽取结果列表
        """
        chunks = self._split_text(
            text,
            chunk_size,
            overlap,
            strategy=chunk_strategy,
            chapter_max_chars=chapter_max_chars,
        )
        results = []
        
        for i, chunk in enumerate(chunks):
            print(f"  处理分块 {i+1}/{len(chunks)}...")
            result = self.extract(chunk, chunk_index=i, total_chunks=len(chunks), **kwargs)
            result.metadata["chunk_index"] = i
            result.metadata["total_chunks"] = len(chunks)
            results.append(result)
        
        return results
    
    # ============================================================
    # 子类实现
    # ============================================================
    
    @abstractmethod
    def build_prompt(self, text: str, **kwargs) -> str | list:
        """
        构建发给 LLM 的提示词
        
        Args:
            text: 预处理后的文本
            **kwargs: 额外参数
        
        Returns:
            提示词字符串或消息列表
        """
        pass
    
    @abstractmethod
    def parse_response(self, response: str) -> Any:
        """
        解析 LLM 返回的内容
        
        Args:
            response: LLM 原始输出
        
        Returns:
            结构化数据
        """
        pass
    
    # ============================================================
    # 可选覆盖
    # ============================================================
    
    def preprocess(self, text: str) -> str:
        """
        预处理输入文本
        
        默认：去除首尾空白
        子类可覆盖以实现自定义预处理
        """
        return text.strip()
    
    def postprocess(self, data: Any) -> Any:
        """
        后处理抽取结果
        
        默认：直接返回
        子类可覆盖以实现去重、合并等
        """
        return data
    
    # ============================================================
    # 工具方法
    # ============================================================
    
    def _split_text(
        self,
        text: str,
        chunk_size: int,
        overlap: int,
        *,
        strategy: Literal["auto", "fixed", "chapters"] = "auto",
        chapter_max_chars: int = 20000,
    ) -> list[str]:
        """
        分割文本
        
        优先按段落分割，避免截断句子
        """
        return self._split_text_ex(
            text,
            chunk_size,
            overlap,
            strategy=strategy,
            chapter_max_chars=chapter_max_chars,
        )

    def _split_text_ex(
        self,
        text: str,
        chunk_size: int,
        overlap: int,
        *,
        strategy: Literal["auto", "fixed", "chapters"] = "auto",
        chapter_max_chars: int = 20000,
    ) -> list[str]:
        """
        分割文本（支持章节策略）。

        - fixed: 固定长度优先按段落/换行/句末切分
        - chapters: 按 Markdown 标题行（# / ## / ...）切分章节；章节过长则按 chapter_max_chars 再切
        - auto: 有多个章节标题则使用 chapters，否则使用 fixed
        """
        if not text or not text.strip():
            return []

        if strategy == "fixed":
            return self._split_text_fixed(text, chunk_size, overlap)

        if strategy == "auto":
            headings = self._find_markdown_heading_positions(text)
            # 至少 2 个标题才有明显“章节化”价值，避免误判
            strategy = "chapters" if len(headings) >= 2 else "fixed"
            return self._split_text_ex(
                text,
                chunk_size,
                overlap,
                strategy=strategy,
                chapter_max_chars=chapter_max_chars,
            )

        # chapters
        chapters = self._split_markdown_chapters(text)
        if not chapters:
            return self._split_text_fixed(text, chunk_size, overlap)

        max_chars = int(chapter_max_chars) if chapter_max_chars else 0
        if max_chars <= 0:
            return [c for c in chapters if c.strip()]

        out: list[str] = []
        for ch in chapters:
            ch = ch.strip()
            if not ch:
                continue
            if len(ch) <= max_chars:
                out.append(ch)
                continue
            # 超长章节：按章节上限再切，避免单章过长
            out.extend(self._split_text_fixed(ch, max_chars, overlap))
        return out

    def _split_text_fixed(self, text: str, chunk_size: int, overlap: int) -> list[str]:
        """固定长度切分：优先段落/换行/句末边界，带 overlap。"""
        if len(text) <= chunk_size:
            return [text.strip()]

        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            if end >= len(text):
                chunks.append(text[start:].strip())
                break

            # 尝试在段落边界切分
            split_pos = text.rfind("\n\n", start + chunk_size // 2, end)
            if split_pos == -1:
                # 没找到段落边界，尝试换行符
                split_pos = text.rfind("\n", start + chunk_size // 2, end)
            if split_pos == -1:
                # 没找到换行符，尝试句号
                for sep in ["。", ".", "！", "!", "？", "?"]:
                    split_pos = text.rfind(sep, start + chunk_size // 2, end)
                    if split_pos != -1:
                        split_pos += 1  # 包含标点
                        break
            if split_pos == -1:
                # 都没找到，直接切
                split_pos = end

            chunks.append(text[start:split_pos].strip())
            start = split_pos - overlap  # 带重叠
            if start < 0:
                start = split_pos

        return [c for c in chunks if c]

    def _find_markdown_heading_positions(self, text: str) -> list[int]:
        """
        找到 Markdown 标题行起始位置（忽略 ``` 围栏代码块内部）。
        例如：# ○椎名日和的独白
        """
        positions: list[int] = []
        in_fence = False
        offset = 0
        for line in text.splitlines(keepends=True):
            stripped = line.lstrip()
            if stripped.startswith("```"):
                in_fence = not in_fence
            if not in_fence:
                if re.match(r"^\s{0,3}#{1,6}\s+\S", line):
                    positions.append(offset)
            offset += len(line)
        return positions

    def _split_markdown_chapters(self, text: str) -> list[str]:
        """按 Markdown 标题分章：每个 chunk 从标题行开始，包含到下一个标题之前。"""
        positions = self._find_markdown_heading_positions(text)
        if not positions:
            return []

        segments: list[str] = []
        # 处理首标题前的“前言/序章”内容
        if positions[0] > 0:
            pre = text[: positions[0]].strip()
            if pre:
                segments.append(pre)

        for i, start in enumerate(positions):
            end = positions[i + 1] if i + 1 < len(positions) else len(text)
            seg = text[start:end].strip()
            if seg:
                segments.append(seg)

        return segments
    
    @staticmethod
    def extract_json(text: str) -> Any:
        """
        从文本中提取 JSON
        
        支持:
        - 纯 JSON
        - ```json ... ``` 代码块
        - 混杂文本中的 JSON
        """
        import re
        
        text = text.strip()
        
        # 1. 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        # 2. 尝试提取 ```json ... ``` 代码块
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        
        # 3. 尝试提取 [...] 或 {...}
        for pattern in [r"\[[\s\S]*\]", r"\{[\s\S]*\}"]:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        
        raise ValueError(f"无法从文本中提取 JSON: {text[:200]}...")
