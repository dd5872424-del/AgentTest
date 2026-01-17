"""
依赖注入：提供 Runtime 单例
"""
from functools import lru_cache
from core import Runtime


@lru_cache()
def get_runtime() -> Runtime:
    """
    获取 Runtime 单例
    
    使用 lru_cache 确保整个应用生命周期内只有一个实例
    """
    return Runtime()
