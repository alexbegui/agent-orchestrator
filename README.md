# Agent Orchestrator

Plataforma local-first para orquestração de múltiplos agentes de IA e múltiplos projetos simultâneos, eliminando sobrecarga cognitiva, conversas intercaladas e inchaço de contexto.

---

## 🎯 Problemas Resolvidos
1. **Zero Colisão de Conversas:** Cada tarefa opera em uma thread 100% isolada. Mesmo com 4 agentes finalizando tarefas ao mesmo tempo, nenhuma mensagem interrompe a sua conversa atual.
2. **Isolamento Físico de Arquivos (Git Worktrees):** Múltiplas tarefas no mesmo projeto rodam em pastas de trabalho separadas (`.worktrees/task-{id}`). Um agente nunca sobrescreve o código de outro.
3. **Economia Máxima de Tokens:**
   - **Context Pruning:** Seleção atômica apenas dos arquivos necessários.
   - **Prompt Caching:** Estrutura otimizada para cache de prompt no Claude e Gemini (economia de 70% a 90%).
   - **Compressão de Saída:** Diffs e relatórios salvos no disco, sem despejo de milhares de linhas no histórico de chat.
4. **Lapidador de Prompts Integrado:** Transforma ideias brutas em especificações técnicas completas antes de rodar código.
5. **Central de Revisão (Human-in-the-Loop):** Visualizador de Git Diffs e botão de **"✓ Aprovar & Merge"** em 1 clique.

---

## 🚀 Como Iniciar no Windows

### Modo 1: Clique Duplo
Basta dar dois cliques no arquivo:
```cmd
start.bat
```

### Modo 2: Via Terminal
```powershell
py run.py
```
O painel abrirá automaticamente em seu navegador padrão em: **`http://localhost:8000`**.

---

## 🧪 Suíte de Testes Automatizados (TDD)
Para rodar todos os testes de backend:
```powershell
backend\venv\Scripts\pytest backend\tests -v
```

Para recompilar o frontend React:
```powershell
cd frontend
npm run build
```
