"""
工具类：封装 LLM 操作

记忆管理已移至 state，由 LangGraph checkpointer 自动持久化。
"""
from typing import Optional, Callable


# 全局流式输出回调（由 Runtime 设置）
_stream_callback: Optional[Callable[[str], None]] = None


def set_stream_callback(callback: Optional[Callable[[str], None]]):
    """设置全局流式输出回调"""
    global _stream_callback
    _stream_callback = callback


def get_stream_callback() -> Optional[Callable[[str], None]]:
    """获取全局流式输出回调"""
    return _stream_callback


class LLMClient:
    """
    LLM 调用客户端
    
    使用 LangChain 的 ChatModel 封装，支持多提供商
    """
    
    def __init__(self, provider: str = None, model: str = None, 
                 api_key: Optional[str] = None, base_url: Optional[str] = None,
                 **kwargs):
        from .config import get_config
        config = get_config()
        self.config = config.llm
        
        # 基础配置
        self.provider = provider or self.config.provider
        self.model = model or self.config.model
        self.api_key = api_key or self.config.api_key
        self.base_url = base_url or self.config.base_url
        
        # 生成参数（可通过 kwargs 覆盖）
        self.max_tokens = kwargs.get('max_tokens', self.config.max_tokens)
        self.temperature = kwargs.get('temperature', self.config.temperature)
        self.top_p = kwargs.get('top_p', self.config.top_p)
        self.stream = kwargs.get('stream', self.config.stream)
        self.timeout = kwargs.get('timeout', self.config.timeout)
        self.max_retries = kwargs.get('max_retries', self.config.max_retries)
        
        self._client = self._create_client()
    
    def _get_model_kwargs(self) -> dict:
        """构建模型参数（过滤 None 值）"""
        params = {
            'model': self.model,
            'api_key': self.api_key,
        }
        
        # 可选参数
        if self.base_url:
            params['base_url'] = self.base_url
        if self.max_tokens is not None:
            params['max_tokens'] = self.max_tokens
        if self.temperature is not None:
            params['temperature'] = self.temperature
        if self.top_p is not None:
            params['top_p'] = self.top_p
        if self.timeout is not None:
            params['timeout'] = self.timeout
        if self.max_retries is not None:
            params['max_retries'] = self.max_retries
            
        return params
    
    def _create_client(self):
        """根据 provider 创建 LangChain ChatModel"""
        params = self._get_model_kwargs()
        
        try:
            if self.provider == "openai":
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(**params)
            
            elif self.provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                # Anthropic 不支持 base_url
                params.pop('base_url', None)
                return ChatAnthropic(**params)
            
            elif self.provider == "google":
                from langchain_google_genai import ChatGoogleGenerativeAI
                # Google 参数略有不同
                params.pop('base_url', None)
                return ChatGoogleGenerativeAI(**params)
            
            else:
                # 默认尝试 OpenAI 兼容接口
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(**params)
        
        except ImportError as e:
            print(f"[警告] 无法导入 {self.provider} 的 LangChain 模块: {e}")
            return None
    
    def invoke(self, prompt: str | list, stream_callback: Callable[[str], None] = None) -> str:
        """
        调用 LLM
        
        Args:
            prompt: 提示词（字符串或消息列表）
            stream_callback: 流式输出回调，如果提供则使用流式模式
                            如果为 None 且配置了 stream=True，使用全局回调
        
        Returns:
            完整的响应文本
        """
        if self._client is None:
            return f"[模拟响应] 收到: {str(prompt)[:50]}..."
        
        # 转换为 LangChain 消息格式
        if isinstance(prompt, str):
            from langchain_core.messages import HumanMessage
            messages = [HumanMessage(content=prompt)]
        else:
            messages = self._convert_messages(prompt)
        
        # 决定是否使用流式
        callback = stream_callback or (get_stream_callback() if self.stream else None)
        
        if callback:
            # 流式调用
            return self._stream_invoke(messages, callback)
        else:
            # 普通调用
            response = self._client.invoke(messages)
            return response.content
    
    def _stream_invoke(self, messages: list, callback: Callable[[str], None]) -> str:
        """流式调用 LLM 并通过回调输出"""
        full_response = []
        
        for chunk in self._client.stream(messages):
            if chunk.content:
                callback(chunk.content)
                full_response.append(chunk.content)
        
        return "".join(full_response)
    
    def _convert_messages(self, messages: list):
        """将 OpenAI 格式消息转为 LangChain 格式"""
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
        
        result = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                result.append(SystemMessage(content=content))
            elif role == "assistant":
                result.append(AIMessage(content=content))
            else:
                result.append(HumanMessage(content=content))
        
        return result
    
    async def ainvoke(self, prompt: str | list) -> str:
        """异步调用 LLM"""
        if self._client is None:
            return f"[模拟响应] 收到: {str(prompt)[:50]}..."
        
        if isinstance(prompt, str):
            from langchain_core.messages import HumanMessage
            messages = [HumanMessage(content=prompt)]
        else:
            messages = self._convert_messages(prompt)
        
        response = await self._client.ainvoke(messages)
        return response.content


class ChatTools:
    """
    聊天工具集
    
    提供 LLM 调用能力，记忆管理已移至 state 由 checkpointer 管理。
    """
    
    def __init__(self, model: str = None):
        self.llm = LLMClient(model=model)
    
    def call_llm(self, prompt: str | list, stream_callback: Callable[[str], None] = None) -> str:
        """
        调用 LLM
        
        Args:
            prompt: 提示词
            stream_callback: 可选的流式回调，不传则使用全局配置
        
        Returns:
            完整响应文本
        """
        return self.llm.invoke(prompt, stream_callback)
