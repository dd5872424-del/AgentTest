"""
聊天路由：发送消息、流式响应、重新生成
"""
import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Depends
from sse_starlette.sse import EventSourceResponse

from ..deps import get_runtime
from ..schemas import (
    ChatRequest,
    ChatResponse,
    MessageListResponse,
    Message,
    MessageEdit,
    SuccessResponse,
)
from core import Runtime

router = APIRouter(prefix="/conversations/{conversation_id}", tags=["chat"])


@router.get("/messages", response_model=MessageListResponse)
async def get_messages(
    conversation_id: str,
    runtime: Runtime = Depends(get_runtime),
):
    """获取消息历史"""
    conv = runtime.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    messages = runtime.get_history(conversation_id)
    return MessageListResponse(
        messages=[
            Message(role=m.get("role", ""), content=m.get("content", ""))
            for m in messages
        ],
        total=len(messages),
    )


@router.post("/chat")
async def chat(
    conversation_id: str,
    data: ChatRequest,
    runtime: Runtime = Depends(get_runtime),
):
    """
    发送消息（SSE 流式响应）
    
    返回 Server-Sent Events 流，格式：
    - data: {"type": "chunk", "content": "..."} - 内容片段
    - data: {"type": "done", "output": "...", "mood": "...", "thought": "..."} - 完成
    - data: {"type": "error", "error": "..."} - 错误
    """
    conv = runtime.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    async def generate() -> AsyncGenerator[str, None]:
        chunks = []
        
        def stream_callback(chunk: str):
            chunks.append(chunk)
        
        try:
            # 在线程池中运行同步代码
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: runtime.run(conversation_id, data.message, stream_callback=stream_callback)
            )
            
            # 逐个发送收集到的 chunks
            for chunk in chunks:
                yield json.dumps({"type": "chunk", "content": chunk}, ensure_ascii=False)
                await asyncio.sleep(0)  # 让出控制权
            
            # 发送完成信号
            yield json.dumps({
                "type": "done",
                "output": result.get("last_output", ""),
                "mood": result.get("mood"),
                "thought": result.get("inner_thought"),
            }, ensure_ascii=False)
            
        except Exception as e:
            yield json.dumps({"type": "error", "error": str(e)}, ensure_ascii=False)
    
    return EventSourceResponse(generate())


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(
    conversation_id: str,
    data: ChatRequest,
    runtime: Runtime = Depends(get_runtime),
):
    """发送消息（非流式，等待完整响应）"""
    conv = runtime.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: runtime.run(conversation_id, data.message)
        )
        
        return ChatResponse(
            output=result.get("last_output", ""),
            mood=result.get("mood"),
            inner_thought=result.get("inner_thought"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regenerate")
async def regenerate(
    conversation_id: str,
    runtime: Runtime = Depends(get_runtime),
):
    """
    重新生成最后一条回复（SSE 流式响应）
    """
    conv = runtime.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    async def generate() -> AsyncGenerator[str, None]:
        chunks = []
        
        def stream_callback(chunk: str):
            chunks.append(chunk)
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: runtime.regenerate(conversation_id, stream_callback=stream_callback)
            )
            
            for chunk in chunks:
                yield json.dumps({"type": "chunk", "content": chunk}, ensure_ascii=False)
                await asyncio.sleep(0)
            
            yield json.dumps({
                "type": "done",
                "output": result.get("last_output", ""),
                "mood": result.get("mood"),
                "thought": result.get("inner_thought"),
            }, ensure_ascii=False)
            
        except Exception as e:
            yield json.dumps({"type": "error", "error": str(e)}, ensure_ascii=False)
    
    return EventSourceResponse(generate())


@router.put("/messages/{message_index}", response_model=SuccessResponse)
async def edit_message(
    conversation_id: str,
    message_index: int,
    data: MessageEdit,
    runtime: Runtime = Depends(get_runtime),
):
    """编辑指定消息"""
    conv = runtime.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    success = runtime.edit_message(conversation_id, message_index, data.content)
    if not success:
        raise HTTPException(status_code=400, detail="编辑失败，消息索引无效")
    
    return SuccessResponse(message=f"消息 {message_index} 已更新")


@router.delete("/messages/{message_index}", response_model=SuccessResponse)
async def delete_message(
    conversation_id: str,
    message_index: int,
    runtime: Runtime = Depends(get_runtime),
):
    """删除指定消息"""
    conv = runtime.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    success = runtime.delete_message(conversation_id, message_index)
    if not success:
        raise HTTPException(status_code=400, detail="删除失败，消息索引无效")
    
    return SuccessResponse(message=f"消息 {message_index} 已删除")
