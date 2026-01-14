"""
工具类：封装 LLM / Memory 操作
使用独立的存储层，LLM 使用 LangChain 封装
"""
from typing import Optional

from .config import get_config
from .storage import MemoryStore, InMemoryMemoryStore


class LLMClient:
    """
    LLM 调用客户端
    
    使用 LangChain 的 ChatModel 封装，支持多提供商
    """
    
    def __init__(self, provider: str = None, model: str = None, 
                 api_key: Optional[str] = None, base_url: Optional[str] = None):
        config = get_config()
        self.provider = provider or config.llm.provider
        self.model = model or config.llm.model
        self.api_key = api_key or config.llm.api_key
        self.base_url = base_url or config.llm.base_url
        self._client = self._create_client()
    
    def _create_client(self):
        """根据 provider 创建 LangChain ChatModel"""
        try:
            if self.provider == "openai":
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model=self.model, 
                    api_key=self.api_key,
                    base_url=self.base_url
                )
            
            elif self.provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                return ChatAnthropic(model=self.model, api_key=self.api_key)
            
            elif self.provider == "google":
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(model=self.model, api_key=self.api_key)
            
            else:
                # 默认尝试 OpenAI 兼容接口
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model=self.model, 
                    api_key=self.api_key,
                    base_url=self.base_url
                )
        
        except ImportError as e:
            print(f"[警告] 无法导入 {self.provider} 的 LangChain 模块: {e}")
            return None
    
    def invoke(self, prompt: str | list) -> str:
        """调用 LLM"""
        if self._client is None:
            return f"[模拟响应] 收到: {str(prompt)[:50]}..."
        
        # 转换为 LangChain 消息格式
        if isinstance(prompt, str):
            from langchain_core.messages import HumanMessage
            messages = [HumanMessage(content=prompt)]
        else:
            messages = self._convert_messages(prompt)
        
        response = self._client.invoke(messages)
        return response.content
    
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


class ChatMemory:
    """
    聊天记忆管理
    
    封装 MemoryStore，提供便捷方法
    """
    
    def __init__(self, conversation_id: str, store: MemoryStore):
        self.conversation_id = conversation_id
        self._store = store
    
    def search(self, query: str = None, top_k: int = 5) -> list[dict]:
        """检索记忆"""
        return self._store.search(self.conversation_id, query, top_k)
    
    def save(self, content: str, type: str = "default", metadata: dict = None):
        """保存记忆"""
        self._store.add(self.conversation_id, content, type, metadata)
    
    def delete(self, keyword: str):
        """删除包含关键词的记忆"""
        self._store.delete_by_keyword(self.conversation_id, keyword)
    
    def clear(self):
        """清空记忆"""
        self._store.clear(self.conversation_id)


class ChatTools:
    """
    聊天工具集
    
    整合 LLM 和 Memory，供节点使用
    """
    
    def __init__(self, conversation_id: str, 
                 memory_store: MemoryStore = None,
                 model: str = None):
        self.conversation_id = conversation_id
        self.llm = LLMClient(model=model)  # model=None 时使用配置文件中的设置
        
        # 使用传入的 store 或创建默认的内存存储
        self._memory_store = memory_store or InMemoryMemoryStore()
        self.memory = ChatMemory(conversation_id, self._memory_store)
    
    def search_memory(self, query: str, top_k: int = 5) -> list[dict]:
        """快捷方法：检索记忆"""
        return self.memory.search(query, top_k)
    
    def save_memory(self, content: str, type: str = "default"):
        """快捷方法：保存记忆"""
        self.memory.save(content, type)
    
    def call_llm(self, prompt: str | list) -> str:
        """快捷方法：调用 LLM"""
        return self.llm.invoke(prompt)
