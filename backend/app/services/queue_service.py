"""
Serviço de gerenciamento da fila de tarefas concorrentes (QUEUED).
Impede o esgotamento de recursos do sistema e limites de tokens ao limitar
o número de execuções simultâneas ao configurado em MAX_CONCURRENT_TASKS.
"""
from typing import Optional
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.task import Task, TaskStatus


class QueueService:
    def __init__(self):
        pass

    def count_running(self, db: Session) -> int:
        return db.query(Task).filter(Task.status == TaskStatus.RUNNING).count()

    def can_run_now(self, db: Session, max_concurrent: Optional[int] = None) -> bool:
        limite = max_concurrent if max_concurrent is not None else settings.MAX_CONCURRENT_TASKS
        return self.count_running(db) < limite

    def enqueue(self, task: Task, db: Session) -> None:
        task.status = TaskStatus.QUEUED
        db.commit()
        db.refresh(task)

    def get_next_queued(self, db: Session) -> Optional[Task]:
        return (
            db.query(Task)
            .filter(Task.status == TaskStatus.QUEUED)
            .order_by(Task.created_at.asc(), Task.id.asc())
            .first()
        )


queue_service = QueueService()
