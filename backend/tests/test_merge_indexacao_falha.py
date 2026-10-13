"""
Falha ao indexar artefatos não pode derrubar um merge já feito.

O `except` em merge_task existe justamente para isso: indexar é conveniência,
o merge é o trabalho. Mas o handler chamava `logging.getLogger(...)` sem que
`logging` estivesse importado no módulo. O NameError escapava do except DEPOIS
do merge ter acontecido e ANTES de remove_worktree() e status = DONE — a tarefa
ficava mergeada mas não concluída, com a worktree órfã no disco.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.task import Task, TaskStatus


@pytest.fixture
def ambiente(tmp_path):
    """Devolve (client, Session) para o teste poder ajustar a tarefa no banco."""
    db_file = tmp_path / "test_merge_indexacao.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, Session
    app.dependency_overrides.clear()


def _tarefa_pronta_para_merge(client, Session, tmp_path):
    """Cria projeto e tarefa, e grava um worktree_path — sem ele nem se indexa."""
    proj_dir = tmp_path / "projeto-merge"
    proj_dir.mkdir(exist_ok=True)

    r = client.post("/api/projects", json={
        "name": "Projeto Merge", "root_path": str(proj_dir), "default_branch": "main"
    })
    assert r.status_code == 201
    proj_id = r.json()["id"]

    r = client.post("/api/tasks", json={
        "project_id": proj_id, "title": "Tarefa a mergear", "raw_prompt": "faça X"
    })
    assert r.status_code == 201
    task_id = r.json()["id"]

    worktree = tmp_path / "worktree"
    worktree.mkdir(exist_ok=True)
    session = Session()
    tarefa = session.query(Task).filter(Task.id == task_id).first()
    tarefa.worktree_path = str(worktree)
    tarefa.status = TaskStatus.REVIEW_READY
    session.commit()
    session.close()

    return task_id


def test_falha_ao_indexar_nao_derruba_o_merge(ambiente, tmp_path):
    """O merge já aconteceu: engolir o erro de indexação é o comportamento certo."""
    client, Session = ambiente
    task_id = _tarefa_pronta_para_merge(client, Session, tmp_path)

    with patch("app.api.tasks.artifact_service.listar", return_value=[{"name": "mapa.md"}]), \
         patch("app.api.tasks.artifact_service.registrar_no_indice",
               side_effect=RuntimeError("disco cheio")), \
         patch("app.api.tasks.git_service.merge_task", return_value=True), \
         patch("app.api.tasks.git_service.remove_worktree", return_value=True) as remove:
        r = client.post(f"/api/tasks/{task_id}/merge")

    assert r.status_code == 200, (
        f"o merge já tinha acontecido, mas a resposta virou {r.status_code} "
        f"por causa da indexação: {r.text[:300]}"
    )
    assert r.json()["status"] == "DONE"
    # O que vem DEPOIS do except precisa ter rodado.
    assert r.json()["artifacts_indexed"] == [], "não indexou nada, não pode dizer que indexou"
    remove.assert_called_once()

    session = Session()
    assert session.query(Task).filter(Task.id == task_id).first().status == TaskStatus.DONE
    session.close()


def test_indexacao_bem_sucedida_reporta_os_artefatos(ambiente, tmp_path):
    """O caminho feliz continua reportando o que entrou no índice."""
    client, Session = ambiente
    task_id = _tarefa_pronta_para_merge(client, Session, tmp_path)

    with patch("app.api.tasks.artifact_service.listar", return_value=[{"name": "mapa.md"}]), \
         patch("app.api.tasks.artifact_service.registrar_no_indice", return_value=None), \
         patch("app.api.tasks.git_service.merge_task", return_value=True), \
         patch("app.api.tasks.git_service.remove_worktree", return_value=True):
        r = client.post(f"/api/tasks/{task_id}/merge")

    assert r.status_code == 200
    assert r.json()["artifacts_indexed"] == ["mapa.md"]
