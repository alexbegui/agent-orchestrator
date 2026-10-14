# Agent Orchestrator

## Visão geral

Orquestrador local de agentes de IA. O usuário descreve uma tarefa, escolhe um motor
(Claude Code CLI ou `agy`/Antigravity CLI), e o orquestrador despacha o agente **dentro de um
git worktree isolado** do projeto alvo. O trabalho aparece num painel kanban e o usuário
revisa o diff antes de aprovar o merge.

**Stack**: FastAPI + SQLAlchemy + SQLite · React 18 + TypeScript + Vite + Tailwind ·
WebSocket para tempo real. Fortemente orientado a **Windows**.

**Estrutura**: `backend/app/{api,services,core,models,websockets}` · `frontend/src/{components,hooks,services,types}` ·
`backend/tests/` (270 testes) · `frontend/src/**/*.test.tsx` (vitest, 17 testes) · `docs/{specs,plans,mockups}`.

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
  a cada ▶ Rodar. (história completa abaixo)
- **Nunca suponha que o ramo base é `main`.** Use `git_service.branch_base`, que descobre.
  (história completa abaixo)
- **Nunca declare sucesso sem evidência.** Um serviço já declarava "[Sucesso] Tarefa pronta!"
  sem ter implementado nada. Se não deu para verificar, diga que não deu.
- **PID sozinho não identifica processo** no Windows, que recicla PIDs. Sempre compare também
  o instante de início.
- Abrir a aba de diff **cria um commit** na branch da tarefa (auto-snapshot).
- **Nunca passe texto multilinha como argumento para um `.cmd`.** O `claude.cmd` é
  batch, e o cmd.exe **corta o argumento na primeira quebra de linha** — medido: 90
  caracteres em 6 linhas entraram, 1 linha saiu. O agente recebia só o começo do
  prompt, terminava com `rc=0` sem fazer nada, e o card dizia "Entregou". Não há
  escape que resolva: o prompt do Claude Code vai pela **entrada padrão**
  (`run_wrapper --stdin`). O `agy` é `.exe` e não tem esse problema. O chat segue a
  mesma regra (`_comunicar_com_teto(entrada=...)`): na primeira mensagem o preâmbulo
  tem `

` antes da pergunta, então ela era descartada inteira e o agente respondia
  algo genérico — defeito silencioso, sem sintoma na tela.
- **O refino usa o CLI da própria tarefa**, com `--json-schema` obrigando o formato
  — sem chave de API, na assinatura que o usuário já paga. Quem refina é o motor que
  vai executar. Os dois CLIs devolvem o objeto no campo `structured_output`, e exigem
  `--output-format json` junto. A API direta continua como opção para quem tem chave
  (~4s contra ~50s do CLI).
- **O refino pode falhar — e falhar é o comportamento certo.** Sem motor nenhum
  ou com resposta inválida, `/refine` devolve 502 e a tarefa fica em `DRAFT`.
  Não acrescente fallback heurístico: a versão antiga era regex, nunca falhava, e
  produzia spec genérica indistinguível de uma spec real. O portão de aprovação
  só vale se o que está atrás dele for genuíno.
- **A árvore mandada à IA vem de `git ls-files`**, nunca de `os.walk`. O walk
  devolvia 4.077 arquivos neste repositório (~72 mil tokens), 3.786 deles na `venv`.
- `CLAUDE_PERMISSION_MODE` é `bypassPermissions` por padrão: o agente executa qualquer comando
  na máquina. O worktree isola arquivos, **não é sandbox de segurança**.

## Os três pontos em que o código contraria a spec de 08/10

A spec (`docs/specs/2026-10-08-agent-orchestrator-design.md`) descreve o caso feliz:
worktree que ainda não existe, projeto que usa `main`, processo que termina direito.
Nestes três pontos o código **desobedece a spec de propósito**, porque obedecê-la
quebrou o sistema em produção. Quem "corrigir" o código para seguir o documento
reintroduz os três bugs. A comparação completa está em `docs/spec-vs-realidade.md`.

### 1. `git worktree add -b` apagava o trabalho do agente

**A spec manda** (§4.3), literal: `git worktree add -b task/{id} .worktrees/{id}`.

**O que acontecia.** Rodar uma tarefa duas vezes é normal — o agente para, o usuário
ajusta, clica ▶ Rodar de novo. Na segunda vez a worktree já existe e o git recusa. A
implementação resolvia do jeito que parece razoável: apagava a pasta e recriava a
branch com `-B`. Cada ▶ Rodar destruía tudo que o agente tinha feito, arquivos soltos
**e commits da branch**.

**O relato que originou.** O usuário disse: *"criei um mapa mental e ele não aparece na
aba Artefatos"*. Um sintoma pequeno — um arquivo não aparece numa aba. Atrás dele
estavam horas de trabalho sendo apagadas a cada clique. Do commit `08fc063`: *"Era a
causa real dos artefatos desaparecerem entre execuções; **o agente não estava mentindo
ao dizer que salvou**."* O custo real do bug foi o usuário passar a desconfiar do agente.

**Como ficou.** `git_service.create_worktree` devolve a worktree existente quando ela é
válida — e "válida" não é "a pasta existe", é `git rev-parse --is-inside-work-tree`
rodando dentro dela (`_worktree_valida`). A criação tenta `worktree add <path> <branch>`
**sem** `-b` primeiro, reaproveitando a branch se ela já tiver trabalho, e só cai no `-b`
quando o git diz que a branch não existe. A spec põe o `-b` como regra; o código põe
como exceção. **Trava:** `test_worktree_nao_destroi.py` — `test_rodar_de_novo_preserva_arquivo_nao_commitado`,
`test_rodar_de_novo_preserva_commit_da_tarefa`, mais `test_primeira_vez_cria_normalmente`
e `test_pasta_quebrada_e_recriada`, que existem para o conserto não virar o bug oposto.

### 2. `main` não existia no projeto do usuário

**A spec manda** (§4.4): `git diff main..task/{id}`, e `git checkout main` no merge.

**O que acontecia.** O projeto real usa `master`. O estrago tinha dois tempos. Agora:
`git diff main...HEAD` falhava **em silêncio** — sem branch `main` não há diff, e a aba
de artefatos não mostrava o que a tarefa já tinha commitado. Depois: o merge faria
`git checkout main` num repositório sem `main` e **teria falhado na hora de aprovar** —
o pior momento possível, com o trabalho feito e revisado.

**O relato que originou.** O mesmo *"o mapa mental não aparece"*. Um sintoma, três
defeitos. A bomba do merge nunca explodiu: foi encontrada investigando o diff, antes de
alguém tentar aprovar uma tarefa.

**O terceiro defeito, o mais traiçoeiro.** `Project.default_branch` existia e tinha a
resposta — errada. Os três projetos tinham `'main'` gravado: valor padrão do formulário,
nunca conferido contra o disco. O banco estava no formato certo e no conteúdo errado,
então confiar no campo mantinha o bug. Por isso a correção não foi "ler do banco", foi
**descobrir no disco**.

**Como ficou.** `git_service.branch_base` tenta, em ordem de confiabilidade: o que o
remoto declara (`refs/remotes/origin/HEAD`); depois os nomes usuais — `main`, `master`,
`trunk`, `develop`, `desenvolvimento` — mas só os que existem de verdade; por último o
ramo atual do repositório. Cada passo usa `rev-parse --verify`: confirma antes de
devolver, nunca chuta. **Trava:** `test_branch_base.py`, em especial
`test_artefato_commitado_aparece_em_repo_com_master` (o sintoma vivido) e
`test_merge_funciona_em_repo_com_master` (a bomba desarmada).

### 3. O card mentia sobre o agente estar vivo

**A spec assume** (§4), sem nunca escrever: a tarefa tem um `status`, o kanban mostra
esse `status`, logo o banco sabe o que está acontecendo.

**Por que não se sustenta.** O agente é um processo desacoplado (`DETACHED_PROCESS`), e
isso foi deliberado para que reiniciar o uvicorn não matasse trabalho de horas. O preço
é que o servidor não é avisado quando o processo morre. O banco só muda quando alguém
escreve nele; se o processo caiu, travou, ou a máquina hibernou, ninguém escreve. Do
commit `1acaada`: *"agente morto continuava 'Rodando' para sempre"* — e o usuário
esperando um agente que não existe mais.

**Como ficou.** O card mostra `card_state`, calculado a cada resposta a partir do
processo real. O banco virou histórico; a verdade é o processo. A identificação do
processo é **PID + instante de início**, porque o Windows recicla PIDs e matar por PID
puro mataria outro programa. Duas decisões de produto embutidas: *"Te perguntou"* e
*"Entregou"* são estados separados *"porque custam tempos diferentes do usuário"* (um
pede 10 segundos, o outro pede meia hora de revisão); e trabalho sinalizado pelo chat
expira em 15 minutos, senão o card trava para sempre se o servidor cair no meio.
**Trava:** `test_card_states.py` — `test_processo_sumiu_tem_estado_parou`,
`test_verificar_agora_corrige_tarefa_que_morreu_sem_avisar`, e
`test_executando_tem_precedencia_sobre_a_conversa`, que resolve o empate quando o agente
está trabalhando **e** falou no chat (sem a regra, dois estados verdadeiros ao mesmo
tempo dariam resultado aleatório).

## Rodar

```bash
start.bat                                                  # sobe tudo em http://127.0.0.1:8000
start.bat rebuild                                          # força recompilar o frontend
backend/venv/Scripts/python.exe -m pytest tests -q         # testes (a partir de backend/)
```

Dados locais (`orchestrator.db`, `uploads/`, `.env`, `.worktrees/`) são ignorados pelo git e
nunca devem ser commitados — eles contêm os caminhos e o histórico dos projetos do usuário.
