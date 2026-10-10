"""
Abrir um terminal na pasta do projeto (ou no worktree da tarefa).
O disparo real é mockado — pytest não deve abrir janelas.
"""
import os
import tempfile
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.main import app
from app.core.database import SessionLocal
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.services.terminal_service import TerminalService

client = TestClient(app)

PREFIXO = "__pytest_term__"


@pytest.fixture(autouse=True)
def limpar():
    def _purgar():
        db = SessionLocal()
        for p in db.query(Project).filter(Project.name.like(f"{PREFIXO}%")).all():
            for t in db.query(Task).filter(Task.project_id == p.id).all():
                db.delete(t)
            db.delete(p)
        db.commit()
        db.close()
    _purgar()
    yield
    _purgar()


def _projeto(root_path):
    db = SessionLocal()
    p = Project(name=f"{PREFIXO} Proj", root_path=root_path)
    db.add(p)
    db.commit()
    db.refresh(p)
    pid = p.id
    db.close()
    return pid


def test_prefere_windows_terminal_quando_disponivel():
    svc = TerminalService()
    with patch("shutil.which", side_effect=lambda n: "C:/fake/wt.exe" if n == "wt" else None):
        cmd = svc.build_command("C:/projetos/meu-projeto")
    assert cmd[0] == "C:/fake/wt.exe"
    assert "C:/projetos/meu-projeto" in cmd


def test_cai_para_powershell_sem_windows_terminal():
    svc = TerminalService()
    with patch("shutil.which", side_effect=lambda n: "C:/fake/pwsh.exe" if n == "pwsh" else None):
        cmd = svc.build_command("C:/projetos/meu-projeto")
    assert "pwsh" in cmd[0]
    assert "C:/projetos/meu-projeto" in cmd


def test_sem_nenhum_terminal_disponivel_falha_explicito():
    svc = TerminalService()
    with patch("shutil.which", return_value=None):
        with pytest.raises(RuntimeError):
            svc.build_command("C:/projetos/meu-projeto")


def test_abrir_terminal_do_projeto():
    with tempfile.TemporaryDirectory() as pasta:
        pid = _projeto(pasta)
        with patch("app.services.terminal_service.subprocess.Popen") as mock_popen:
            resp = client.post(f"/api/projects/{pid}/terminal")
        assert resp.status_code == 200
        assert resp.json()["opened_at"] == pasta
        mock_popen.assert_called_once()


def test_pasta_inexistente_devolve_erro_claro():
    pid = _projeto("C:/caminho/que/nao/existe/mesmo")
    with patch("app.services.terminal_service.subprocess.Popen") as mock_popen:
        resp = client.post(f"/api/projects/{pid}/terminal")
    assert resp.status_code == 400
    assert "não encontrada" in resp.json()["detail"].lower()
    mock_popen.assert_not_called()


def test_projeto_inexistente_devolve_404():
    resp = client.post("/api/projects/nao-existe/terminal")
    assert resp.status_code == 404


def test_terminal_da_tarefa_abre_no_worktree():
    with tempfile.TemporaryDirectory() as pasta:
        worktree = os.path.join(pasta, "wt-da-tarefa")
        os.makedirs(worktree)
        pid = _projeto(pasta)

        db = SessionLocal()
        t = Task(project_id=pid, title="T", raw_prompt="p",
                 status=TaskStatus.RUNNING, worktree_path=worktree)
        db.add(t)
        db.commit()
        db.refresh(t)
        tid = t.id
        db.close()

        with patch("app.services.terminal_service.subprocess.Popen") as mock_popen:
            resp = client.post(f"/api/tasks/{tid}/terminal")
        assert resp.status_code == 200
        assert resp.json()["opened_at"] == worktree
        mock_popen.assert_called_once()


def test_tarefa_sem_worktree_cai_na_pasta_do_projeto():
    """Tarefa ainda não executada não tem worktree — abrir no projeto é mais útil que falhar."""
    with tempfile.TemporaryDirectory() as pasta:
        pid = _projeto(pasta)
        db = SessionLocal()
        t = Task(project_id=pid, title="T", raw_prompt="p", status=TaskStatus.DRAFT)
        db.add(t)
        db.commit()
        db.refresh(t)
        tid = t.id
        db.close()

        with patch("app.services.terminal_service.subprocess.Popen") as mock_popen:
            resp = client.post(f"/api/tasks/{tid}/terminal")
        assert resp.status_code == 200
        assert resp.json()["opened_at"] == pasta
        mock_popen.assert_called_once()
