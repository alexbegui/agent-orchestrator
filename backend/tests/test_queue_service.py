"""
Testes para o QueueService e controle de concorrência com TaskStatus.QUEUED.
Garante que tarefas além de MAX_CONCURRENT_TASKS entrem na fila (QUEUED) e sejam
despachadas ordenadamente quando vagas abrirem.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.project import Project
from app.models.task import Task, TaskStatus, RunnerType
from app.models.message import Message
from app.services.queue_service import QueueService


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "test_queue.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()
    try:
        p = Project(id="p1", name="Proj", root_path=str(tmp_path), default_branch="main")
        session.add(p)
        session.commit()
        yield session
    finally:
        session.close()


def test_can_run_now_respeita_limite(db_session):
    qs = QueueService()
    # Limite configurado como 2
    assert qs.can_run_now(db_session, max_concurrent=2) is True

    # Adiciona 1 rodando
    t1 = Task(id="t1", project_id="p1", title="T1", raw_prompt="...", status=TaskStatus.RUNNING)
    db_session.add(t1)
    db_session.commit()
    assert qs.can_run_now(db_session, max_concurrent=2) is True

    # Adiciona 2 rodando (atinge limite)
    t2 = Task(id="t2", project_id="p1", title="T2", raw_prompt="...", status=TaskStatus.RUNNING)
    db_session.add(t2)
    db_session.commit()
    assert qs.can_run_now(db_session, max_concurrent=2) is False


def test_enqueue_e_get_next_queued_em_ordem_fifo(db_session):
    qs = QueueService()
    t1 = Task(id="t1", project_id="p1", title="T1", raw_prompt="...", status=TaskStatus.DRAFT)
    t2 = Task(id="t2", project_id="p1", title="T2", raw_prompt="...", status=TaskStatus.DRAFT)
    db_session.add_all([t1, t2])
    db_session.commit()

    qs.enqueue(t1, db_session)
    assert t1.status == TaskStatus.QUEUED

    qs.enqueue(t2, db_session)
    assert t2.status == TaskStatus.QUEUED

    proxima = qs.get_next_queued(db_session)
    assert proxima is not None
    assert proxima.id == "t1"  # FIFO


def test_api_run_task_enfileira_quando_limite_atingido(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.database import get_db

    db_file = tmp_path / "test_api_queue.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            proj_dir = tmp_path / "proj_q"
            proj_dir.mkdir()
            p_resp = client.post("/api/projects", json={
                "name": "PQ", "root_path": str(proj_dir), "default_branch": "main"
            })
            proj_id = p_resp.json()["id"]

            # Cria 2 tarefas
            t1_resp = client.post("/api/tasks", json={
                "project_id": proj_id, "title": "T1", "raw_prompt": "run 1"
            })
            t1_id = t1_resp.json()["id"]

            t2_resp = client.post("/api/tasks", json={
                "project_id": proj_id, "title": "T2", "raw_prompt": "run 2"
            })
            t2_id = t2_resp.json()["id"]

            # Força limite de concorrência = 1 para testar
            from app.core.config import settings
            orig_max = settings.MAX_CONCURRENT_TASKS
            settings.MAX_CONCURRENT_TASKS = 1
            try:
                # Dispara T1
                r1 = client.post(f"/api/tasks/{t1_id}/run")
                assert r1.status_code == 200
                assert r1.json()["status"] == "RUNNING"

                # Dispara T2 (deve ir para QUEUED pois limite é 1)
                r2 = client.post(f"/api/tasks/{t2_id}/run")
                assert r2.status_code == 200
                assert r2.json()["status"] == "QUEUED"
            finally:
                settings.MAX_CONCURRENT_TASKS = orig_max
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_despachar_proxima_da_fila(tmp_path):
    from app.api.tasks import _despachar_proxima_da_fila
    db_file = tmp_path / "test_dispatch.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    s = Session()
    p = Project(id="p_disp", name="Disp", root_path=str(tmp_path), default_branch="main")
    s.add(p)
    t = Task(id="t_queued", project_id="p_disp", title="TQ", raw_prompt="prompt", status=TaskStatus.QUEUED)
    s.add(t)
    s.commit()
    s.close()

    # Despacha a próxima da fila
    await _despachar_proxima_da_fila(Session)

    s2 = Session()
    t_after = s2.query(Task).filter(Task.id == "t_queued").first()
    assert t_after.status == TaskStatus.RUNNING
    s2.close()


