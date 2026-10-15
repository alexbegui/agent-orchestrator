# Roteamento de Conversas e Criação Automática de Projetos no Antigravity

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Garantir que tarefas e conversas disparadas pelo Agent Orchestrator sejam criadas dentro do projeto correto no Antigravity (barra lateral esquerda), que novos projetos criados no Orquestrador tenham seus diretórios e workspaces preparados automaticamente, e realocar as conversas existentes do Patrimônio que caíram em `agent-orchestrator`.

**Architecture:**
1. No `assistant_service.py` e `runner_service.py`, garantir que chamadas ao CLI do Antigravity (`agentapi` e `agy`) sejam disparadas com `cwd=project_root` (ou worktree do projeto), e que ao criar uma conversa os metadados de workspace (`workspace_uris` e `project_id`) em `conversation_summaries.db` sejam explicitamente validados/garantidos.
2. Na API de projetos (`projects.py`), ao cadastrar um novo projeto, se o diretório `root_path` não existir no disco, criá-lo automaticamente (`os.makedirs`) e registrar/vincular seu identificador de workspace para o Antigravity.
3. Script/migração para realocar conversas existentes do projeto Patrimônio de volta para a pasta/workspace correta no `conversation_summaries.db`.

**Tech Stack:** Python 3.12, FastAPI, SQLite (`orchestrator.db` e `conversation_summaries.db`), asyncio subprocess.

---

### Task 1: Realocação das Conversas Órfãs no Antigravity

**Files:**
- Modify: `C:/Users/alex.asbp/.gemini/antigravity/conversation_summaries.db`
- Create: `backend/scripts/migrate_antigravity_projects.py`

- [ ] **Step 1: Criar script para identificar e mover conversas de Patrimônio para o workspace correto**
- [ ] **Step 2: Executar migração no banco `conversation_summaries.db` atualizando `workspace_uris` e `project_id` para `ac18ca3d-99c4-48fe-a717-6a80f9bafd86`**
- [ ] **Step 3: Verificar no banco que as conversas foram associadas a `file:///d:/Projetos/Patrimonio`**

---

### Task 2: Correção do Diretório de Execução (`cwd`) e Registro de Workspace em `assistant_service.py`

**Files:**
- Modify: `backend/app/services/assistant_service.py`
- Test: `backend/tests/test_antigravity_project_cwd.py`

- [ ] **Step 1: Escrever teste unitário verificando que `_call_antigravity_cli` passa `cwd=project_root` ao criar conversa e registra o workspace_uris correto**
- [ ] **Step 2: Rodar teste e confirmar que falha (RED)**
- [ ] **Step 3: Implementar em `assistant_service.py`:**
  - Passar `cwd=project_root` (ou `worktree_path`) no `asyncio.create_subprocess_shell` do `_call_antigravity_cli`.
  - Adicionar método auxiliar `ensure_conversation_workspace(conv_id, project_root)` que garante a gravação correta de `workspace_uris` e `project_id` em `conversation_summaries.db`.
- [ ] **Step 4: Rodar teste e confirmar que passa (GREEN)**

---

### Task 3: Criação Automática de Diretório e Registro de Projeto na API

**Files:**
- Modify: `backend/app/api/projects.py`
- Test: `backend/tests/test_project_auto_create_dir.py`

- [ ] **Step 1: Escrever teste unitário para `POST /api/projects` quando o diretório não existe previamente no disco**
- [ ] **Step 2: Rodar teste e confirmar que falha com HTTP 400 (RED)**
- [ ] **Step 3: Modificar `projects.py` para criar o diretório automaticamente (`os.makedirs(normalized_path, exist_ok=True)`) com tratamento de exceções**
- [ ] **Step 4: Rodar teste e confirmar que passa (GREEN)**

---

### Task 4: Verificação Completa e Integração

- [ ] **Step 1: Executar suite de testes do backend para garantir regressão zero**
- [ ] **Step 2: Validar estado final no banco de dados e apresentar walkthrough ao usuário**
