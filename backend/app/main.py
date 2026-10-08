from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.api.projects import router as projects_router
from app.api.tasks import router as tasks_router
from app.websockets.manager import ws_manager

init_db()

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Agent Orchestrator Local Engine"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)
app.include_router(tasks_router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME}


@app.websocket("/ws/tasks/{task_id}")
async def websocket_task_endpoint(websocket: WebSocket, task_id: str):
    await ws_manager.connect_task(task_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Opcional: receber comandos interativos do cliente
    except WebSocketDisconnect:
        ws_manager.disconnect_task(task_id, websocket)


@app.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    await ws_manager.connect_dashboard(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect_dashboard(websocket)
