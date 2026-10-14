import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Project, Task } from './types';
import { api } from './services/api';
import { useDashboardWebSocket } from './hooks/useDashboardWebSocket';
import { Sidebar } from './components/Sidebar';
import { KanbanBoard } from './components/KanbanBoard';
import { TaskDrawer } from './components/TaskDrawer';
import { ImportConversationModal } from './components/ImportConversationModal';
import { Plus, Shield, Sparkles, FolderPlus, X, Key, Settings, Check, RefreshCw } from 'lucide-react';

export default function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Modals state
  const [isNewProjectModalOpen, setIsNewProjectModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectPath, setNewProjectPath] = useState('');

  const [isNewTaskModalOpen, setIsNewTaskModalOpen] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState('');
  const [newTaskPrompt, setNewTaskPrompt] = useState('');
  // Padrão no Claude: o "assistente integrado" não escreve código, e tê-lo
  // como padrão fazia toda tarefa nova nascer sem conseguir implementar nada.
  const [newTaskRunner, setNewTaskRunner] = useState('claude');

  const [isImportModalOpen, setIsImportModalOpen] = useState(false);

  // IA Settings Modal
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [settingsStatus, setSettingsStatus] = useState<{
    has_gemini_key: boolean;
    has_anthropic_key: boolean;
    has_antigravity?: boolean;
    antigravity_status?: string;
    gemini_key_preview?: string;
  }>({ has_gemini_key: false, has_anthropic_key: false, has_antigravity: false });
  const [geminiKeyInput, setGeminiKeyInput] = useState('');
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsSuccess, setSettingsSuccess] = useState(false);

  // Global Sync States
  const [isSyncingAll, setIsSyncingAll] = useState(false);
  const [syncAllFeedback, setSyncAllFeedback] = useState<string | null>(null);
  const [autoSyncEnabled, setAutoSyncEnabled] = useState(true);

  // Carrega lista inicial de projetos
  const loadProjects = async () => {
    try {
      const data = await api.getProjects();
      setProjects(data);
      if (data.length > 0 && !activeProjectId) {
        setActiveProjectId(data[0].id);
      }
    } catch (err) {
      console.error('Failed to load projects', err);
    }
  };

  // Carrega tarefas do projeto ativo — ou de todos, quando '__ALL__'
  const loadTasks = async (projId: string) => {
    try {
      const data = projId === '__ALL__' ? await api.getAllTasks() : await api.getTasks(projId);
      setTasks(data);
    } catch (err) {
      console.error('Failed to load tasks', err);
    }
  };

  const loadSettings = async () => {
    try {
      const s = await api.getSettings();
      setSettingsStatus(s);
    } catch (err) {
      console.error('Failed to load settings', err);
    }
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingSettings(true);
    try {
      const updated = await api.updateSettings({ gemini_api_key: geminiKeyInput });
      setSettingsStatus(updated);
      setSettingsSuccess(true);
      setTimeout(() => {
        setSettingsSuccess(false);
        setIsSettingsModalOpen(false);
      }, 1500);
    } catch (err: any) {
      alert(`Erro ao salvar chave: ${err.message || 'Falha ao salvar'}`);
    } finally {
      setSavingSettings(false);
    }
  };

  useEffect(() => {
    loadProjects();
    loadSettings();
  }, []);

  useEffect(() => {
    if (activeProjectId) {
      loadTasks(activeProjectId);
      setSelectedTask(null);
    }
  }, [activeProjectId]);

  // Recarrega quando o backend avisa que algo mudou — em vez de esperar
  // o ciclo de 20s. A ref evita reconectar o socket a cada render.
  const activeProjectRef = useRef(activeProjectId);
  useEffect(() => {
    activeProjectRef.current = activeProjectId;
  }, [activeProjectId]);

  const { connected: liveConnected } = useDashboardWebSocket(
    useCallback(() => {
      if (activeProjectRef.current) loadTasks(activeProjectRef.current);
    }, [])
  );

  const handleRefreshStates = async () => {
    if (isRefreshing) return;
    setIsRefreshing(true);
    try {
      const res = await api.refreshStates();
      if (activeProjectId) await loadTasks(activeProjectId);
      const msg =
        res.fixed.length > 0
          ? `${res.checked} verificadas · ${res.fixed.length} corrigida(s)`
          : `${res.checked} verificadas · tudo certo`;
      setSyncAllFeedback(msg);
      setTimeout(() => setSyncAllFeedback(null), 4000);
    } catch (err: any) {
      alert(`⚠️ Falha ao verificar: ${err.message || 'erro desconhecido'}`);
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleSyncAllTasks = async (isManual = true) => {
    if (isSyncingAll) return;
    setIsSyncingAll(true);
    try {
      const res = await api.syncAllTasks(activeProjectId || undefined);
      if (res.tasks_updated > 0 || res.total_messages_synced > 0) {
        if (activeProjectId) {
          loadTasks(activeProjectId);
        }
        setSyncAllFeedback(`${res.total_messages_synced} nova(s) resposta(s) em ${res.tasks_updated} tarefa(s)!`);
        setTimeout(() => setSyncAllFeedback(null), 4000);
      } else if (isManual) {
        setSyncAllFeedback(res.tasks_checked > 0 ? 'Todas as tarefas sincronizadas.' : 'Nenhuma tarefa vinculada.');
        setTimeout(() => setSyncAllFeedback(null), 3000);
      }
    } catch (err: any) {
      if (isManual) {
        setSyncAllFeedback('Erro ao sincronizar tarefas.');
        setTimeout(() => setSyncAllFeedback(null), 3000);
      }
    } finally {
      setIsSyncingAll(false);
    }
  };

  // Auto-sync suave em segundo plano (a cada 20 segundos)
  useEffect(() => {
    if (!autoSyncEnabled || !activeProjectId) return;
    const interval = setInterval(() => {
      handleSyncAllTasks(false);
    }, 20000);
    return () => clearInterval(interval);
  }, [autoSyncEnabled, activeProjectId, isSyncingAll]);

  const activeProject = projects.find((p) => p.id === activeProjectId);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProjectName || !newProjectPath) return;
    try {
      const created = await api.createProject(newProjectName, newProjectPath);
      setProjects((prev) => [...prev, created]);
      setActiveProjectId(created.id);
      setIsNewProjectModalOpen(false);
      setNewProjectName('');
      setNewProjectPath('');
    } catch (err: any) {
      alert(`Erro ao criar projeto: ${err.message || 'Verifique o caminho do diretório Git'}`);
    }
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeProjectId || !newTaskTitle || !newTaskPrompt) return;
    try {
      const runnerType = newTaskRunner === 'assistant' ? 'DIRECT_API' : 'SUBPROCESS_CLI';
      const created = await api.createTask(
        activeProjectId,
        newTaskTitle,
        newTaskPrompt,
        runnerType,
        { cli: newTaskRunner }
      );
      setTasks((prev) => [...prev, created]);
      setIsNewTaskModalOpen(false);
      setNewTaskTitle('');
      setNewTaskPrompt('');
      setSelectedTask(created);
    } catch (err: any) {
      alert(`Erro ao criar tarefa: ${err.message || 'Falha na requisição'}`);
    }
  };

  const handleTaskUpdated = (updated: Task) => {
    setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
    setSelectedTask(updated);
  };

  const handleTaskDeleted = (taskId: string) => {
    setTasks((prev) => prev.filter((t) => t.id !== taskId));
    if (selectedTask?.id === taskId) {
      setSelectedTask(null);
    }
  };

  const handleTaskImported = (task: Task) => {
    setTasks((prev) => [task, ...prev]);
    setSelectedTask(task);
  };

  const handleProjectUpdated = (updated: Project) => {
    setProjects((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  };

  return (
    <div className="h-screen flex flex-col bg-[#090a0f] text-slate-100 overflow-hidden text-sm">
      {/* Topbar */}
      <header className="h-14 border-b border-[#262a3b] bg-[#12141c] px-5 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-blue-600/20 border border-blue-500/40 flex items-center justify-center font-bold text-blue-400">
              AO
            </div>
            <div>
              <h1 className="font-semibold text-base tracking-tight leading-tight">Agent Orchestrator</h1>
              <p className="text-[10px] text-[#8a93a8] leading-none">Local-First Multi-Agent Engine</p>
            </div>
          </div>
          <div className="h-5 w-[1px] bg-[#262a3b] mx-1" />
          <div className="text-xs text-[#8a93a8]">
            Projeto Ativo:{' '}
            <strong className="text-white font-medium">
              {activeProject ? activeProject.name : 'Nenhum selecionado'}
            </strong>
          </div>
        </div>

        <div className="flex items-center gap-5">
          {/* Token Economy Badge */}
          <div className="flex items-center gap-2.5 bg-[#090a0f] border border-[#262a3b] px-3 py-1.5 rounded-lg text-xs">
            <Shield size={14} className="text-emerald-400" />
            <div className="flex flex-col text-right">
              <span className="text-[9px] text-[#8a93a8] uppercase font-semibold">Economia de Tokens</span>
              <span className="text-[11px] font-semibold text-emerald-400">⚡ 78% Cached (412k economizados)</span>
            </div>
          </div>

          {/* Botão Configurar IA */}
          <button
            onClick={() => setIsSettingsModalOpen(true)}
            className={`px-3 py-1.5 rounded-lg flex items-center gap-1.5 text-xs font-medium border transition ${
              settingsStatus.has_antigravity || settingsStatus.has_gemini_key
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20'
                : 'border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20'
            }`}
          >
            <Key size={13} />
            <span>
              {settingsStatus.has_antigravity
                ? '✨ Antigravity Pro Ativo'
                : settingsStatus.has_gemini_key
                ? '✨ Gemini API Ativa'
                : '⚙️ Configurar IA'}
            </span>
          </button>

          {activeProjectId && (
            <div className="flex items-center gap-2">
              {syncAllFeedback && (
                <span className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2.5 py-1 rounded-lg font-medium animate-in fade-in duration-200">
                  {syncAllFeedback}
                </span>
              )}

              <button
                onClick={handleRefreshStates}
                disabled={isRefreshing}
                className="bg-[#1a1d2c] hover:bg-[#23273a] text-emerald-300 hover:text-emerald-200 border border-emerald-500/30 hover:border-emerald-500/60 font-medium px-3 py-1.5 rounded-lg flex items-center gap-1.5 text-xs shadow-sm transition disabled:opacity-50"
                title="Confere todos os agentes neste instante e corrige estados errados, sem esperar o ciclo automático"
              >
                <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
                <span>{isRefreshing ? 'Verificando...' : 'Verificar agora'}</span>
              </button>

              <button
                onClick={() => handleSyncAllTasks(true)}
                disabled={isSyncingAll}
                className="bg-[#1a1d2c] hover:bg-[#23273a] text-blue-300 hover:text-blue-200 border border-blue-500/30 hover:border-blue-500/60 font-medium px-3 py-1.5 rounded-lg flex items-center gap-1.5 text-xs shadow-sm transition disabled:opacity-50"
                title="Sincronizar respostas do Antigravity em todas as tarefas do projeto de uma só vez"
              >
                <RefreshCw size={13} className={isSyncingAll ? "animate-spin text-blue-400" : "text-blue-400"} />
                <span>{isSyncingAll ? "Sincronizando..." : "Sincronizar Todas"}</span>
              </button>

              <button
                onClick={() => setIsImportModalOpen(true)}
                className="bg-[#1a1d2c] hover:bg-[#23273a] text-purple-300 hover:text-purple-200 border border-purple-500/30 hover:border-purple-500/60 font-medium px-3 py-1.5 rounded-lg flex items-center gap-1.5 text-xs shadow-sm transition"
                title="Vincular uma conversa ativa no Antigravity a este projeto"
              >
                <Sparkles size={13} className="text-purple-400" />
                <span>Importar do Antigravity</span>
              </button>

              <span
                title={
                  liveConnected
                    ? 'Conectado ao painel em tempo real — os cards mudam assim que algo acontece'
                    : 'Sem conexão em tempo real — os cards atualizam a cada 20s'
                }
                className={`flex items-center gap-1.5 text-[10px] font-mono px-2 py-1 rounded-md border ${
                  liveConnected
                    ? 'text-emerald-300 border-emerald-500/30 bg-emerald-500/5'
                    : 'text-[#8a93a8] border-[#262a3b] bg-[#12141c]'
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    liveConnected ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'
                  }`}
                />
                {liveConnected ? 'ao vivo' : 'offline'}
              </span>

              <button
                onClick={() => setIsNewTaskModalOpen(true)}
                className="bg-blue-600 hover:bg-blue-500 text-white font-medium px-3.5 py-1.5 rounded-lg flex items-center gap-1.5 text-xs shadow-sm transition"
              >
                <Plus size={14} /> Nova Tarefa
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Main Layout */}
      <div className="flex-1 flex overflow-hidden">
        <Sidebar
          projects={projects}
          activeProjectId={activeProjectId}
          onSelectProject={(id) => setActiveProjectId(id)}
          onOpenNewProject={() => setIsNewProjectModalOpen(true)}
          onProjectUpdated={handleProjectUpdated}
        />

        <main className="flex-1 overflow-x-auto p-5 custom-scroll bg-[#090a0f]">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">
                {activeProject ? `${activeProject.name} — Quadro de Tarefas` : 'Selecione um projeto'}
              </h2>
              <p className="text-xs text-[#8a93a8]">
                Tarefas operando em worktrees isoladas. Zero colisão de arquivos ou contexto.
              </p>
            </div>

            {activeProjectId && (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setAutoSyncEnabled(!autoSyncEnabled)}
                  title={
                    autoSyncEnabled
                      ? 'Auto-sincronização ativa a cada 20s. Clique para pausar.'
                      : 'Auto-sincronização pausada. Clique para reativar.'
                  }
                  className={`flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full border transition ${
                    autoSyncEnabled
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20'
                      : 'bg-slate-800/80 border-slate-700 text-slate-400 hover:text-slate-300 hover:bg-slate-800'
                  }`}
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${
                      autoSyncEnabled ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'
                    }`}
                  />
                  <span>{autoSyncEnabled ? 'Auto-sync ativo (20s)' : 'Auto-sync pausado'}</span>
                </button>
              </div>
            )}
          </div>

          <KanbanBoard tasks={tasks} onSelectTask={(task) => setSelectedTask(task)} />
        </main>

        {selectedTask && (
          // A key força remontar ao trocar de tarefa. Sem ela o React
          // reaproveitava a instância e TODO o estado interno atravessava a
          // troca — mensagens, logs, diff, anexos e rascunho do campo —, então
          // o usuário via o chat de uma tarefa dentro de outra.
          <TaskDrawer
            key={selectedTask.id}
            task={selectedTask}
            onClose={() => setSelectedTask(null)}
            onTaskUpdated={handleTaskUpdated}
            onTaskDeleted={handleTaskDeleted}
          />
        )}
      </div>

      {/* Modal: Novo Projeto */}
      {isNewProjectModalOpen && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-[#12141c] border border-[#262a3b] rounded-xl p-5 w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-white text-sm flex items-center gap-2">
                <FolderPlus size={16} className="text-blue-400" /> Cadastrar Novo Projeto
              </h3>
              <button onClick={() => setIsNewProjectModalOpen(false)} className="text-[#8a93a8] hover:text-white">
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleCreateProject} className="space-y-3 text-xs">
              <div>
                <label className="block text-[#8a93a8] mb-1 font-medium">Nome do Projeto</label>
                <input
                  type="text"
                  required
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  placeholder="Ex: E-commerce Core"
                  className="w-full bg-[#090a0f] border border-[#262a3b] rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-[#8a93a8] mb-1 font-medium">Caminho da Pasta Git (Windows)</label>
                <input
                  type="text"
                  required
                  value={newProjectPath}
                  onChange={(e) => setNewProjectPath(e.target.value)}
                  placeholder="Ex: C:\dev\ecommerce"
                  className="w-full bg-[#090a0f] border border-[#262a3b] rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsNewProjectModalOpen(false)}
                  className="px-3 py-1.5 rounded text-[#8a93a8] hover:text-white"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="bg-blue-600 hover:bg-blue-500 text-white font-medium px-4 py-1.5 rounded-lg"
                >
                  Cadastrar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Nova Tarefa */}
      {isNewTaskModalOpen && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-[#12141c] border border-[#262a3b] rounded-xl p-5 w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-white text-sm flex items-center gap-2">
                <Plus size={16} className="text-blue-400" /> Criar Nova Tarefa
              </h3>
              <button onClick={() => setIsNewTaskModalOpen(false)} className="text-[#8a93a8] hover:text-white">
                <X size={16} />
              </button>
            </div>
            <form onSubmit={handleCreateTask} className="space-y-3 text-xs">
              <div>
                <label className="block text-[#8a93a8] mb-1 font-medium">Título Resumido</label>
                <input
                  type="text"
                  required
                  value={newTaskTitle}
                  onChange={(e) => setNewTaskTitle(e.target.value)}
                  placeholder="Ex: Criar tela de checkout com cupom"
                  className="w-full bg-[#090a0f] border border-[#262a3b] rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-[#8a93a8] mb-1 font-medium">
                  Ideia Bruta (Não se preocupe com formato, a IA lapida depois)
                </label>
                <textarea
                  rows={4}
                  required
                  value={newTaskPrompt}
                  onChange={(e) => setNewTaskPrompt(e.target.value)}
                  placeholder="Ex: Quero um componente de resumo de carrinho com validação de cupom e exibição de frete calculado..."
                  className="w-full bg-[#090a0f] border border-[#262a3b] rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-[#8a93a8] mb-1 font-medium">Motor / Runner do Agente</label>
                <select
                  value={newTaskRunner}
                  onChange={(e) => setNewTaskRunner(e.target.value)}
                  className="w-full bg-[#090a0f] border border-[#262a3b] rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="claude">✅ Claude Code CLI (Recomendado — escreve código no worktree)</option>
                  <option value="agy">✅ Antigravity CLI (agy — conta Google, sem API key)</option>
                  <option value="assistant">💬 Só conversar (não escreve código)</option>
                  <option value="custom">Comando Customizado</option>
                </select>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsNewTaskModalOpen(false)}
                  className="px-3 py-1.5 rounded text-[#8a93a8] hover:text-white"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="bg-blue-600 hover:bg-blue-500 text-white font-medium px-4 py-1.5 rounded-lg"
                >
                  Criar Tarefa
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Configurar Chaves de IA */}
      {isSettingsModalOpen && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
          <div className="bg-[#12141c] border border-[#262a3b] rounded-xl p-5 w-full max-w-lg shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-white text-sm flex items-center gap-2">
                <Key size={16} className="text-amber-400" /> Configurar Inteligência Artificial (LLM)
              </h3>
              <button onClick={() => setIsSettingsModalOpen(false)} className="text-[#8a93a8] hover:text-white">
                <X size={16} />
              </button>
            </div>

            {settingsStatus.has_antigravity ? (
              <div className="p-3 bg-emerald-500/10 border border-emerald-500/25 rounded-lg text-xs text-emerald-200 mb-4 leading-relaxed flex items-start gap-2.5">
                <Check size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                <div>
                  <strong className="text-emerald-300">Google Antigravity CLI Ativo!</strong>
                  <p className="text-[11px] text-emerald-300/80 mt-1">
                    Seu Orquestrador está conectado à sua conta <strong>Google Pro</strong> via <code>agentapi</code> nativo. O chat e as tarefas usam o modelo oficial sem necessidade de chave externa de API.
                  </p>
                </div>
              </div>
            ) : (
              <div className="p-3 bg-blue-600/10 border border-blue-500/20 rounded-lg text-xs text-blue-200 mb-4 leading-relaxed">
                💡 Para que o modelo converse com você com inteligência plena e gere códigos em tempo real, conecte sua chave do <strong>Google Gemini</strong>. É 100% gratuita no Google AI Studio.
              </div>
            )}

            <form onSubmit={handleSaveSettings} className="space-y-4 text-xs">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[#8a93a8] font-medium">Google Gemini API Key (Recomendado - Gratuito)</label>
                  {settingsStatus.has_gemini_key && (
                    <span className="text-[10px] text-emerald-400 font-semibold flex items-center gap-1">
                      <Check size={11} /> Conectada ({settingsStatus.gemini_key_preview})
                    </span>
                  )}
                </div>
                <input
                  type="password"
                  value={geminiKeyInput}
                  onChange={(e) => setGeminiKeyInput(e.target.value)}
                  placeholder={settingsStatus.has_gemini_key ? 'Substituir chave existente (AIzaSy...)' : 'Cole sua chave AIzaSy...'}
                  className="w-full bg-[#090a0f] border border-[#262a3b] rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500 font-mono text-[11px]"
                />
                <p className="text-[10px] text-[#8a93a8] mt-1">
                  👉 Obtenha sua chave gratuita em:{' '}
                  <a
                    href="https://aistudio.google.com/app/apikey"
                    target="_blank"
                    rel="noreferrer"
                    className="text-blue-400 hover:underline"
                  >
                    https://aistudio.google.com/app/apikey
                  </a>
                </p>
              </div>

              {settingsSuccess && (
                <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
                  <Check size={13} /> Chave salva com sucesso! O modelo Gemini já está ativo no chat.
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2 border-t border-[#262a3b]">
                <button
                  type="button"
                  onClick={() => setIsSettingsModalOpen(false)}
                  className="px-3 py-1.5 rounded text-[#8a93a8] hover:text-white"
                >
                  Fechar
                </button>
                <button
                  type="submit"
                  disabled={savingSettings || !geminiKeyInput.trim()}
                  className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-medium px-4 py-1.5 rounded-lg flex items-center gap-1.5 transition"
                >
                  {savingSettings ? 'Salvando...' : 'Salvar Chave'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal de Importação do Antigravity */}
      {activeProject && (
        <ImportConversationModal
          project={activeProject}
          isOpen={isImportModalOpen}
          onClose={() => setIsImportModalOpen(false)}
          onTaskImported={handleTaskImported}
          onBulkImported={() => activeProjectId && loadTasks(activeProjectId)}
        />
      )}
    </div>
  );
}

