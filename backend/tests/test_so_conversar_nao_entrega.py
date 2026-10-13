"""
Resíduo do defeito do "Assistente Integrado" que declarava sucesso sem implementar.

O commit 5a142e9 consertou a função: ela parou de escrever TASK_IMPLEMENTATION.md,
parou de commitar, parou de dizer "[Sucesso] Tarefa pronta!", e passou a devolver
False em vez de True.

Mas quem chama **descartava o retorno**:

    await assistant_service.execute_task_direct(...)   # False ignorado
    final_status = TaskStatus.REVIEW_READY

E `_card_state` traduz REVIEW_READY em "ENTREGOU". Resultado: a tarefa "💬 Só
conversar" terminava com o card em "🟣 Entregou · revisar" e um diff vazio. O log
ficou honesto; o estado continuou dizendo que entregou — que é a mesma classe de
defeito num lugar que a correção não alcançou.
"""
import subprocess
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.project import Project
from app.models.task import Task, TaskStatus, RunnerType
from app.api.tasks import _run_task_background, _card_state


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def cenario(tmp_path):
    """Projeto git de verdade + tarefa no banco, prontos para executar."""
    raiz = tmp_path / "projeto"
    raiz.mkdir()
    (raiz / "app.py").write_text("print('oi')\n", encoding="utf-8")
    _git("init", cwd=raiz)
    _git("config", "user.email", "teste@teste", cwd=raiz)
    _git("config", "user.name", "Teste", cwd=raiz)
    _git("add", "-A", cwd=raiz)
    _git("commit", "-m", "inicial", cwd=raiz)

    engine = create_engine(
        f"sqlite:///{tmp_path / 'teste.db'}", connect_args={"check_same_thread": False}
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = Session()
    projeto = Project(name="Projeto", root_path=str(raiz), default_branch="master")
    db.add(projeto)
    db.commit()
    tarefa = Task(
        project_id=projeto.id,
        title="Só conversar sobre a arquitetura",
        raw_prompt="me explica como funciona o merge",
        status=TaskStatus.QUEUED,
        runner_type=RunnerType.DIRECT_API,
        runner_config={"cli": "assistant"},
    )
    db.add(tarefa)
    db.commit()
    tid = tarefa.id
    db.close()

    return {"raiz": str(raiz), "Session": Session, "task_id": tid}


def _recarregar(cenario) -> Task:
    db = cenario["Session"]()
    tarefa = db.query(Task).filter(Task.id == cenario["task_id"]).first()
    db.refresh(tarefa)
    db.expunge(tarefa)
    db.close()
    return tarefa


@pytest.mark.asyncio
async def test_so_conversar_nao_termina_como_entregou(cenario):
    """O sintoma: card roxo 'Entregou · revisar' para uma tarefa que não escreveu nada."""
    await _run_task_background(
        cenario["task_id"],
        cenario["raiz"],
        ["assistant"],
        cenario["Session"],
        is_assistant=True,
        prompt="me explica como funciona o merge",
    )

    tarefa = _recarregar(cenario)
    assert tarefa.status != TaskStatus.REVIEW_READY

    db = cenario["Session"]()
    estado = _card_state(tarefa, db, is_alive=False, stalled=False)
    db.close()
    assert estado != "ENTREGOU"


@pytest.mark.asyncio
async def test_execucao_que_escreve_codigo_continua_entregando(cenario):
    """
    O conserto não pode virar o bug oposto: quem de fato trabalhou tem de
    continuar chegando em REVIEW_READY.
    """
    from app.api import tasks as rotas
    from app.services import assistant_service as mod_assistente

    async def entregou(**kwargs):
        await kwargs["log_callback"]("[Assistente] implementei de verdade")
        return True

    original = mod_assistente.assistant_service.execute_task_direct
    mod_assistente.assistant_service.execute_task_direct = entregou
    rotas.assistant_service.execute_task_direct = entregou
    try:
        await _run_task_background(
            cenario["task_id"],
            cenario["raiz"],
            ["assistant"],
            cenario["Session"],
            is_assistant=True,
            prompt="faz alguma coisa",
        )
    finally:
        mod_assistente.assistant_service.execute_task_direct = original
        rotas.assistant_service.execute_task_direct = original

    assert _recarregar(cenario).status == TaskStatus.REVIEW_READY
