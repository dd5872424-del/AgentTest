"""
Pydantic 模型：请求/响应数据结构
"""
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field


# ============================================================
# 会话相关
# ============================================================

class ConversationCreate(BaseModel):
    """创建会话请求"""
    graph_name: str = Field(default="default", description="图名称")
    title: Optional[str] = Field(default=None, description="会话标题")
    content_refs: Optional[dict] = Field(default=None, description="内容引用")


class ConversationResponse(BaseModel):
    """会话响应"""
    id: str
    title: str
    graph_name: str
    thread_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    content_refs: Optional[dict] = None


class ConversationListResponse(BaseModel):
    """会话列表响应"""
    conversations: list[ConversationResponse]
    total: int


# ============================================================
# 消息相关
# ============================================================

class Message(BaseModel):
    """消息"""
    role: str = Field(description="角色: user/assistant")
    content: str = Field(description="消息内容")


class MessageListResponse(BaseModel):
    """消息列表响应"""
    messages: list[Message]
    total: int


class MessageEdit(BaseModel):
    """编辑消息请求"""
    content: str = Field(description="新的消息内容")


# ============================================================
# 聊天相关
# ============================================================

class ChatRequest(BaseModel):
    """发送消息请求"""
    message: str = Field(description="用户消息")


class ChatResponse(BaseModel):
    """聊天响应（非流式）"""
    output: str = Field(description="AI 回复")
    mood: Optional[str] = Field(default=None, description="角色情绪")
    inner_thought: Optional[str] = Field(default=None, description="角色内心想法")


# ============================================================
# 状态相关
# ============================================================

class StateResponse(BaseModel):
    """状态响应"""
    state: dict = Field(description="完整状态")


class StateEditRequest(BaseModel):
    """编辑状态请求"""
    updates: dict = Field(description="要更新的字段")


# ============================================================
# 通用
# ============================================================

class SuccessResponse(BaseModel):
    """成功响应"""
    success: bool = True
    message: str = "操作成功"


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: str
    detail: Optional[str] = None
