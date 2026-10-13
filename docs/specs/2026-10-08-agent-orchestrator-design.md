# Especificação de Design: Orquestrador Local Multi-Agente & Multi-Projeto (Agent Orchestrator)

**Data:** 08/10/2026  
**Status:** Aprovado em Brainstorming  
**Autor:** Antigravity & Alex  

> ### 📌 Como ler este documento (anotado em 13/10/2026)
>
> **O texto original de 08/10 está preservado inteiro.** Nada foi apagado ou
> reescrito: o que foi planejado continua aqui como foi aprovado, e é isso que
> torna possível ver o que a realidade mudou.
>
> O que foi acrescentado são blocos assim, colados logo abaixo da parte a que
> se referem:
>
> > **🔴 Realidade em 13/10/2026 — título**
> > o que o código faz hoje, e por quê.
>
> Três cores de bloco, pelo tipo de divergência:
>
> | | Significado |
> |---|---|
> | 🔴 | **A spec está errada.** Seguir o texto ao pé da letra reintroduz um bug real que já aconteceu em produção. |
> | 🟡 | **A spec está desatualizada.** O código foi para outro lugar, por decisão consciente. Nada quebra, mas o documento descreve algo que não existe. |
> | ⚪ | **A spec não foi entregue.** Continua sendo o plano; ainda não virou código. |
>
> Os três blocos 🔴 são o motivo deste documento ter sido anotado em vez de
> reescrito. Eles estão também no `CLAUDE.md`, com a história completa de cada
> bug. A comparação peça por peça está em [`docs/spec-vs-realidade.md`](../spec-vs-realidade.md).

---

## 1. Visão Geral e Objetivos

O **Agent Orchestrator** é uma plataforma local projetada para resolver a sobrecarga cognitiva e o colapso de contexto decorrentes do desenvolvimento simultâneo com múltiplos agentes de IA.

### 1.1 Problemas Resolvidos
1. **Colisão de Canais (Chat Linear):** Elimina a intercalação de respostas de múltiplos agentes em uma única timeline de chat. Cada tarefa passa a ter seu canal e histórico 100% isolados.
2. **Inchaço de Contexto (Context Bloat):** As tarefas operam em contextos atômicos e independentes. Nenhuma tarefa polui a janela de contexto de outra.
3. **Colisão de Arquivos:** Cada tarefa em execução cria e utiliza um **Git Worktree** isolado. Dois ou mais agentes podem trabalhar simultaneamente no mesmo repositório sem sobrescrever arquivos.
4. **Falta de Refinamento de Prompts:** Módulo integrado de "Engenheiro de Especificação" (*Prompt Refiner*) que converte ideias brutas em especificações técnicas estruturadas antes da execução.
5. **Central de Revisão e Aprovação (Human-in-the-Loop):** Interface com visualizador de Git Diffs, galeria de mockups/artefatos e botão de merge em 1 clique.

> **🟡 Realidade em 13/10/2026 — o item 4 existiu como casca por 5 dias**
>
> O *Prompt Refiner* foi implementado como **regex**, não como IA: o "objetivo"
> era `raw_prompt.strip()` (uma cópia), os passos eram três frases fixas, e os
> critérios de aceite eram **três constantes idênticas em toda tarefa**. A
> escolha de arquivos casava substring do prompt contra o caminho — medido:
> dois pedidos sem relação nenhuma ("calcular frete" e "trocar a cor do botão
> de login") recebiam **a mesma lista de arquivos**.
>
> Importava porque o item 4 é o portão de aprovação do item 5: você aprovava um
> texto genérico achando que era entendimento da IA.
>
> **Corrigido em 13/10.** Hoje o refino é IA de verdade, em duas chamadas —
> primeiro escolhe de 2 a 5 arquivos vendo só a árvore de caminhos (e diz *por
> que* cada um), depois escreve a spec vendo o **conteúdo** deles. A separação
> existe porque critério de aceite específico exige ter lido o código; numa
> chamada só a IA escreveria por adivinhação, que é o defeito do regex de roupa
> nova. A spec passou a incluir um **plano de testes TDD** (arquivo, nome da
> função, o que prova), que a spec original não previa.
>
> E o refino agora **pode falhar**: sem chave de API ou com resposta inválida,
> `/refine` devolve 502 e a tarefa continua em `DRAFT`. Não há fallback
> heurístico de propósito — o regex nunca falhava, e produzia spec genérica
> indistinguível de uma real. O portão só vale se o que está atrás for genuíno.

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

> **🟡 Realidade — `Artifact` nunca virou tabela**
>
> `Project`, `Task` e `Message` foram implementados exatamente como aqui,
> campo por campo. `Artifact` não: não existe `__tablename__ = "artifacts"`.
> Artefatos são **descobertos varrendo o disco** (`artifact_service.py`).
>
> A decisão foi consciente. Quem produz o arquivo é o agente, no sistema de
> arquivos, e o banco passaria a mentir no instante em que ele salvasse algo
> fora do esperado — que é exatamente o que acontece (daí existir
> `listar_amplo`, que procura além da pasta da tarefa, e o teste
> `test_artefato_de_fora_abre.py`). Um índice em banco seria uma segunda fonte
> de verdade sobre algo que o disco já responde.
>
> O campo `type` sobreviveu como classificação por extensão em memória:
> `.html` → `mockup`, `.png/.jpg` → `imagem`, e assim por diante.

---

## 4. Ciclo de Vida da Tarefa e Máquina de Estados

1. **`DRAFT` (Ideação):** Usuário cria a tarefa no projeto selecionado e digita a necessidade em linguagem natural.
2. **`SPEC_READY` (Lapidação):** O serviço `PromptRefiner` formata a ideia em:
   * Objetivo claro
   * Arquivos a serem modificados/criados
   * Passos de execução detalhados
   * Critérios de aceite

> **🟡 Realidade — a spec ganhou um plano de testes, e este passo pode falhar**
>
> Além dos quatro itens acima, a `refined_spec` traz hoje um **Plano de Testes
> (escrever ANTES do código)** e o **motivo de cada arquivo escolhido**. Esse
> motivo é o que te permite discordar da escolha antes de aprovar.
>
> E a transição `DRAFT → SPEC_READY` **não é garantida**: se a IA não responder,
> a tarefa fica em `DRAFT` e a tela mostra o motivo real. Ver o bloco em §1.1.

3. **`RUNNING` (Execução Isolada):**
   * O `GitWorktreeService` cria a pasta de trabalho isolada:
     `git worktree add -b task/{id} .worktrees/{id}`.
   * O `ExecutionEngine` inicia o subprocesso ou chamada de API direcionando o `cwd` para a pasta do worktree.
   * Logs e tokens fluem via WebSocket exclusivamente para a aba daquela tarefa.

> **🔴 Realidade — esta linha apagava o trabalho do agente. NÃO a siga.**
>
> `git worktree add -b task/{id}` funciona na primeira execução. Mas rodar uma
> tarefa duas vezes é normal — o agente para, você ajusta, clica ▶ Rodar de
> novo — e aí a worktree já existe e o git recusa. A implementação resolvia do
> jeito que parece razoável: **apagava a pasta e recriava a branch com `-B`**.
> Cada ▶ Rodar destruía tudo que o agente tinha feito: arquivos soltos **e
> commits da branch**.
>
> Foi encontrado a partir do relato *"criei um mapa mental e ele não aparece na
> aba Artefatos"*. Do commit `08fc063`: *"Era a causa real dos artefatos
> desaparecerem entre execuções; **o agente não estava mentindo ao dizer que
> salvou**."* O custo real foi você passar a desconfiar do agente.
>
> **Hoje:** `create_worktree` **reaproveita** worktree válida — e "válida" não é
> "a pasta existe", é `git rev-parse --is-inside-work-tree` rodando dentro dela.
> A criação tenta `worktree add <path> <branch>` **sem** `-b` primeiro,
> reaproveitando a branch se ela já tiver trabalho, e só cai no `-b` quando o
> git diz que a branch não existe. A spec põe o `-b` como regra; o código põe
> como exceção. Travado por `test_worktree_nao_destroi.py`.
>
> * **A execução também mudou de natureza.** O `ExecutionEngine` descrito aqui
>   inicia um subprocesso filho do servidor. Hoje o agente roda **desacoplado**
>   (`DETACHED_PROCESS`), com o vínculo num arquivo em disco (`.run/run.json`)
>   em vez de um objeto em memória — por isso reiniciar o uvicorn não mata
>   trabalho de horas, e por isso existem `run_registry`, `run_wrapper` e
>   `reconcile`, que a spec não previu.
4. **`REVIEW_READY` (Aguardando Revisão):**
   * O agente conclui a execução.
   * O sistema gera o relatório de diffs (`git diff main..task/{id}`) e lista de artefatos.
   * O usuário pode:
     * **Pedir Ajustes:** Conversa no chat da tarefa $\rightarrow$ retorna para `RUNNING`.
     * **Aprovar & Merge:** Incorpora as mudanças na branch principal $\rightarrow$ avança para `DONE`.
> **🔴 Realidade — `main` não existia no projeto do usuário. NÃO suponha o nome.**
>
> O projeto real usa `master`. O estrago tinha dois tempos. **Agora:**
> `git diff main...HEAD` falhava **em silêncio** — sem branch `main` não há
> diff, e a aba de artefatos não mostrava o que a tarefa já havia commitado
> (o segundo defeito por trás do mesmo relato do mapa mental). **Depois:** o
> merge faria `git checkout main` num repositório sem `main` e **teria falhado
> na hora de aprovar** — o pior momento possível, com o trabalho feito e já
> revisado. Essa bomba nunca explodiu: foi desarmada investigando o diff.
>
> Havia um terceiro defeito, o mais traiçoeiro: `Project.default_branch`
> existia e tinha `'main'` gravado nos três projetos — valor padrão do
> formulário, **nunca conferido contra o disco**. O banco estava no formato
> certo e no conteúdo errado, então confiar no campo mantinha o bug. Por isso a
> correção não foi "ler do banco", foi **descobrir no disco**.
>
> **Hoje:** `git_service.branch_base` tenta, em ordem de confiabilidade: o que o
> remoto declara (`refs/remotes/origin/HEAD`); depois os nomes usuais — `main`,
> `master`, `trunk`, `develop`, `desenvolvimento` — **mas só os que existem de
> verdade** (`rev-parse --verify`); por último o ramo atual. Nunca chuta.
> Travado por `test_branch_base.py`.

5. **`DONE` (Concluído):**
   * A branch é mergeada na principal.
   * A pasta de worktree temporária é removida de forma segura no Windows.
   * A tarefa é arquivada com histórico completo preservado.

> **🔴 Realidade — o card não mostra o `status` desta máquina de estados**
>
> Esta seção assume, sem nunca escrever, que o banco sabe o que está
> acontecendo: a tarefa tem um `status`, o kanban mostra esse `status`.
>
> Não se sustenta. O agente é um processo **desacoplado**, e o servidor não é
> avisado quando ele morre. O banco só muda quando alguém escreve nele; se o
> processo caiu, travou, ou a máquina hibernou, ninguém escreve. Do commit
> `1acaada`: *"agente morto continuava 'Rodando' para sempre"* — e o usuário
> esperando um agente que não existe mais.
>
> **Hoje:** o card mostra `card_state`, **calculado a cada resposta a partir do
> processo real**. Os estados desta seção continuam válidos como histórico no
> banco; a verdade na tela é o processo. A identificação do processo é
> **PID + instante de início**, porque o Windows recicla PIDs e matar por PID
> puro mataria outro programa.
>
> Dois estados que a spec não tem: *"Te perguntou"* e *"Entregou"* são
> separados *"porque custam tempos diferentes do usuário"* — um pede 10
> segundos, o outro pede meia hora de revisão. Travado por
> `test_card_states.py`.

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

> **🟡 Realidade — as 10 rotas existem; outras 11 nasceram depois**
>
> Todas as rotas desta lista foram implementadas. O que a spec não previu, e
> hoje é mais da metade da superfície da API:
>
> | Rota | Para quê |
> |---|---|
> | `/import-antigravity`, `/import-antigravity-bulk` | trazer conversas do Antigravity como tarefas |
> | `/{id}/sync-antigravity`, `/antigravity/{conv}/sync`, `/sync-all` | sincronizar o transcript |
> | `/{id}/artifacts`, `/{id}/artifacts/{nome}/raw` | galeria de artefatos servida pelo backend |
> | `/{id}/knowledge-proposals` | base de conhecimento do projeto (ver §7.2) |
> | `/{id}/terminal` | abrir um terminal na worktree |
> | `/{id}/upload` | anexos na tarefa |
> | `/refresh-states` | recalcular `card_state` de todas as tarefas |
> | `/all`, `DELETE /{id}` | painel geral e exclusão |
>
> Convenção que vale ao mexer aqui: **rotas fixas (`/all`, `/refresh-states`,
> `/sync-all`) vêm antes das rotas com `{task_id}`**, senão o FastAPI casa
> `/all` como um id de tarefa.

### 5.2 WebSockets
* `/ws/tasks/{id}`:
  * Eventos recebidos pelo cliente: `LOG_LINE`, `STREAM_CHUNK`, `STATUS_CHANGE`, `ERROR`.
  * Eventos enviados pelo cliente: `STOP`, `CHAT_MESSAGE`.
* `/ws/dashboard`:
  * Notificações globais leves: `TASK_UPDATED` (mudança de status, badge de revisão).

> **🟡 Realidade — os nomes dos eventos são outros**
>
> | Spec | Código |
> |---|---|
> | `LOG_LINE` | `LOG` |
> | `STATUS_CHANGE` | `STATUS` |
> | `STREAM_CHUNK` | não existe |
> | `ERROR` | não existe — erro vai como `LOG` |
> | — | **novos:** `MESSAGE`, `TASK_BUSY`, `TASK_CREATED`, `TASK_UPDATED`, `TASK_DELETED`, `TASKS_IMPORTED` |
>
> O cliente também não envia `STOP` pelo WebSocket: parar é `POST /{id}/stop`.
> Nada quebrado — mas quem programar contra esta seção vai escutar eventos que
> nunca chegam.
>
> O `/ws/dashboard` tem uma história própria: **existia no backend e nunca foi
> usado**. O frontend fazia polling de 20s, então o card demorava até 20
> segundos para mostrar que o agente terminou. Hoje o painel escuta o canal,
> com reconexão em espera crescente e agrupamento de 250ms para vários agentes
> terminando juntos. O polling continua como reserva, e um selo "ao vivo"
> mostra se o canal está de pé — sem ele, *"nada aconteceu"* e *"parei de
> receber avisos"* seriam indistinguíveis.

---

## 6. Tratamento de Erros e Resiliência no Windows

1. **Encerramento Limpo de Processos:** Em caso de parada de tarefa ou timeout, o backend executa encerramento da árvore de processos via PID (`taskkill /F /T /PID <pid>`), evitando processos órfãos no Windows.
2. **Concorrência e File Locks:** Limpeza de worktrees com retentativas seguras e tratamento de exceções de permissão comuns no Windows.
3. **Detecção de Conflitos de Merge:** Caso duas tarefas concorrentes no mesmo projeto alterem o mesmo trecho, o orquestrador exibe o aviso de conflito e oferece botão de resolução assistida por IA.
4. **Persistência Total:** Qualquer reinicialização do sistema recupera o estado exato dos projetos, tarefas e branches sem perda de histórico.

> **Realidade — 3 de 4 entregues, e o item 4 foi além do pedido**
>
> * **Item 1 ✅** `runner_service` tenta `psutil` e cai para `taskkill /F /T /PID`.
> * **Item 2 ✅** limpeza de worktree com retentativa.
> * **Item 3 ⚪ parcialmente.** A **detecção** existe: HTTP 409 no merge, e o
>   `git_service` aborta o merge para manter a main limpa. A **"resolução
>   assistida por IA"** não foi implementada.
> * **Item 4 ✅ e além.** A spec pedia que o sistema recuperasse o estado após
>   reiniciar. O código foi mais longe: o **trabalho em si** sobrevive ao
>   reinício, porque o agente roda desacoplado e o servidor reconcilia na
>   subida o que ficou como `RUNNING`. O código de saída é gravado por um
>   envoltório, já que processo desacoplado não devolve `returncode` ao
>   servidor.
>
> Uma armadilha que esta seção não previa e custou caro: **PID sozinho não
> identifica processo no Windows**, que recicla PIDs. Sempre compare também o
> instante de início, senão parar uma tarefa pode matar outro programa.

---

## 7. Configuração de Modelos, CLIs Locais e Economia de Tokens

### 7.1 Configuração de CLIs Locais (Gemini agy e Claude Code)
O usuário pode alternar ou escolher qual motor executará cada tarefa:
* **Detecção Automática no Windows:** O backend verifica se `claude.cmd` (Claude Code) e `agy.exe` (Antigravity CLI) estão presentes no `PATH` do sistema operacional.
* **Configuração no Painel (Settings):**
  * `CLAUDE_PATH`: caminho customizado caso não esteja no PATH (ex: `%APPDATA%\npm\claude.cmd`).
  * `AGY_PATH`: caminho do executável do Antigravity CLI.
  * `API_KEYS`: chaves opcionais para chamadas diretas via API (Anthropic, Gemini, OpenAI).
* **Seletor por Tarefa:** Cada card possui um dropdown onde o usuário escolhe:
  1. *Claude Code CLI (Local)*
  2. *Antigravity CLI (Gemini Local)*
  3. *Direct API (Claude 3.5 Sonnet / Gemini 2.5)*

> **Realidade — a única seção entregue integralmente**
>
> Detecção automática, campos no painel de Ajustes e seletor por tarefa: tudo
> como especificado. Três ajustes que a prática impôs:
>
> * **`agy` passou à frente do `agentapi`** como motor Antigravity: não exige o
>   IDE aberto nem `ANTIGRAVITY_LS_ADDRESS`/`CSRF_TOKEN`.
> * **Claude recebe `--permission-mode`**, padrão `bypassPermissions`. Sem isso,
>   em modo não-interativo toda permissão era negada e o agente travava sem
>   conseguir avisar. ⚠️ Nesse modo o agente **executa qualquer comando na
>   máquina** — o worktree isola arquivos, não é sandbox de segurança.
> * **A opção "Assistente Integrado" era o padrão e dizia "Recomendado"** — e
>   ela não escreve código. Pior: ela escrevia um `TASK_IMPLEMENTATION.md` com
>   o prompt do usuário de volta, commitava, e declarava `[Sucesso] Tarefa
>   pronta!` sem ter implementado nada. Toda tarefa nova nascia incapaz de
>   implementar, e mentia sobre isso. Removido; o padrão passou para Claude e
>   os rótulos passaram a dizer o que cada opção **faz**.

### 7.2 Engenharia de Economia Máxima de Tokens
1. **Prompt Caching Estratégico:**
   * A estrutura dos prompts enviados para os agentes separa a parte estática (regras de sistema, skills selecionadas) na frente da mensagem. Provedores modernos (Claude e Gemini) aplicam **Prompt Caching**, gerando economia de até **70% a 90%** dos tokens lidos em rodadas consecutivas de feedback.
2. **Context Pruning (Contexto Mínimo Viável):**
   * O orquestrador nunca injeta a árvore inteira do repositório no contexto do agente. A etapa de *Prompt Refiner* identifica e passa apenas os 2 a 5 arquivos diretamente afetados pela tarefa.
3. **Compressão de Saída (Output Compression):**
   * O código modificado é gravado diretamente no sistema de arquivos do *worktree*. O histórico de chat da conversa grava apenas um sumário atômico (ex: `walkthrough.md` com 3 tópicos e lista de arquivos alterados), evitando inchaço desnecessário de tokens.
4. **Harness & Gestão Seletiva de Skills:**
   * O projeto conta com uma biblioteca de skills modulares (ex: `ui-ux-pro-max`, `test-driven-development`, `fastapi-standards`).
   * **Injeção sob demanda:** Apenas as skills relevantes para aquela tarefa específica são anexadas ao prompt, evitando o desperdício de dezenas de milhares de tokens com instruções desnecessárias.

> **⚪ Realidade — a maior dívida da spec: 1 de 4 entregues**
>
> | # | Promessa | Status |
> |---|---|---|
> | 1 | Prompt caching estratégico (70–90% de economia) | ⚪ nenhuma ocorrência de `cache_control` no backend |
> | 2 | Context pruning: passar só 2–5 arquivos afetados | ✅ **entregue em 13/10** |
> | 3 | Compressão de saída via `walkthrough.md` | ⚪ nem `walkthrough` nem `execution.log` existem no código |
> | 4 | Injeção seletiva de skills | ⚪ nenhuma ocorrência de `skill` no backend |
>
> **Sobre o item 2.** Até 13/10 ele estava não só ausente como **invertido**: o
> refino varria a árvore inteira do projeto com `os.walk`, pulando apenas
> `.git`, `node_modules` e `.worktrees`. Medido neste repositório: **4.077
> arquivos, ~72 mil tokens, dos quais 3.786 dentro da `venv` do Python** — o
> oposto exato do "nunca injeta a árvore inteira". Não doía porque quem recebia
> era um regex, e regex não gasta token.
>
> Hoje a árvore vem de **`git ls-files`**: 99 arquivos, ~800 tokens, **41 vezes
> menor**. Não é heurística nova — é a lista que o usuário já curou no
> `.gitignore`. A IA escolhe de 2 a 5 arquivos dessa lista, e se a árvore não
> couber no teto ela é ordenada por recência do git e **truncada com aviso
> visível na spec**, em vez de sair pela metade fingindo estar completa.
>
> **Sobre a ordem dos blocos (item 1).** A ideia de pôr a parte estática na
> frente do prompt, para o caching funcionar, foi seguida por acidente: o
> prompt de despacho começa com o conhecimento do projeto e termina com o
> pedido. Falta só declarar `cache_control` para a economia existir de fato.
>
> **O que a spec não previu e funciona: a base de conhecimento do projeto.**
> Cada projeto tem um índice em `.agent/artefatos/`, e **só o índice entra no
> prompt** (com teto `MAX_CONTEXTO`) — o agente abre os artefatos sob demanda.
> É o espírito do item 3 resolvido por outro caminho, e melhor que o descrito:
> em vez de comprimir a saída depois, não se carrega o que não foi pedido. O
> agente é convidado a registrar o que aprendeu, **com o padrão explícito em
> "não escreva nada"** — sem isso ele registra em toda tarefa e o índice vira
> ruído.

---

## 8. Central de Artefatos do Projeto

Cada tarefa gera e vincula seus próprios artefatos de forma rastreável:
* **Diffs Unificados (`git.diff`):** Linhas adicionadas e removidas prontas para inspeção.
* **Mockups & Imagens:** Telas geradas em HTML ou imagens renderizadas visíveis em galeria integrada.
* **Logs de Execução (`execution.log`):** Saída completa do terminal gravada em arquivo independente do chat.
* **Sumários de Entrega (`walkthrough.md`):** Relatório de validação e testes executados.

> **Realidade — diffs e galeria sim; os dois arquivos nomeados, não**
>
> Diffs ✅ e galeria ✅ (mermaid é desenhado, HTML abre em iframe, imagens
> servidas pelo backend porque o navegador bloqueia acesso direto ao disco).
> `execution.log` ⚪ — os logs existem e são transmitidos por WebSocket, mas não
> no arquivo nomeado aqui. `walkthrough.md` ⚪ — não existe.
>
> **Onde os artefatos moram mudou.** Esta seção fala em artefatos "da tarefa".
> Hoje eles ficam em `.agent/artefatos/` **no repositório do projeto**, e
> pertencem à tarefa e ao projeto sem sincronização: é o mesmo arquivo, e o
> merge é a promoção.
>
> Duas armadilhas desta área, descobertas depois: abrir a aba de diff **cria um
> commit** na branch da tarefa (auto-snapshot); e o agente **nem sempre salva
> onde mandaram** — pedem para ele subir o docker, ele navega para a pasta do
> compose e passa a salvar lá. Por isso `listar_amplo` procura além da pasta da
> tarefa e **marca** o que veio de fora, em vez de simplesmente não achar.

---

## 9. Estrutura de Diretórios e Execução

O projeto reside em `C:\Users\alex.asbp\.gemini\antigravity\scratch\agent-orchestrator`:
* `backend/`: FastAPI, SQLAlchemy/SQLite, Pydantic, WebSockets, Git Service, Runner Service.
* `frontend/`: React, Vite, Tailwind CSS, Lucide Icons, Kanban, Diff Viewer, Task Drawer.
* `docs/mockups/`: Protótipo visual em HTML e especificações de interface.
* `run.py` / `start.bat`: Scripts de inicialização automática em 1 clique para o Windows.

> **🟡 Realidade — este caminho não existe mais**
>
> `C:\Users\alex.asbp\.gemini\antigravity\scratch\agent-orchestrator` é de onde
> o projeto nasceu. Ele foi movido, e o link que esta spec faz para si mesma
> (no plano em `docs/plans/`) aponta para lá — está quebrado.
>
> A estrutura em si se manteve, com uma camada a mais que a spec não listava:
> `backend/app/{api,services,core,models,websockets}` — em especial
> `websockets/` e `core/`, que não aparecem aqui.
>
> Os dados locais (`orchestrator.db`, `uploads/`, `.env`, `.worktrees/`) são
> ignorados pelo git e **nunca devem ser commitados**: contêm os caminhos e o
> histórico dos projetos do usuário.

---

## 10. Estratégia de Testes

* **Testes Automatizados Backend (`pytest`):**
  * Teste do ciclo de vida da tarefa (`TaskStateMachine`).
  * Teste de criação e remoção de Git Worktrees em repositório temporário.
  * Teste de isolamento de roteamento dos WebSockets.
  * Teste de detecção e execução de subprocessos locais.
  * Teste de rotas REST e persistência no SQLite.
* **Testes Frontend:**
  * Build e typecheck (`npm run build`).
  * Renderização de cards no Kanban, navegação por abas e abertura de drawers.

> **Realidade — superado: 216 testes no backend, 5 no frontend**
>
> As cinco famílias pedidas estão cobertas: `test_card_states.py`,
> `test_git_service.py`, `test_dashboard_events.py`, `test_runner_service.py`,
> `test_api.py`. Acima delas cresceu uma camada que a spec não previa — **testes
> de regressão nomeados pelo sintoma do bug que corrigiram**:
> `test_worktree_nao_destroi.py`, `test_sessao_reusada_mata_execucao.py`,
> `test_artefato_de_fora_abre.py`, `test_merge_preserva_trabalho.py`. Vários
> deles guardam no topo a **mensagem de erro literal** que o CLI gravou no log
> do usuário.
>
> A convenção que saiu disso: cada defeito corrigido ganha um teste cujo nome
> descreve o sintoma (`test_pid_reciclado_nao_e_confundido_com_o_agente`), e a
> suíte precisa continuar passando inteira.
>
> **Um limite que vale registrar.** Os testes de continuidade de sessão mockam
> `create_subprocess_exec`: provam que o comando montado está certo, **não** que
> o Claude Code retome a sessão entre processos distintos — a execução roda
> desacoplada e o chat roda noutro processo. Só um teste de integração real
> confirmaria. Verde não é prova de tudo; é prova daquilo.
>
> `backend/venv/Scripts/python.exe -m pytest tests -q` leva ~3,5 min, dos quais
> ~2 min são um único teste (`test_api_create_project_and_task`, no passo de
> chat que percorre os CLIs até o timeout).

