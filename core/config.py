"""
配置加载器：读取 config.yaml 并提供类型安全的配置访问
"""
import os
import yaml
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional


@dataclass
class LLMConfig:
    """LLM 配置"""
    provider: str = "openai"
    model: str = "gpt-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    
    def __post_init__(self):
        # 优先使用配置文件中的值，否则从环境变量读取
        if not self.api_key:
            self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.base_url:
            self.base_url = os.getenv("OPENAI_BASE_URL")


@dataclass
class DatabaseConfig:
    """数据库配置"""
    path: str = "data/app.db"
    messages_path: str = "data/messages.db"
    memories_path: str = "data/memories.db"


@dataclass
class VectorStoreConfig:
    """向量库配置"""
    enabled: bool = False
    provider: str = "chroma"
    path: str = "data/vectors"


@dataclass
class Config:
    """应用配置"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    vector_store: VectorStoreConfig = field(default_factory=VectorStoreConfig)


def _find_config_file() -> Path:
    """查找配置文件"""
    # 从当前目录向上查找
    current = Path.cwd()
    for _ in range(5):
        config_path = current / "config.yaml"
        if config_path.exists():
            return config_path
        current = current.parent
    
    # 默认路径
    return Path("config.yaml")


def _dict_to_dataclass(cls, data: dict):
    """
    递归将 dict 转为 dataclass
    
    自动处理嵌套的 dataclass 字段
    """
    from dataclasses import fields, is_dataclass
    
    if data is None:
        return cls()
    
    kwargs = {}
    for f in fields(cls):
        value = data.get(f.name)
        # 处理嵌套 dataclass
        if value is not None and is_dataclass(f.type):
            value = _dict_to_dataclass(f.type, value)
        if value is not None:
            kwargs[f.name] = value
    
    return cls(**kwargs)


@lru_cache()
def load_config(path: str = None) -> Config:
    """
    加载配置文件
    
    Args:
        path: 配置文件路径，默认自动查找
    
    Returns:
        Config 对象
    """
    config_path = Path(path) if path else _find_config_file()
    
    if not config_path.exists():
        return Config()
    
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    
    return _dict_to_dataclass(Config, data)


def get_config() -> Config:
    """获取配置（便捷方法）"""
    return load_config()
