"""
内容资产管理路由

支持角色卡、预设、世界观、正则脚本等内容的 CRUD 操作
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from ..deps import get_runtime
from ..schemas import SuccessResponse
from core import Runtime

router = APIRouter(prefix="/contents", tags=["contents"])


# ============================================================
# 请求/响应模型
# ============================================================

class ContentCreate(BaseModel):
    """创建/更新内容请求"""
    id: str = Field(description="内容唯一标识")
    data: dict = Field(description="内容数据")
    scope: str = Field(default="global", description="作用域")
    tags: Optional[list[str]] = Field(default=None, description="标签列表")


class ContentResponse(BaseModel):
    """内容响应"""
    id: str
    type: str
    data: dict
    scope: str
    tags: Optional[list[str]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ContentListResponse(BaseModel):
    """内容列表响应"""
    items: list[ContentResponse]
    total: int
    type: str


# ============================================================
# 内容类型定义
# ============================================================

CONTENT_TYPES = {
    "character": {
        "name": "角色卡",
        "description": "角色扮演的角色定义",
        "schema_hint": {
            "name": "角色名称",
            "personality": "性格特点",
            "scenario": "场景设定",
            "first_message": "开场白",
            "description": "角色描述",
        }
    },
    "preset": {
        "name": "预设",
        "description": "系统提示词预设",
        "schema_hint": {
            "name": "预设名称",
            "system_prompt": "系统提示词",
            "jailbreak": "越狱提示（可选）",
        }
    },
    "world_info": {
        "name": "世界观",
        "description": "世界观/知识库条目",
        "schema_hint": {
            "name": "实体名称（用于唯一标识和去重）",
            "key": "触发关键词1,关键词2,关键词3",
            "content": "条目内容",
            "comment": "类型标注（如 人物-主角）",
            "priority": 0,
            "enabled": True,
        }
    },
    "regex": {
        "name": "正则脚本",
        "description": "文本替换正则表达式",
        "schema_hint": {
            "name": "脚本名称",
            "find_regex": "查找正则",
            "replace_string": "替换字符串",
            "flags": "gi",
            "enabled": True,
            "priority": 0,
        }
    },
}


# ============================================================
# API 端点
# ============================================================

@router.get("/types")
async def list_content_types():
    """列出支持的内容类型"""
    return {
        "types": [
            {
                "type": key,
                "name": value["name"],
                "description": value["description"],
                "schema_hint": value["schema_hint"],
            }
            for key, value in CONTENT_TYPES.items()
        ]
    }


@router.get("/{content_type}", response_model=ContentListResponse)
async def list_contents(
    content_type: str,
    scope: str = Query(default="global", description="作用域"),
    tags: Optional[str] = Query(default=None, description="标签筛选（逗号分隔）"),
    runtime: Runtime = Depends(get_runtime),
):
    """列出指定类型的所有内容"""
    if content_type not in CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的内容类型: {content_type}")
    
    tag_list = tags.split(",") if tags else None
    items = runtime.contents.list(content_type, scope=scope, tags=tag_list)
    
    return ContentListResponse(
        items=[
            ContentResponse(
                id=item["id"],
                type=item["type"],
                data=item["data"],
                scope=item.get("scope", "global"),
                tags=item.get("tags"),
                created_at=str(item.get("created_at")) if item.get("created_at") else None,
                updated_at=str(item.get("updated_at")) if item.get("updated_at") else None,
            )
            for item in items
        ],
        total=len(items),
        type=content_type,
    )


@router.get("/{content_type}/{content_id}", response_model=ContentResponse)
async def get_content(
    content_type: str,
    content_id: str,
    scope: str = Query(default="global"),
    runtime: Runtime = Depends(get_runtime),
):
    """获取单个内容"""
    if content_type not in CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的内容类型: {content_type}")
    
    item = runtime.contents.get(content_type, content_id, scope=scope)
    if not item:
        raise HTTPException(status_code=404, detail="内容不存在")
    
    return ContentResponse(
        id=item["id"],
        type=item["type"],
        data=item["data"],
        scope=item.get("scope", "global"),
        tags=item.get("tags"),
        created_at=str(item.get("created_at")) if item.get("created_at") else None,
        updated_at=str(item.get("updated_at")) if item.get("updated_at") else None,
    )


@router.post("/{content_type}", response_model=ContentResponse)
async def create_content(
    content_type: str,
    data: ContentCreate,
    runtime: Runtime = Depends(get_runtime),
):
    """创建或更新内容（Upsert）"""
    if content_type not in CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的内容类型: {content_type}")
    
    runtime.contents.save(
        type=content_type,
        id=data.id,
        data=data.data,
        scope=data.scope,
        tags=data.tags,
    )
    
    # 重新获取保存后的数据
    item = runtime.contents.get(content_type, data.id, scope=data.scope)
    
    return ContentResponse(
        id=item["id"],
        type=item["type"],
        data=item["data"],
        scope=item.get("scope", "global"),
        tags=item.get("tags"),
        created_at=str(item.get("created_at")) if item.get("created_at") else None,
        updated_at=str(item.get("updated_at")) if item.get("updated_at") else None,
    )


@router.put("/{content_type}/{content_id}", response_model=ContentResponse)
async def update_content(
    content_type: str,
    content_id: str,
    data: ContentCreate,
    runtime: Runtime = Depends(get_runtime),
):
    """更新内容"""
    if content_type not in CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的内容类型: {content_type}")
    
    # 检查是否存在
    existing = runtime.contents.get(content_type, content_id, scope=data.scope)
    if not existing:
        raise HTTPException(status_code=404, detail="内容不存在")
    
    runtime.contents.save(
        type=content_type,
        id=content_id,
        data=data.data,
        scope=data.scope,
        tags=data.tags,
    )
    
    item = runtime.contents.get(content_type, content_id, scope=data.scope)
    
    return ContentResponse(
        id=item["id"],
        type=item["type"],
        data=item["data"],
        scope=item.get("scope", "global"),
        tags=item.get("tags"),
        created_at=str(item.get("created_at")) if item.get("created_at") else None,
        updated_at=str(item.get("updated_at")) if item.get("updated_at") else None,
    )


@router.delete("/{content_type}/{content_id}", response_model=SuccessResponse)
async def delete_content(
    content_type: str,
    content_id: str,
    scope: str = Query(default="global"),
    runtime: Runtime = Depends(get_runtime),
):
    """删除内容"""
    if content_type not in CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的内容类型: {content_type}")
    
    success = runtime.contents.delete(content_type, content_id, scope=scope)
    if not success:
        raise HTTPException(status_code=404, detail="内容不存在")
    
    return SuccessResponse(message=f"{CONTENT_TYPES[content_type]['name']} {content_id} 已删除")


@router.get("/{content_type}/search/{keyword}")
async def search_contents(
    content_type: str,
    keyword: str,
    scope: str = Query(default="global"),
    runtime: Runtime = Depends(get_runtime),
):
    """搜索内容"""
    if content_type not in CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的内容类型: {content_type}")
    
    items = runtime.contents.search(content_type, keyword, scope=scope)
    
    return {
        "items": [
            ContentResponse(
                id=item["id"],
                type=item["type"],
                data=item["data"],
                scope=item.get("scope", "global"),
                tags=item.get("tags"),
            )
            for item in items
        ],
        "total": len(items),
        "keyword": keyword,
    }
