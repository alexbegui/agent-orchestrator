"""
Artefato encontrado fora da pasta da tarefa precisa ABRIR, não só aparecer.

Sintoma real (visto no log do servidor, quatro tentativas do usuário):

    GET /api/tasks/<id>/artifacts/.worktrees/ledger-postgres-docker/docs/mapa-mental-databricks.mmd      404
    GET /api/tasks/<id>/artifacts/.worktrees/ledger-postgres-docker/docs/mapa-mental-databricks.mmd/raw  404

Causa: `listar_amplo` nomeia o que veio de fora relativo à RAIZ DO PROJETO,
mas os endpoints de leitura resolviam o nome contra o WORKTREE DA TAREFA. O
nome era relativo a um lugar e a leitura partia de outro, então o arquivo
nunca era achado.

Regra: a lista e a leitura precisam falar da mesma base. Como o worktree da
tarefa fica em `<projeto>/.worktrees/task-<id>`, a raiz do projeto é ancestral
de tudo que a lista varre — é ela a base única. Cada item carrega `rel_path`,
o caminho a partir dessa raiz, e é isso que o cliente devolve ao ler.
"""
import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.task import Task
from app.services.artifact_service import ArtifactService, ARTIFACT_DIR

CONTEUDO = "mindmap\n  root((Databricks))\n    Bronze\n    Silver\n"


def _escrever(pasta: str, rel: str, texto: str) -> None:
    alvo = os.path.join(pasta, rel)
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    with open(alvo, "w", encoding="utf-8") as f:
        f.write(texto)


@pytest.fixture
def projeto(tmp_path):
    """
    Reproduz a geometria real: o worktree da tarefa e a worktree "alheia"
    ficam ambos sob a raiz do projeto, em .worktrees/.
    """
    raiz = tmp_path / "projeto"
    worktree_tarefa = raiz / ".worktrees" / "task-abc123"
    worktree_outra = raiz / ".worktrees" / "ledger-postgres-docker"
    for p in (raiz, worktree_tarefa, worktree_outra):
        p.mkdir(parents=True, exist_ok=True)

    # O agente navegou e salvou o mapa na worktree do docker, não na da tarefa.
    _escrever(str(worktree_outra), os.path.join(ARTIFACT_DIR, "mapa-mental-databricks.mmd"), CONTEUDO)
    return raiz, worktree_tarefa, worktree_outra


@pytest.fixture
def client(tmp_path):
    db_file = tmp_path / "test_artefato_fora.db"
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
    with TestClient(app) as c:
        yield c, Session
    app.dependency_overrides.clear()


# ---------- nível do serviço ----------

def test_item_de_fora_carrega_o_caminho_a_partir_da_raiz(projeto):
    """Sem uma chave relativa à raiz, a leitura não tem como achar o arquivo."""
    raiz, worktree_tarefa, _ = projeto
    itens = ArtifactService().listar_amplo(str(worktree_tarefa), str(raiz))

    de_fora = [i for i in itens if i.get("outside_task")]
    assert de_fora, "o mapa salvo na outra worktree nem foi encontrado"

    item = de_fora[0]
    assert "rel_path" in item, "o item não diz onde está a partir da raiz do projeto"
    # A chave precisa resolver de verdade a partir da raiz.
    assert os.path.isfile(os.path.join(str(raiz), item["rel_path"])), (
        f"rel_path={item['rel_path']} não existe a partir de {raiz}"
    )


def test_item_de_dentro_tambem_carrega_a_chave(projeto):
    """A base é única: o que está na tarefa usa a mesma régua."""
    raiz, worktree_tarefa, _ = projeto
    _escrever(str(worktree_tarefa), os.path.join(ARTIFACT_DIR, "analise.md"), "# analise")

    itens = ArtifactService().listar_amplo(str(worktree_tarefa), str(raiz))
    de_dentro = [i for i in itens if not i.get("outside_task")]
    assert de_dentro

    item = de_dentro[0]
    assert os.path.isfile(os.path.join(str(raiz), item["rel_path"]))
    # O nome mostrado ao usuário continua curto; a chave é que é longa.
    assert not item["name"].startswith(".worktrees/"), (
        "o nome exibido não deve ganhar o prefixo interno do worktree"
    )


# ---------- nível da API: o 404 do log ----------

def _tarefa(client_tuple, projeto):
    client, Session = client_tuple
    raiz, worktree_tarefa, _ = projeto

    r = client.post("/api/projects", json={
        "name": "Projeto Artefatos", "root_path": str(raiz), "default_branch": "main"
    })
    assert r.status_code == 201
    proj_id = r.json()["id"]

    r = client.post("/api/tasks", json={
        "project_id": proj_id, "title": "Mapa mental", "raw_prompt": "faça o mapa"
    })
    assert r.status_code == 201
    task_id = r.json()["id"]

    session = Session()
    t = session.query(Task).filter(Task.id == task_id).first()
    t.worktree_path = str(worktree_tarefa)
    session.commit()
    session.close()
    return task_id


def test_abrir_artefato_de_fora_nao_da_404(client, projeto):
    """O sintoma exato do log: aparece na lista e devolve 404 ao abrir."""
    task_id = _tarefa(client, projeto)
    c, _ = client

    r = c.get(f"/api/tasks/{task_id}/artifacts")
    assert r.status_code == 200
    de_fora = [a for a in r.json()["artifacts"] if a.get("outside_task")]
    assert de_fora, "o artefato de fora sumiu da listagem"

    chave = de_fora[0]["rel_path"]

    r = c.get(f"/api/tasks/{task_id}/artifacts/{chave}")
    assert r.status_code == 200, (
        f"o artefato aparece na lista mas não abre (404 do log): {r.text[:200]}"
    )
    assert "Databricks" in r.json()["content"]


def test_servir_artefato_de_fora_nao_da_404(client, projeto):
    """Mesmo sintoma no /raw, que é o botão 'Abrir' do painel."""
    task_id = _tarefa(client, projeto)
    c, _ = client

    r = c.get(f"/api/tasks/{task_id}/artifacts")
    chave = [a for a in r.json()["artifacts"] if a.get("outside_task")][0]["rel_path"]

    r = c.get(f"/api/tasks/{task_id}/artifacts/{chave}/raw")
    assert r.status_code == 200, f"/raw também devolveu {r.status_code}"
    assert b"Databricks" in r.content


def test_continua_bloqueando_path_traversal(client, projeto):
    """A base mudou para a raiz do projeto; a guarda não pode ter afrouxado."""
    task_id = _tarefa(client, projeto)
    c, _ = client

    r = c.get(f"/api/tasks/{task_id}/artifacts/../../../../.env")
    assert r.status_code in (400, 404), (
        f"traversal devolveu {r.status_code} — a guarda de caminho afrouxou"
    )
