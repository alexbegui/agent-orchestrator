"""
O prompt do agente dizia ONDE salvar e O QUE registrar — nunca COMO trabalhar.

Sem nenhuma regra de comportamento, cada tarefa virava uma loteria de
disciplina: um agente escrevia teste, o seguinte não; um verificava antes de
declarar pronto, o seguinte declarava no escuro. A §7.2 item 4 da spec previa
"injeção sob demanda" de instruções e nunca saiu do papel.

Duas regras entram, e são as duas que este repositório já aprendeu na pele:
TDD e "nunca declare sucesso sem evidência".

O CLAUDE.md do projeto alvo entra JUNTO — mas só para os motores que não o
leem sozinhos, senão é token pago duas vezes.
"""
import pytest

from app.services.prompt_service import (
    regras_de_trabalho,
    memoria_do_projeto,
    instrucao_de_entrega,
    le_o_claude_md_sozinho,
    MAX_MEMORIA,
)


# --- Regras de trabalho ------------------------------------------------------

def test_regras_cobram_teste_antes_do_codigo():
    texto = regras_de_trabalho()

    assert "teste" in texto.lower()
    assert "antes" in texto.lower()


def test_regras_proibem_declarar_sucesso_sem_evidencia():
    """
    A armadilha mais cara do repositório: um serviço já declarou
    "[Sucesso] Tarefa pronta!" sem ter implementado nada.
    """
    texto = regras_de_trabalho().lower()

    assert "evidência" in texto or "evidencia" in texto


def test_regras_sao_as_mesmas_em_toda_tarefa():
    """
    Bloco estático: é o que permite o prompt caching funcionar, porque fica
    no começo e não muda. Se variar por tarefa, o cache nunca acerta.
    """
    assert regras_de_trabalho() == regras_de_trabalho()


# --- Quem já lê o CLAUDE.md sozinho ------------------------------------------

def test_claude_code_le_o_claude_md_sozinho():
    """Ele lê do cwd, que é o worktree. Injetar seria pagar o token duas vezes."""
    assert le_o_claude_md_sozinho({"cli": "claude"}) is True
    assert le_o_claude_md_sozinho({"cli": "Claude Code CLI"}) is True


def test_agy_e_api_direta_nao_leem():
    assert le_o_claude_md_sozinho({"cli": "agy"}) is False
    assert le_o_claude_md_sozinho({"cli": "assistant"}) is False
    assert le_o_claude_md_sozinho({}) is False


# --- Memória do projeto alvo -------------------------------------------------

@pytest.fixture
def projeto(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "# Projeto X\n\nNunca mexa no gerador de faturas sem rodar o lote de regressão.\n",
        encoding="utf-8",
    )
    return str(tmp_path)


def test_memoria_entra_para_motor_que_nao_le_sozinho(projeto):
    texto = memoria_do_projeto(projeto, {"cli": "agy"})

    assert "gerador de faturas" in texto


def test_memoria_nao_entra_para_quem_ja_le(projeto):
    """Duplicar o CLAUDE.md no prompt do Claude Code é token pago à toa."""
    assert memoria_do_projeto(projeto, {"cli": "claude"}) == ""


def test_projeto_sem_claude_md_nao_quebra(tmp_path):
    assert memoria_do_projeto(str(tmp_path), {"cli": "agy"}) == ""


def test_memoria_gigante_e_truncada_com_aviso(tmp_path):
    """
    CLAUDE.md de projeto grande pode ter dezenas de KB. Entrar inteiro no
    prompt de toda tarefa é a §7.2 ao contrário.
    """
    (tmp_path / "CLAUDE.md").write_text("linha de memória\n" * 5000, encoding="utf-8")

    texto = memoria_do_projeto(str(tmp_path), {"cli": "agy"})

    assert len(texto) <= MAX_MEMORIA + 500
    assert "truncad" in texto.lower()


# --- Pedido do sumário de entrega --------------------------------------------

def test_instrucao_pede_o_sumario_no_lugar_certo():
    texto = instrucao_de_entrega("C:/proj/.worktrees/task-1")

    assert "walkthrough.md" in texto
    assert "C:/proj/.worktrees/task-1" in texto


def test_instrucao_pede_o_que_nao_foi_feito():
    """
    A parte que o agente mais omite e que mais te custa: o que ele tentou e
    falhou, e o que deixou de fora. Sem pedir, ele escreve só a vitória.
    """
    texto = instrucao_de_entrega("C:/proj").lower()

    assert "não" in texto and ("fez" in texto or "fora" in texto or "faltou" in texto)


def test_sem_worktree_nao_pede_nada():
    assert instrucao_de_entrega("") == ""


# --- O prompt montado de verdade, pela rota ----------------------------------

def test_o_agente_recebe_as_regras_e_o_pedido_de_sumario(tmp_path, monkeypatch):
    """
    A prova que importa: não basta as funções existirem soltas, elas precisam
    estar ligadas ao prompt que o agente recebe de fato.
    """
    import subprocess
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base, get_db
    from app.main import app
    from app.api import tasks as rotas

    projeto = tmp_path / "projeto"
    projeto.mkdir()
    (projeto / "app.py").write_text("print(1)\n", encoding="utf-8")
    (projeto / "CLAUDE.md").write_text(
        "# Projeto\nNunca mexa no gerador de faturas sem rodar o lote.\n", encoding="utf-8"
    )
    for args in (["init"], ["config", "user.email", "t@t"], ["config", "user.name", "T"],
                 ["add", "-A"], ["commit", "-m", "inicial"]):
        subprocess.run(["git", *args], cwd=projeto, check=True, capture_output=True)

    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    Sessao = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    def abrir_sessao():
        s = Sessao()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = abrir_sessao

    capturado = {}

    def espiao(runner_type, prompt, cfg):
        capturado["prompt"] = prompt
        return ["echo", "ok"]

    monkeypatch.setattr(rotas.runner_service, "resolve_cli_command", espiao)
    # Não dispara o agente de verdade: o que se prova aqui é o prompt montado.
    monkeypatch.setattr(rotas, "_run_task_background", _nao_faz_nada)

    with TestClient(app) as cliente:
        pid = cliente.post("/api/projects", json={
            "name": "P", "root_path": str(projeto), "default_branch": "master"}).json()["id"]
        tid = cliente.post("/api/tasks", json={
            "project_id": pid, "title": "T", "raw_prompt": "faz alguma coisa",
            "runner_config": {"cli": "agy"}}).json()["id"]
        assert cliente.post(f"/api/tasks/{tid}/run").status_code == 200

    app.dependency_overrides.clear()
    prompt = capturado["prompt"]

    assert "Como trabalhar nesta tarefa" in prompt
    assert "**veja-o falhar**" in prompt
    assert "walkthrough.md" in prompt
    assert "O que NÃO fiz" in prompt
    # Motor que não lê o CLAUDE.md sozinho recebe a memória do projeto alvo:
    assert "gerador de faturas" in prompt
    # E as regras vêm ANTES do pedido, senão o cache nunca casa prefixo.
    assert prompt.index("Como trabalhar") < prompt.index("faz alguma coisa")


async def _nao_faz_nada(*args, **kwargs):
    return None
