# Spec de 08/10 × Código de hoje

**Data da análise:** 13/10/2026
**Spec analisada:** [docs/specs/2026-10-08-agent-orchestrator-design.md](specs/2026-10-08-agent-orchestrator-design.md)
**Método:** cada promessa da spec foi procurada no código. Nada foi marcado como
pronto sem evidência no arquivo.

Legenda: ✅ entregue · ⚠️ parcial ou diferente do prometido · ❌ não existe ·
➕ existe no código e não estava na spec.

---

## Resumo

A spec foi cumprida em quase tudo que é **infraestrutura** — worktrees, estados,
rotas, WebSocket, persistência, detecção de CLIs. Foi cumprida em quase nada do
que é **economia de tokens** (seção 7.2), e a peça que a própria spec elege como
um dos cinco problemas a resolver — o *Prompt Refiner* — existe como casca.

Em compensação, o código tem hoje subsistemas inteiros que a spec não previu
(importação do Antigravity, reconciliação de processos, base de conhecimento do
projeto, terminal), e em três pontos ele contraria a spec **porque a spec estava
errada**. Esses três estão marcados abaixo e valem mais que os acertos.

---

## 1. Problemas que o sistema se propôs a resolver (§1.1)

| # | Promessa | Status | Evidência |
|---|---|---|---|
| 1 | Chat isolado por tarefa | ✅ | `models/message.py` — `Message.task_id`; WS por `task_id` |
| 2 | Contexto atômico por tarefa | ✅ | worktree + conversa própria por tarefa |
| 3 | Worktree isolado, zero colisão | ✅ | `services/git_service.py` |
| 4 | **Prompt Refiner** | ❌ | `services/refiner_service.py` é regex, não IA — ver §7.2 |
| 5 | Central de revisão com diff e merge | ✅ | `GET /{id}/diff`, `POST /{id}/merge`, galeria de artefatos |

---

## 2. Modelo de dados (§3)

| Entidade | Status | Observação |
|---|---|---|
| `Project` | ✅ | todos os campos da spec |
| `Task` | ✅ | todos os campos da spec, inclusive `runner_config` JSON |
| `Message` | ✅ | — |
| `Artifact` | ⚠️ | **não é tabela.** Não há `__tablename__ = "artifacts"`. Artefatos são descobertos varrendo o disco em `artifact_service.py` |

A decisão de não persistir artefato em banco é defensável — quem produz o arquivo
é o agente, no disco, e o banco ficaria mentindo assim que ele salvasse algo fora
do esperado (foi exatamente o bug que gerou `test_artefato_de_fora_abre.py`). Mas
é uma divergência da spec que nunca foi registrada.

---

## 3. Ciclo de vida (§4)

Os sete estados existem exatamente como especificados em `TaskStatus`. Três
divergências, e as três são o código corrigindo a spec:

| Promessa da spec | O que o código faz | Por quê |
|---|---|---|
| O card mostra o `status` do banco | Mostra `card_state`, **derivado do processo real** | Um agente morto ficaria "Rodando" para sempre. Ver `CLAUDE.md` |
| `git worktree add -b task/{id}` toda vez | `create_worktree` **reaproveita** worktree válida | A versão literal da spec apagava o trabalho do agente a cada ▶ Rodar (commit `08fc063`) |
| `git diff main..task/{id}` | Usa `git_service.branch_base`, que descobre o ramo | Nem todo projeto chama o ramo principal de `main` |

> Essas três linhas são a parte mais importante deste documento. Quem ler só a
> spec e "corrigir" o código para obedecê-la reintroduz três bugs reais.

---

## 4. API e WebSocket (§5)

**Rotas REST:** as 10 da spec existem, todas. ✅

**Rotas que a spec não previu (➕):** `/import-antigravity`,
`/import-antigravity-bulk`, `/{id}/sync-antigravity`, `/sync-all`,
`/{id}/artifacts` (+ `/raw`), `/{id}/knowledge-proposals`, `/{id}/terminal`,
`/{id}/upload`, `/refresh-states`, `/all`, `DELETE /{id}`.

São mais rotas novas do que rotas especificadas. O sistema cresceu bem além do
documento, e o documento não acompanhou.

**Eventos WebSocket:** ⚠️ os nomes divergem.

| Spec | Código |
|---|---|
| `LOG_LINE` | `LOG` |
| `STATUS_CHANGE` | `STATUS` |
| `STREAM_CHUNK` | não existe |
| `ERROR` | não existe (erro vai como `LOG`) |
| — | ➕ `MESSAGE`, `TASK_BUSY`, `TASK_CREATED`, `TASK_UPDATED`, `TASK_DELETED`, `TASKS_IMPORTED` |

A spec também diz que o cliente envia `STOP` pelo WebSocket; na prática parar é
`POST /{id}/stop`. Nada quebrado — mas a spec descreve um protocolo que não é o
que está no ar.

---

## 5. Resiliência no Windows (§6)

| Promessa | Status | Evidência |
|---|---|---|
| Matar árvore de processos (`taskkill /F /T /PID`) | ✅ | `runner_service.py:217,220,395` — tenta `psutil` e cai para `taskkill` |
| Limpeza de worktree com retentativa | ✅ | `git_service.py` |
| Detecção de conflito de merge | ✅ | `tasks.py:946` — HTTP 409; `git_service.py:267` aborta para manter a main limpa |
| **Resolução de conflito assistida por IA** | ❌ | não existe |
| Persistência total após reinício | ✅ **e além** | `run_registry` + `run_wrapper` + `reconcile`: o agente sobrevive ao restart do uvicorn, o que a spec nem pediu |

---

## 6. CLIs e configuração (§7.1)

| Promessa | Status |
|---|---|
| Detectar `claude.cmd` e `agy` no PATH | ✅ `core/cli_paths.py`, `assistant_service._find_claude_cmd` |
| `CLAUDE_PATH` / `AGY_PATH` / API keys no painel | ✅ `api/settings.py` |
| Seletor de motor por tarefa | ✅ `runner_type` + `runner_config` |

Única seção da spec entregue integralmente.

---

## 7. Economia de tokens (§7.2) — a seção não entregue

| # | Promessa | Status | O que existe de fato |
|---|---|---|---|
| 1 | Prompt caching estratégico (70–90% de economia) | ❌ | nenhuma ocorrência de `cache_control` no backend |
| 2 | Context pruning: passar só 2–5 arquivos afetados | ❌ | o refiner escolhe arquivos por substring e erra; e a rota `/refine` varre **a árvore inteira** do projeto para montar a lista — o oposto da promessa |
| 3 | Compressão de saída via `walkthrough.md` | ❌ | nenhuma ocorrência de `walkthrough` ou `execution.log` no backend |
| 4 | Injeção seletiva de skills | ❌ | nenhuma ocorrência de `skill` no backend |

**Mas:** existe uma peça de economia de contexto que a spec **não** previu e que
funciona — a base de conhecimento do projeto (`artifact_service`). Só o índice
entra no prompt; os artefatos o agente abre sob demanda
(`contexto_para_prompt`, com teto `MAX_CONTEXTO`). É o item 3 da spec resolvido
por outro caminho, melhor que o descrito.

---

## 8. Central de artefatos (§8)

| Promessa | Status |
|---|---|
| Diffs unificados | ✅ |
| Galeria de mockups e imagens | ✅ `.html` → `mockup`, `.png/.jpg` → `imagem` |
| `execution.log` em arquivo independente | ⚠️ logs existem e são transmitidos por WS; o arquivo nomeado da spec, não |
| `walkthrough.md` de entrega | ❌ |

---

## 9. Estrutura de diretórios (§9)

⚠️ A spec aponta para `C:\Users\alex.asbp\.gemini\antigravity\scratch\agent-orchestrator`.
O projeto não mora mais lá. O link interno da spec para si mesma também está
quebrado por isso.

---

## 10. Testes (§10)

✅ **Superado.** A spec pede cinco famílias de teste no backend; o repositório tem
41 arquivos de teste. As famílias pedidas estão cobertas (`test_card_states.py`,
`test_git_service.py`, `test_dashboard_events.py`, `test_runner_service.py`,
`test_api.py`), e há uma camada inteira de testes de regressão que a spec não
previa — cada um nomeado pelo sintoma do bug que corrigiu
(`test_worktree_nao_destroi.py`, `test_sessao_reusada_mata_execucao.py`).

---

## O que fazer com este documento

Três conclusões práticas:

1. **A spec está desatualizada, não errada no espírito.** Ela descreve bem o que o
   sistema é. O que ela não tem é o que o sistema aprendeu depois — e o que ela
   tem de literal (worktree, `main`, nomes de evento) em três pontos está errado.
2. **A seção 7.2 é a dívida real.** Quatro promessas, zero entregues. E a primeira
   peça da cadeia é o refiner: sem ele identificar os arquivos de verdade, o
   context pruning não tem como existir.
3. **O que vale mais que a spec hoje é o `CLAUDE.md`.** A seção "Armadilhas que já
   custaram caro" tem o conhecimento que a spec nunca teve, porque só se aprende
   depois de o bug acontecer.
