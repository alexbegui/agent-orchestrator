# Agent Orchestrator

## Visão geral

Orquestrador local de agentes de IA. O usuário descreve uma tarefa, escolhe um motor
(Claude Code CLI ou `agy`/Antigravity CLI), e o orquestrador despacha o agente **dentro de um
git worktree isolado** do projeto alvo. O trabalho aparece num painel kanban e o usuário
revisa o diff antes de aprovar o merge.

**Stack**: FastAPI + SQLAlchemy + SQLite · React 18 + TypeScript + Vite + Tailwind ·
WebSocket para tempo real. Fortemente orientado a **Windows**.

**Estrutura**: `backend/app/{api,services,core,models,websockets}` · `frontend/src/{components,hooks,services,types}` ·
`backend/tests/` (182 testes) · `docs/{specs,plans,mockups}`.

Para a arquitetura detalhada, veja [docs/CODEBASE_MAP.md](docs/CODEBASE_MAP.md).

## Os dois conceitos que explicam o resto

**1. O agente não é filho do servidor.** Ele roda desacoplado (`DETACHED_PROCESS`), e o vínculo
com o orquestrador é um arquivo em disco (`.run/run.json`), não um objeto em memória. Por isso
reiniciar o uvicorn não mata trabalho de horas, e por isso existem `run_registry`, `run_wrapper`
e `reconcile`.

**2. O estado visual é derivado, não lido do banco.** O card mostra `card_state`, calculado a
cada resposta a partir do processo real. O `status` no banco pode estar velho — um agente morto
continuaria "Rodando" para sempre.

## Convenções

- **Escreva em português**: comentários, docstrings, nomes de teste e mensagens de erro.
- **Comentários explicam o porquê**, não o quê — no formato "sintoma → causa → regra". Eles são
  a melhor fonte de contexto deste repositório. **Leia os comentários da área antes de mudá-la**:
  várias decisões que parecem estranhas são correções de bugs reais e voltar atrás reintroduz o bug.
- **TDD**: cada defeito corrigido ganha um teste cujo nome descreve o sintoma
  (`test_pid_reciclado_nao_e_confundido_com_o_agente`). A suíte precisa continuar passando inteira.
- Rotas fixas (`/all`, `/refresh-states`, `/sync-all`) vêm **antes** das rotas com `{task_id}`.
- `runner_config` é JSON livre no `Task`. Atribua um **dict novo** para o SQLAlchemy ver a mudança.

## Armadilhas que já custaram caro

- **Nunca recrie uma worktree que existe.** `create_worktree` reaproveita worktree válida. A
  versão antiga removia a pasta e recriava a branch com `-B`, apagando todo o trabalho do agente
  a cada ▶ Rodar.
- **Nunca suponha que o ramo base é `main`.** Use `git_service.branch_base`, que descobre.
- **Nunca declare sucesso sem evidência.** Um serviço já declarava "[Sucesso] Tarefa pronta!"
  sem ter implementado nada. Se não deu para verificar, diga que não deu.
- **PID sozinho não identifica processo** no Windows, que recicla PIDs. Sempre compare também
  o instante de início.
- Abrir a aba de diff **cria um commit** na branch da tarefa (auto-snapshot).
- `CLAUDE_PERMISSION_MODE` é `bypassPermissions` por padrão: o agente executa qualquer comando
  na máquina. O worktree isola arquivos, **não é sandbox de segurança**.

## Rodar

```bash
start.bat                                                  # sobe tudo em http://127.0.0.1:8000
start.bat rebuild                                          # força recompilar o frontend
backend/venv/Scripts/python.exe -m pytest tests -q         # testes (a partir de backend/)
```

Dados locais (`orchestrator.db`, `uploads/`, `.env`, `.worktrees/`) são ignorados pelo git e
nunca devem ser commitados — eles contêm os caminhos e o histórico dos projetos do usuário.
