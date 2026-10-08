# Agent Orchestrator MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o sistema local-first completo do Agent Orchestrator (Backend FastAPI com SQLite e WebSockets + Frontend React Vite com Tailwind) para gerenciar múltiplos projetos e tarefas de agentes em Git Worktrees isolados com CLIs locais (Claude e Gemini).

**Architecture:** Backend Python desacoplado em arquitetura modular assíncrona gerenciando banco SQLite, repositórios git e subprocessos locais. Frontend React SPA reativo com WebSockets transmitindo streaming de logs e tokens por tarefa, Kanban por colunas de estado e central de revisão com diff viewer.

**Tech Stack:** Python 3.10+, FastAPI, Uvicorn, WebSockets, SQLAlchemy/Pydantic, Git CLI (Worktrees), React 18, Vite, TypeScript, Tailwind CSS, Lucide React.

**Spec:** [docs/specs/2026-10-08-agent-orchestrator-design.md](file:///C:/Users/alex.asbp/.gemini/antigravity/scratch/agent-orchestrator/docs/specs/2026-10-08-agent-orchestrator-design.md)

---

## Global Constraints
- Sistema operacional: Windows 11 (usar sintaxe compatível com PowerShell/cmd, launcher `py` no Windows).
- Isolamento total: Cada tarefa executa exclusivamente em `.worktrees/task-{id}`.
- Streaming direcionado: O WebSocket de uma tarefa transmite apenas dados referentes ao seu próprio `task_id`.
- TDD Rigoroso: Cada funcionalidade no backend deve ser acompanhada de testes unitários automatizados com `pytest`.

## Review Focus
1. Concorrência no Windows: Processos filhos devem ser encerrados sem deixar processos órfãos (`taskkill /F /T /PID`).
2. Limpeza de Worktrees: Tratamento de exceções caso indexadores ou antivírus bloqueiem a remoção da pasta no Windows.
3. Tratamento de caracteres: Suporte estrito a UTF-8 nas saídas de console dos subprocessos no Windows.
4. Roteamento de WebSockets: Garantir que reconexões ou múltiplos clientes sincronizem o estado correto do card.
5. Detecção de conflitos de merge: Alerta imediato se duas branches alterarem as mesmas linhas no mesmo projeto.

---

### Task 1: Estrutura Base do Backend & Modelos de Dados (SQLite + Pydantic + SQLAlchemy)

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/core/config.py`
- Create: `backend/app/core/database.py`
- Create: `backend/app/models/project.py`
- Create: `backend/app/models/task.py`
- Create: `backend/app/models/message.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces: `Project`, `Task`, `TaskStatus`, `RunnerType`, `Message`, `init_db()`

- [ ] **Step 1: Escrever teste falhando para modelos e criação de tabelas**
- [ ] **Step 2: Rodar teste para verificar falha (`pytest backend/tests/test_models.py -v`)**
- [ ] **Step 3: Implementar `backend/requirements.txt`, `config.py`, `database.py` e modelos SQLAlchemy**
- [ ] **Step 4: Rodar teste para verificar aprovação (`pytest backend/tests/test_models.py -v`)**
- [ ] **Step 5: Commit (`git commit -m "feat(backend): add database models and sqlite setup"`)**

---

### Task 2: Serviço de Gestão de Git Worktrees (`GitWorktreeService`)

**Files:**
- Create: `backend/app/services/git_service.py`
- Test: `backend/tests/test_git_service.py`

**Interfaces:**
- Consumes: `Project`, `Task`
- Produces: `create_worktree(project_path: str, task_id: str) -> str`, `remove_worktree(project_path: str, task_id: str) -> bool`, `get_diff(project_path: str, task_id: str) -> str`, `merge_task(project_path: str, task_id: str) -> bool`

- [ ] **Step 1: Escrever testes unitários para criação, diff e merge de worktrees**
- [ ] **Step 2: Rodar teste para verificar falha**
- [ ] **Step 3: Implementar `GitWorktreeService` com suporte a Windows e tratamento de locks**
- [ ] **Step 4: Rodar teste para verificar aprovação**
- [ ] **Step 5: Commit (`git commit -m "feat(git): implement git worktree service"`)**

---

### Task 3: Serviço Executor de Processos & CLIs (`RunnerService`)

**Files:**
- Create: `backend/app/services/runner_service.py`
- Test: `backend/tests/test_runner_service.py`

**Interfaces:**
- Consumes: `Task`, `GitWorktreeService`
- Produces: `RunnerService.execute_task(task: Task, on_output: Callable) -> AsyncGenerator`, `RunnerService.stop_task(task_id: str) -> bool`

- [ ] **Step 1: Escrever teste para execução assíncrona de subprocesso e encerramento limpo via PID**
- [ ] **Step 2: Rodar teste para verificar falha**
- [ ] **Step 3: Implementar `RunnerService` suportando Claude Code (`claude.cmd`), Antigravity (`agy.exe`) e comandos customizados**
- [ ] **Step 4: Rodar teste para verificar aprovação**
- [ ] **Step 5: Commit (`git commit -m "feat(runner): implement hybrid subprocess runner service"`)**

---

### Task 4: Serviço de Refinamento de Prompts (`PromptRefinerService`)

**Files:**
- Create: `backend/app/services/refiner_service.py`
- Test: `backend/tests/test_refiner_service.py`

**Interfaces:**
- Consumes: `raw_prompt: str`, `project_context: str`
- Produces: `PromptRefinerService.refine(raw_prompt: str, files_list: list) -> RefinedSpec`

- [ ] **Step 1: Escrever testes de formatação e parser da especificação técnica lapidada**
- [ ] **Step 2: Rodar teste para verificar falha**
- [ ] **Step 3: Implementar `PromptRefinerService` com prompt template de especificação e context pruning**
- [ ] **Step 4: Rodar teste para verificar aprovação**
- [ ] **Step 5: Commit (`git commit -m "feat(refiner): implement prompt refiner service"`)**

---

### Task 5: Endpoints REST & Roteador WebSockets (FastAPI)

**Files:**
- Create: `backend/app/api/projects.py`
- Create: `backend/app/api/tasks.py`
- Create: `backend/app/websockets/manager.py`
- Create: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Produces: Rotas `/api/projects`, `/api/tasks`, `/ws/tasks/{id}`, `/ws/dashboard`

- [ ] **Step 1: Escrever testes de integração para as rotas REST e canais WebSocket**
- [ ] **Step 2: Rodar teste para verificar falha**
- [ ] **Step 3: Implementar rotas e gerenciador de conexões WebSocket com broadcasting isolado por task**
- [ ] **Step 4: Rodar testes da API para verificar aprovação**
- [ ] **Step 5: Commit (`git commit -m "feat(api): add REST endpoints and isolated task websockets"`)**

---

### Task 6: Frontend React — Estrutura Base & Tipos (Vite + Tailwind + TypeScript)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/src/types/index.ts`
- Create: `frontend/src/services/api.ts`
- Create: `frontend/src/hooks/useTaskWebSocket.ts`

- [ ] **Step 1: Configurar dependências e scripts do frontend**
- [ ] **Step 2: Definir contratos TypeScript idênticos aos modelos do backend**
- [ ] **Step 3: Implementar cliente de API e hook de WebSocket com reconexão automática**
- [ ] **Step 4: Verificar compilação com `npm run build` ou teste de tipos**
- [ ] **Step 5: Commit (`git commit -m "feat(frontend): scaffold react vite app and api client"`)**

---

### Task 7: Frontend React — Componentes de Interface (Kanban, Drawer & Review Center)

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`
- Create: `frontend/src/components/KanbanBoard.tsx`
- Create: `frontend/src/components/TaskCard.tsx`
- Create: `frontend/src/components/TaskDrawer.tsx`
- Create: `frontend/src/components/DiffViewer.tsx`
- Create: `frontend/src/components/TokenWidget.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: Implementar Sidebar com alternador de projetos e status**
- [ ] **Step 2: Implementar KanbanBoard com colunas de estado e badges reativos**
- [ ] **Step 3: Implementar TaskDrawer com abas: Chat Isolado, Terminal/Logs em tempo real, Spec e Review Gate**
- [ ] **Step 4: Implementar DiffViewer para revisão side-by-side e botão de Aprovar & Merge**
- [ ] **Step 5: Integrar tudo no App.tsx e validar build completo**
- [ ] **Step 6: Commit (`git commit -m "feat(frontend): implement kanban, task drawer and review center"`)**

---

### Task 8: Scripts de Inicialização no Windows & Verificação Ponta a Ponta

**Files:**
- Create: `run.py`
- Create: `start.bat`
- Create: `README.md`

- [ ] **Step 1: Criar script `run.py` que checa ambiente, inicia FastAPI e serve o frontend**
- [ ] **Step 2: Criar atalho `start.bat` para inicialização com 1 clique no Windows**
- [ ] **Step 3: Escrever README com instruções completas de uso**
- [ ] **Step 4: Executar suíte completa de testes (`pytest`) para validação final**
- [ ] **Step 5: Commit (`git commit -m "feat: add 1-click launcher scripts and docs"`)**
