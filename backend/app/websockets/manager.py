from typing import Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    """
    Roteador de conexões WebSocket.
    Garante que eventos e logs de uma tarefa sejam transmitidos EXCLUSIVAMENTE
    para as conexões que estão com aquela tarefa aberta, eliminando a colisão de mensagens.
    """

    def __init__(self):
        # task_id -> set of WebSocket connections
        self.task_subscribers: Dict[str, Set[WebSocket]] = {}
        # global dashboard subscribers
        self.dashboard_subscribers: Set[WebSocket] = set()

    async def connect_task(self, task_id: str, websocket: WebSocket):
        await websocket.accept()
        if task_id not in self.task_subscribers:
            self.task_subscribers[task_id] = set()
        self.task_subscribers[task_id].add(websocket)

    def disconnect_task(self, task_id: str, websocket: WebSocket):
        if task_id in self.task_subscribers:
            self.task_subscribers[task_id].discard(websocket)
            if not self.task_subscribers[task_id]:
                del self.task_subscribers[task_id]

    async def connect_dashboard(self, websocket: WebSocket):
        await websocket.accept()
        self.dashboard_subscribers.add(websocket)

    def disconnect_dashboard(self, websocket: WebSocket):
        self.dashboard_subscribers.discard(websocket)

    async def broadcast_task(self, task_id: str, message: dict):
        subscribers = self.task_subscribers.get(task_id, set())
        for ws in list(subscribers):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect_task(task_id, ws)

    async def broadcast_dashboard(self, message: dict):
        for ws in list(self.dashboard_subscribers):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect_dashboard(ws)


ws_manager = ConnectionManager()
