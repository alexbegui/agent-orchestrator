import os
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.api.projects import router as projects_router
from app.api.tasks import router as tasks_router
from app.api.settings import router as settings_router
from app.websockets.manager import ws_manager

init_db()


def _reconciliar_execucoes():
    """
    Descobre o que aconteceu com as tarefas que ficaram marcadas como RUNNING.

    Como os agentes agora são desacoplados, reiniciar o servidor não os mata —
    mas o orquestrador precisa reencontrá-los para não mostrar estado falso.
    """
    from app.core.database import SessionLocal
    from app.models.task import Task, TaskStatus
    from app.services.runner_service import RunnerService

    runner = RunnerService()

    db = SessionLocal()
    try:
        pendentes = db.query(Task).filter(Task.status == TaskStatus.RUNNING).all()
        for t in pendentes:
            if not t.worktree_path:
                continue
            novo = runner.reconcile(t.worktree_path)
            if novo and novo != "RUNNING":
                t.status = TaskStatus(novo)
                logging.getLogger("orchestrator").info(
                    f"Tarefa {t.id} reconciliada: RUNNING -> {novo}"
                )
        db.commit()
    except Exception as e:
        logging.getLogger("orchestrator").warning(f"Falha ao reconciliar execuções: {e}")
    finally:
        db.close()


_reconciliar_execucoes()

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
app.include_router(settings_router)


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


# Servir Uploads de Anexos
uploads_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Servir Mockups de protótipos
mockups_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "mockups"))
if os.path.exists(mockups_dir):
    app.mount("/mockups", StaticFiles(directory=mockups_dir, html=True), name="mockups")

# Servir Frontend Estático compilado se existir
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

