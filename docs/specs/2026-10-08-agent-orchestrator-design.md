# Especificação de Design: Orquestrador Local Multi-Agente & Multi-Projeto (Agent Orchestrator)

**Data:** 08/10/2026  
**Status:** Aprovado em Brainstorming  
**Autor:** Antigravity & Alex  

---

## 1. Visão Geral e Objetivos

O **Agent Orchestrator** é uma plataforma local projetada para resolver a sobrecarga cognitiva e o colapso de contexto decorrentes do desenvolvimento simultâneo com múltiplos agentes de IA.

### 1.1 Problemas Resolvidos
1. **Colisão de Canais (Chat Linear):** Elimina a intercalação de respostas de múltiplos agentes em uma única timeline de chat. Cada tarefa passa a ter seu canal e histórico 100% isolados.
2. **Inchaço de Contexto (Context Bloat):** As tarefas operam em contextos atômicos e independentes. Nenhuma tarefa polui a janela de contexto de outra.
3. **Colisão de Arquivos:** Cada tarefa em execução cria e utiliza um **Git Worktree** isolado. Dois ou mais agentes podem trabalhar simultaneamente no mesmo repositório sem sobrescrever arquivos.
4. **Falta de Refinamento de Prompts:** Módulo integrado de "Engenheiro de Especificação" (*Prompt Refiner*) que converte ideias brutas em especificações técnicas estruturadas antes da execução.
5. **Central de Revisão e Aprovação (Human-in-the-Loop):** Interface com visualizador de Git Diffs, galeria de mockups/artefatos e botão de merge em 1 clique.

---

## 2. Arquitetura do Sistema

O sistema é composto por um **Backend Reativo em Python** e um **Frontend Moderno em React**, comunicando-se via REST e WebSockets para streaming em tempo real.

```
+-----------------------------------------------------------------------------------+
|                        FRONTEND (React + Vite + Tailwind)                         |
|  +--------------------+  +-----------------------------------------------------+  |
|  |  Project Sidebar   |  |                   KANBAN BOARD                      |  |
|  |  - Projeto A       |  | [Ideação] -> [Prompt Lapidado] -> [Executando]      |  |
|  |  - Projeto B       |  |              -> [Aguardando Revisão] -> [Concluído] |  |
|  |  + Novo Projeto    |  +-----------------------------------------------------+  |
|  +--------------------+  +-----------------------------------------------------+  |
|                          |     TASK DRAWER / MODAL (Contexto Isolado)          |  |
|                          |  [Chat Exclusivo] [Logs / Terminal] [Spec / Prompt] |  |
|                          |  [Central de Revisão: Diffs Git & Preview Mockups]  |  |
|                          +-----------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
                                   ▲                ▲
                       REST API    │                │ WebSockets (Streaming)
                                   ▼                ▼
+-----------------------------------------------------------------------------------+
|                           BACKEND (FastAPI + Asyncio)                             |
|  +---------------------+  +----------------------+  +--------------------------+  |
|  |   ProjectManager    |  |     TaskManager      |  |   PromptRefinerService   |  |
|  | (Diretórios & Git)  |  |  (Estados & Threads) |  |   (Lapidador de Prompts) |  |
|  +---------------------+  +----------------------+  +--------------------------+  |
|  +-----------------------------------------------------------------------------+  |
|  |                     EXECUTION ENGINE (Executor Híbrido)                     |  |
|  |   - Subprocess Runner: Dispara CLIs locais (Antigravity agy, Claude Code)  |  |
|  |   - Direct API Runner: Streaming com Anthropic / Gemini / OpenAI APIs       |  |
|  +-----------------------------------------------------------------------------+  |
|  +-----------------------------------------------------------------------------+  |
|  |    GitWorktreeService: Cria e gerencia branches e pastas de trabalho        |  |
|  |                        temporárias por tarefa (Zero colisão de arquivos)    |  |
|  +-----------------------------------------------------------------------------+  |
|  +-----------------------------------------------------------------------------+  |
|  |             SQLite DB: Persistência de Projetos, Tasks, Mensagens e Logs    |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 3. Modelo de Dados (SQLite & Pydantic)

### 3.1 Entidades Principais
* **`Project`**:
  * `id`: UUID (chave primária)
  * `name`: string
  * `root_path`: string (caminho absoluto do diretório do projeto no disco)
  * `default_branch`: string (padrão: `main`)
  * `created_at`: datetime
* **`Task`**:
  * `id`: UUID (chave primária)
  * `project_id`: UUID (chave estrangeira para Project)
  * `title`: string
  * `raw_prompt`: string (ideia original do usuário)
  * `refined_spec`: string (especificação técnica formatada)
  * `status`: enum (`DRAFT`, `SPEC_READY`, `QUEUED`, `RUNNING`, `REVIEW_READY`, `DONE`, `FAILED`)
  * `runner_type`: enum (`SUBPROCESS_CLI`, `DIRECT_API`)
  * `runner_config`: JSON (modelo, comando de CLI, flags adicionais)
  * `worktree_path`: string (caminho temporário da pasta de trabalho)
  * `git_branch`: string (ex: `task/uuid-resumido`)
  * `created_at`: datetime
  * `updated_at`: datetime
* **`Message`**:
  * `id`: UUID
  * `task_id`: UUID (vinculado exclusivamente a esta tarefa)
  * `role`: enum (`USER`, `ASSISTANT`, `SYSTEM`)
  * `content`: string
  * `timestamp`: datetime
* **`Artifact`**:
  * `id`: UUID
  * `task_id`: UUID
  * `name`: string
  * `type`: enum (`DIFF`, `IMAGE`, `MARKDOWN`, `LOG`)
  * `file_path`: string
  * `created_at`: datetime

---

## 4. Ciclo de Vida da Tarefa e Máquina de Estados

1. **`DRAFT` (Ideação):** Usuário cria a tarefa no projeto selecionado e digita a necessidade em linguagem natural.
2. **`SPEC_READY` (Lapidação):** O serviço `PromptRefiner` formata a ideia em:
   * Objetivo claro
   * Arquivos a serem modificados/criados
   * Passos de execução detalhados
   * Critérios de aceite
3. **`RUNNING` (Execução Isolada):**
   * O `GitWorktreeService` cria a pasta de trabalho isolada:
     `git worktree add -b task/{id} .worktrees/{id}`.
   * O `ExecutionEngine` inicia o subprocesso ou chamada de API direcionando o `cwd` para a pasta do worktree.
   * Logs e tokens fluem via WebSocket exclusivamente para a aba daquela tarefa.
4. **`REVIEW_READY` (Aguardando Revisão):**
   * O agente conclui a execução.
   * O sistema gera o relatório de diffs (`git diff main..task/{id}`) e lista de artefatos.
   * O usuário pode:
     * **Pedir Ajustes:** Conversa no chat da tarefa $\rightarrow$ retorna para `RUNNING`.
     * **Aprovar & Merge:** Incorpora as mudanças na branch principal $\rightarrow$ avança para `DONE`.
5. **`DONE` (Concluído):**
   * A branch é mergeada na principal.
   * A pasta de worktree temporária é removida de forma segura no Windows.
   * A tarefa é arquivada com histórico completo preservado.

---

## 5. Endpoints da API e Protocolo WebSocket

### 5.1 REST API
* `GET /api/projects` — Lista todos os projetos.
* `POST /api/projects` — Cadastra novo projeto com validação do caminho git.
* `GET /api/projects/{id}/tasks` — Lista tarefas de um projeto agrupadas por coluna de status.
* `POST /api/tasks` — Cria uma nova tarefa em `DRAFT`.
* `POST /api/tasks/{id}/refine` — Aciona o lapidador de prompt e retorna a `refined_spec`.
* `POST /api/tasks/{id}/run` — Inicia a execução da tarefa no worktree isolado.
* `POST /api/tasks/{id}/stop` — Cancela o subprocesso ativo da tarefa de forma limpa.
* `GET /api/tasks/{id}/diff` — Retorna o diff unificado da branch da tarefa contra a main.
* `POST /api/tasks/{id}/merge` — Efetua o merge na main e remove a worktree.
* `GET /api/tasks/{id}/messages` — Retorna o histórico de chat isolado da tarefa.
* `POST /api/tasks/{id}/messages` — Envia mensagem de feedback do usuário para o agente da tarefa.

### 5.2 WebSockets
* `/ws/tasks/{id}`:
  * Eventos recebidos pelo cliente: `LOG_LINE`, `STREAM_CHUNK`, `STATUS_CHANGE`, `ERROR`.
  * Eventos enviados pelo cliente: `STOP`, `CHAT_MESSAGE`.
* `/ws/dashboard`:
  * Notificações globais leves: `TASK_UPDATED` (mudança de status, badge de revisão).

---

## 6. Tratamento de Erros e Resiliência no Windows

1. **Encerramento Limpo de Processos:** Em caso de parada de tarefa ou timeout, o backend executa encerramento da árvore de processos via PID (`taskkill /F /T /PID <pid>`), evitando processos órfãos no Windows.
2. **Concorrência e File Locks:** Limpeza de worktrees com retentativas seguras e tratamento de exceções de permissão comuns no Windows.
3. **Detecção de Conflitos de Merge:** Caso duas tarefas concorrentes no mesmo projeto alterem o mesmo trecho, o orquestrador exibe o aviso de conflito e oferece botão de resolução assistida por IA.
4. **Persistência Total:** Qualquer reinicialização do sistema recupera o estado exato dos projetos, tarefas e branches sem perda de histórico.

---

## 7. Estrutura de Diretórios e Execução

O projeto reside em `C:\Users\alex.asbp\.gemini\antigravity\scratch\agent-orchestrator`:
* `backend/`: FastAPI, SQLAlchemy/SQLite, Pydantic, WebSockets, Git Service, Runner Service.
* `frontend/`: React, Vite, Tailwind CSS, Lucide Icons, Kanban, Diff Viewer, Task Drawer.
* `run.py` / `start.bat`: Scripts de inicialização automática em 1 clique para o Windows.

---

## 8. Estratégia de Testes

* **Testes Automatizados Backend (`pytest`):**
  * Teste do ciclo de vida da tarefa (`TaskStateMachine`).
  * Teste de criação e remoção de Git Worktrees em repositório temporário.
  * Teste de isolamento de roteamento dos WebSockets.
  * Teste de rotas REST e persistência no SQLite.
* **Testes Frontend:**
  * Build e typecheck (`npm run build`).
  * Renderização de cards no Kanban, navegação por abas e abertura de drawers.
