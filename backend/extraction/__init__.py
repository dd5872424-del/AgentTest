"""
数据抽取模块

使用 LLM 从文本/文件中提取结构化知识。

用法示例:
    # 1. 代码调用
    from extraction import WorldInfoExtractor
    
    extractor = WorldInfoExtractor()
    entries = extractor.extract_from_file("novel.txt")
    
    # 2. 命令行
    cd backend
    python -m extraction.run worldinfo novel.txt -o output.json
"""

from .base import BaseExtractor, ExtractionResult
from .worldinfo import WorldInfoExtractor

__all__ = [
    "BaseExtractor",
    "ExtractionResult",
    "WorldInfoExtractor",
]
