"""
FastAPI 应用入口

启动命令：
    cd backend
    uvicorn api.main:app --reload --port 8000

访问：
    API 文档: http://localhost:8000/docs
    前端界面: http://localhost:8000/
"""
import sys
from pathlib import Path

# 确保 backend 目录在 Python 路径中
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .routes import conversations_router, chat_router, state_router, contents_router


# 创建应用
app = FastAPI(
    title="AgentTest API",
    description="LangGraph 聊天框架 API",
    version="1.0.0",
)

# CORS 配置（开发阶段允许所有来源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(conversations_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(state_router, prefix="/api")
app.include_router(contents_router, prefix="/api")


# 静态文件服务（前端）
web_dir = Path(__file__).parent.parent.parent / "web"
if web_dir.exists():
    # 挂载静态资源
    app.mount("/css", StaticFiles(directory=web_dir / "css"), name="css")
    app.mount("/js", StaticFiles(directory=web_dir / "js"), name="js")
    
    @app.get("/")
    async def serve_index():
        """提供前端首页"""
        return FileResponse(web_dir / "index.html")
    
    @app.get("/config.js")
    async def serve_config():
        """提供前端配置"""
        return FileResponse(web_dir / "config.js")


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "AgentTest API"}


@app.get("/api/graphs")
async def list_graphs():
    """列出可用的图"""
    return {
        "graphs": [
            {"name": "default", "description": "默认对话"},
            {"name": "roleplay", "description": "角色扮演"},
            {"name": "with_commands", "description": "带指令解析"},
        ]
    }
