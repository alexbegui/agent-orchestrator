"""
A rota de refino: quando a IA não responde, a tarefa NÃO avança.

Antes a rota sempre devolvia 200 e marcava SPEC_READY, porque o regex nunca
falha. Com IA de verdade a falha existe — e falha silenciosa aqui é a pior
possível: você aprovaria uma spec sem saber que ela não veio da IA.
"""
import json
import subprocess
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.api import tasks as rotas_tarefas
from app.services.assistant_service import MotorIndisponivel


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_refino.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def tarefa(client, tmp_path):
    # Repositório de verdade: a árvore mandada à IA vem de `git ls-files`, e a
    # rota recusa projeto sem git em vez de refinar sobre uma lista vazia.
    projeto = tmp_path / "projeto"
    projeto.mkdir()
    (projeto / "app.py").write_text("print('oi')\n", encoding="utf-8")
    _git("init", cwd=projeto)
    _git("config", "user.email", "teste@teste", cwd=projeto)
    _git("config", "user.name", "Teste", cwd=projeto)
    _git("add", "-A", cwd=projeto)
    _git("commit", "-m", "inicial", cwd=projeto)

    resp = client.post("/api/projects", json={
        "name": "Projeto", "root_path": str(projeto), "default_branch": "main"
    })
    pid = resp.json()["id"]

    resp = client.post("/api/tasks", json={
        "project_id": pid, "title": "Frete", "raw_prompt": "quero calcular frete"
    })
    return resp.json()


SPEC_DA_IA = {
    "objective": "Expor o cálculo de frete como endpoint",
    "steps": ["Escrever o teste", "Criar a rota"],
    "acceptance_criteria": ["POST /frete devolve 200 com o valor"],
    "tests": [{"arquivo": "tests/test_frete.py", "nome": "test_frete", "prova": "que a rota existe"}],
}


def test_refino_bem_sucedido_marca_spec_ready_com_plano_de_testes(client, tarefa, monkeypatch):
    async def refinar_falso(*args, **kwargs):
        from app.services.refiner_service import RefinedSpec
        return RefinedSpec(target_files=["app.py"], **SPEC_DA_IA)

    monkeypatch.setattr(rotas_tarefas.refiner_service, "refinar", refinar_falso)

    resp = client.post(f"/api/tasks/{tarefa['id']}/refine")

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["status"] == "SPEC_READY"
    assert "Plano de Testes" in corpo["refined_spec"]


def test_ia_indisponivel_mantem_a_tarefa_em_draft(client, tarefa, monkeypatch):
    async def recusa(*args, **kwargs):
        raise MotorIndisponivel("Nenhuma chave de API configurada.")

    monkeypatch.setattr(rotas_tarefas.refiner_service, "refinar", recusa)

    resp = client.post(f"/api/tasks/{tarefa['id']}/refine")

    assert resp.status_code == 502
    assert "chave" in resp.json()["detail"].lower()

    # E a tarefa continua onde estava — nada de SPEC_READY sem spec.
    atual = client.get("/api/tasks/all").json()
    minha = next(t for t in atual if t["id"] == tarefa["id"])
    assert minha["status"] == "DRAFT"
    assert not minha["refined_spec"]


def test_motivo_real_da_falha_chega_na_tela(client, tarefa, monkeypatch):
    """Erro genérico manda o usuário adivinhar; o motivo real resolve sozinho."""
    async def recusa(*args, **kwargs):
        raise MotorIndisponivel("A Anthropic devolveu 401: chave inválida.")

    monkeypatch.setattr(rotas_tarefas.refiner_service, "refinar", recusa)

    resp = client.post(f"/api/tasks/{tarefa['id']}/refine")

    assert "401" in resp.json()["detail"]


def test_refino_rota_repassa_target_files_e_fast_mode(client, tarefa, monkeypatch):
    chamada_kwargs = {}

    async def refinar_espiando(*args, **kwargs):
        from app.services.refiner_service import RefinedSpec
        chamada_kwargs.update(kwargs)
        return RefinedSpec(target_files=kwargs.get("target_files") or ["app.py"], **SPEC_DA_IA)

    monkeypatch.setattr(rotas_tarefas.refiner_service, "refinar", refinar_espiando)

    resp = client.post(
        f"/api/tasks/{tarefa['id']}/refine",
        json={"target_files": ["app.py"], "fast_mode": True}
    )

    assert resp.status_code == 200
    assert chamada_kwargs.get("target_files") == ["app.py"]
    assert chamada_kwargs.get("fast_mode") is True

