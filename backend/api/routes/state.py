"""
状态管理路由
"""
from fastapi import APIRouter, HTTPException, Depends

from ..deps import get_runtime
from ..schemas import StateResponse, StateEditRequest, SuccessResponse
from core import Runtime

router = APIRouter(prefix="/conversations/{conversation_id}", tags=["state"])


@router.get("/state", response_model=StateResponse)
async def get_state(
    conversation_id: str,
    runtime: Runtime = Depends(get_runtime),
):
    """获取完整状态"""
    conv = runtime.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    state = runtime.get_state(conversation_id)
    if state is None:
        return StateResponse(state={})
    
    return StateResponse(state=state)


@router.put("/state", response_model=SuccessResponse)
async def edit_state(
    conversation_id: str,
    data: StateEditRequest,
    runtime: Runtime = Depends(get_runtime),
):
    """编辑状态字段"""
    conv = runtime.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    success = runtime.edit_state(conversation_id, data.updates)
    if not success:
        raise HTTPException(status_code=400, detail="编辑失败")
    
    return SuccessResponse(message="状态已更新")


@router.get("/state/history")
async def get_state_history(
    conversation_id: str,
    limit: int = 10,
    runtime: Runtime = Depends(get_runtime),
):
    """获取状态快照历史"""
    conv = runtime.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    history = runtime.get_state_history(conversation_id, limit=limit)
    return {"history": history, "total": len(history)}


@router.post("/state/rollback/{checkpoint_id}", response_model=StateResponse)
async def rollback_state(
    conversation_id: str,
    checkpoint_id: str,
    runtime: Runtime = Depends(get_runtime),
):
    """回滚到指定快照"""
    conv = runtime.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    state = runtime.rollback_to(conversation_id, checkpoint_id)
    return StateResponse(state=state)
