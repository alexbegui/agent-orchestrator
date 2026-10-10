"""
"Esperando você" é derivado, não um status novo no banco:
a bola está com o usuário quando o agente falou por último e a tarefa
não acabou, ou quando há diff para revisar / falha para tratar.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.task import Task, TaskStatus
from app.models.message import Message, MessageRole
from app.models.project import Project

client = TestClient(app)

PREFIXO = "__pytest__"


@pytest.fixture(autouse=True)
def limpar_dados_de_teste():
    """
    Estes testes gravam no banco real. Sem limpeza, o painel do usuário
    enche de lixo. Remove tudo que este módulo criou, antes e depois.
    """
    def _purgar():
        db = SessionLocal()
        projs = db.query(Project).filter(Project.name.like(f"{PREFIXO}%")).all()
        for p in projs:
            for t in db.query(Task).filter(Task.project_id == p.id).all():
                db.query(Message).filter(Message.task_id == t.id).delete()
                db.delete(t)
            db.delete(p)
        db.commit()
        db.close()

    _purgar()
    yield
    _purgar()


def _criar_tarefa(status=TaskStatus.RUNNING):
    db = SessionLocal()
    proj = Project(name=f"{PREFIXO} Proj", root_path="C:/tmp/proj-teste")
    db.add(proj)
    db.commit()
    db.refresh(proj)

    task = Task(project_id=proj.id, title="T", raw_prompt="faça algo", status=status)
    db.add(task)
    db.commit()
    db.refresh(task)
    ids = (proj.id, task.id)
    db.close()
    return ids


def _add_msg(task_id, role):
    db = SessionLocal()
    db.add(Message(task_id=task_id, role=role, content="msg"))
    db.commit()
    db.close()


def test_agente_falou_por_ultimo_entao_esta_esperando_voce():
    proj_id, task_id = _criar_tarefa()
    _add_msg(task_id, MessageRole.USER)
    _add_msg(task_id, MessageRole.ASSISTANT)

    tasks = client.get(f"/api/tasks/project/{proj_id}").json()
    alvo = next(t for t in tasks if t["id"] == task_id)
    assert alvo["awaiting_you"] is True


def test_voce_falou_por_ultimo_entao_a_bola_e_do_agente():
    proj_id, task_id = _criar_tarefa()
    _add_msg(task_id, MessageRole.ASSISTANT)
    _add_msg(task_id, MessageRole.USER)

    tasks = client.get(f"/api/tasks/project/{proj_id}").json()
    alvo = next(t for t in tasks if t["id"] == task_id)
    assert alvo["awaiting_you"] is False


def test_diff_pronto_esta_esperando_voce_mesmo_sem_conversa():
    proj_id, task_id = _criar_tarefa(status=TaskStatus.REVIEW_READY)

    tasks = client.get(f"/api/tasks/project/{proj_id}").json()
    alvo = next(t for t in tasks if t["id"] == task_id)
    assert alvo["awaiting_you"] is True


def test_tarefa_concluida_nunca_espera_voce():
    proj_id, task_id = _criar_tarefa(status=TaskStatus.DONE)
    _add_msg(task_id, MessageRole.ASSISTANT)

    tasks = client.get(f"/api/tasks/project/{proj_id}").json()
    alvo = next(t for t in tasks if t["id"] == task_id)
    assert alvo["awaiting_you"] is False


def test_listar_todas_as_tarefas_de_todos_os_projetos():
    _criar_tarefa()
    _criar_tarefa()

    resp = client.get("/api/tasks/all")
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) >= 2
    assert all("awaiting_you" in t for t in tasks)
    assert all("project_name" in t for t in tasks)
