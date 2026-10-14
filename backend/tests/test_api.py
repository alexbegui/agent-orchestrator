import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_api.db"
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


def test_api_create_project_and_task(client, tmp_path, monkeypatch):
    # 1. Create project
    proj_dir = tmp_path / "fake-project"
    proj_dir.mkdir()
    
    resp = client.post("/api/projects", json={
        "name": "Projeto Alpha",
        "root_path": str(proj_dir),
        "default_branch": "main"
    })
    assert resp.status_code == 201
    proj_data = resp.json()
    proj_id = proj_data["id"]
    assert proj_data["name"] == "Projeto Alpha"

    # 2. List projects
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 3. Create task
    resp = client.post("/api/tasks", json={
        "project_id": proj_id,
        "title": "Configurar Auth",
        "raw_prompt": "Adicionar login com JWT",
        "runner_type": "SUBPROCESS_CLI"
    })
    assert resp.status_code == 201
    task_data = resp.json()
    task_id = task_data["id"]
    assert task_data["status"] == "DRAFT"

    # 4. Refine task prompt
    # O refino passou a ser uma chamada de IA, então este teste de ciclo de vida
    # injeta a spec em vez de bater na rede. O comportamento do refino em si
    # (sucesso, IA fora do ar, resposta inválida) está em test_refino_rota.py.
    from app.api import tasks as rotas_tarefas
    from app.services.refiner_service import RefinedSpec

    async def refinar_falso(*args, **kwargs):
        return RefinedSpec(
            objective="Implementar autenticação por token",
            target_files=["app.py"],
            steps=["Escrever o teste do login"],
            acceptance_criteria=["Login com senha correta devolve token"],
        )

    monkeypatch.setattr(rotas_tarefas.refiner_service, "refinar", refinar_falso)
    monkeypatch.setattr(
        rotas_tarefas.git_service, "listar_versionados", lambda _raiz: ["app.py"]
    )

    resp = client.post(f"/api/tasks/{task_id}/refine")
    assert resp.status_code == 200
    refined_data = resp.json()
    assert refined_data["status"] == "SPEC_READY"
    assert "## Objetivo" in refined_data["refined_spec"]

    # 5. Send message in isolated thread
    #
    # O assistente é dublê aqui. Sem isso, este passo chamava os CLIs de
    # verdade e esperava cada um estourar o próprio timeout: 104 dos 106
    # segundos da suíte inteira saíam DESTE teste. E ele não existe para
    # provar que a IA responde — existe para provar que a mensagem é
    # persistida e devolvida na thread certa. Quem cobre a cascata de motores
    # é test_chat_cli_routing.py, e o teto de tempo é test_chat_busy.py.
    async def resposta_instantanea(*args, **kwargs):
        return "Entendido."

    monkeypatch.setattr(
        rotas_tarefas.assistant_service, "generate_chat_reply", resposta_instantanea
    )

    resp = client.post(f"/api/tasks/{task_id}/messages", json={
        "content": "Use tokens com validade de 24 horas"
    })
    assert resp.status_code == 201
    
    # 6. Get messages
    resp = client.get(f"/api/tasks/{task_id}/messages")
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) >= 1
    # A mensagem do usuário tem de estar na thread — não necessariamente por
    # último. Antes a asserção olhava só `messages[-1]`, e passava porque o
    # assistente real demorava tanto que sua resposta não chegava a tempo;
    # com o dublê respondendo na hora, ela aparece depois e o `-1` deixou de
    # ser a do usuário. O que o teste quer provar é a persistência na thread
    # certa, não a ordem.
    assert any("24 horas" in m["content"] for m in messages), messages


def test_api_update_project(client, tmp_path):
    proj_dir = tmp_path / "proj-update"
    proj_dir.mkdir()

    resp = client.post("/api/projects", json={
        "name": "Nome Antigo",
        "root_path": str(proj_dir),
        "default_branch": "main"
    })
    assert resp.status_code == 201
    proj_id = resp.json()["id"]

    # Atualiza o nome
    patch_resp = client.patch(f"/api/projects/{proj_id}", json={
        "name": "Nome Novo"
    })
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Nome Novo"

    # Verifica se persistiu
    get_resp = client.get(f"/api/projects/{proj_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Nome Novo"
