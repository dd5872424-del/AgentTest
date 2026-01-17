"""
会话管理路由
"""
from fastapi import APIRouter, HTTPException, Depends

from ..deps import get_runtime
from ..schemas import (
    ConversationCreate,
    ConversationResponse,
    ConversationListResponse,
    SuccessResponse,
)
from core import Runtime

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(runtime: Runtime = Depends(get_runtime)):
    """列出所有会话"""
    conversations = runtime.list_conversations()
    return ConversationListResponse(
        conversations=[
            ConversationResponse(
                id=c["id"],
                title=c.get("title", ""),
                graph_name=c.get("graph_name", ""),
                thread_id=c.get("thread_id", ""),
                created_at=c.get("created_at"),
                updated_at=c.get("updated_at"),
                content_refs=c.get("content_refs"),
            )
            for c in conversations
        ],
        total=len(conversations),
    )


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreate,
    runtime: Runtime = Depends(get_runtime),
):
    """创建新会话"""
    conv_id = runtime.create_conversation(
        graph_name=data.graph_name,
        title=data.title,
        content_refs=data.content_refs,
    )
    conv = runtime.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=500, detail="创建会话失败")
    
    return ConversationResponse(
        id=conv["id"],
        title=conv.get("title", ""),
        graph_name=conv.get("graph_name", ""),
        thread_id=conv.get("thread_id", ""),
        created_at=conv.get("created_at"),
        updated_at=conv.get("updated_at"),
        content_refs=conv.get("content_refs"),
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    runtime: Runtime = Depends(get_runtime),
):
    """获取会话详情"""
    conv = runtime.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return ConversationResponse(
        id=conv["id"],
        title=conv.get("title", ""),
        graph_name=conv.get("graph_name", ""),
        thread_id=conv.get("thread_id", ""),
        created_at=conv.get("created_at"),
        updated_at=conv.get("updated_at"),
        content_refs=conv.get("content_refs"),
    )


@router.delete("/{conversation_id}", response_model=SuccessResponse)
async def delete_conversation(
    conversation_id: str,
    runtime: Runtime = Depends(get_runtime),
):
    """删除会话"""
    success = runtime.delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return SuccessResponse(message=f"会话 {conversation_id} 已删除")


@router.delete("", response_model=SuccessResponse)
async def clear_all_conversations(runtime: Runtime = Depends(get_runtime)):
    """清空所有会话"""
    count = runtime.clear_all_conversations()
    return SuccessResponse(message=f"已删除 {count} 个会话")
