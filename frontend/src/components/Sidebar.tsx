import React, { useState, useMemo } from 'react';
import { Project } from '../types';
import {
  Folder,
  Plus,
  ShieldCheck,
  Pencil,
  X,
  Loader2,
  Layers,
  Terminal as TerminalIcon,
  Search,
  Play,
  RotateCw,
  Square,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { api } from '../services/api';

interface SidebarProps {
  projects: Project[];
  activeProjectId: string | null;
  onSelectProject: (id: string) => void;
  onOpenNewProject: () => void;
  onProjectUpdated?: (updated: Project) => void;
  onProjectsImported?: (imported: Project[]) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  projects,
  activeProjectId,
  onSelectProject,
  onOpenNewProject,
  onProjectUpdated,
  onProjectsImported,
}) => {
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [editName, setEditName] = useState('');
  const [editDevCmd, setEditDevCmd] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [skillsExpanded, setSkillsExpanded] = useState(false);
  const [runningActionProjectId, setRunningActionProjectId] = useState<string | null>(null);

  // Modal de Sincronização / Importação de Projetos do Antigravity
  const [isSyncModalOpen, setIsSyncModalOpen] = useState(false);
  const [discoveredProjects, setDiscoveredProjects] = useState<Array<{ name: string; root_path: string; antigravity_project_id: string; already_imported: boolean }>>([]);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [selectedToImport, setSelectedToImport] = useState<string[]>([]);
  const [isImporting, setIsImporting] = useState(false);

  // Filtragem instantânea de projetos pelo nome ou caminho
  const filteredProjects = useMemo(() => {
    if (!searchQuery.trim()) return projects;
    const q = searchQuery.toLowerCase();
    return projects.filter(
      (p) => p.name.toLowerCase().includes(q) || p.root_path.toLowerCase().includes(q)
    );
  }, [projects, searchQuery]);

  const handleOpenTerminal = async (project: Project) => {
    try {
      await api.openProjectTerminal(project.id);
    } catch (err: any) {
      alert(`⚠️ Não foi possível abrir o terminal: ${err.message || 'falha desconhecida'}`);
    }
  };

  const handleToggleOrRestartService = async (e: React.MouseEvent, project: Project) => {
    e.stopPropagation();
    setRunningActionProjectId(project.id);
    try {
      if (project.is_service_running) {
        // Se estiver rodando, reinicia
        const res = await api.restartProjectService(project.id);
        if (onProjectUpdated) {
          onProjectUpdated({ ...project, is_service_running: res.is_running, service_pid: res.pid });
        }
      } else {
        // Se estiver parado, inicia
        const res = await api.startProjectService(project.id);
        if (onProjectUpdated) {
          onProjectUpdated({ ...project, is_service_running: res.is_running, service_pid: res.pid });
        }
      }
    } catch (err: any) {
      alert(`⚠️ Falha ao gerenciar serviço: ${err.message || 'Erro de execução'}`);
    } finally {
      setRunningActionProjectId(null);
    }
  };

  const handleSaveProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingProject || !editName.trim() || isSaving) return;
    setIsSaving(true);
    try {
      const updated = await api.updateProject(editingProject.id, {
        name: editName.trim(),
        dev_command: editDevCmd.trim(),
      });
      if (onProjectUpdated) {
        onProjectUpdated(updated);
      }
      setEditingProject(null);
    } catch (err: any) {
      alert(`⚠️ Erro ao atualizar projeto: ${err.message || 'Falha ao salvar'}`);
    } finally {
      setIsSaving(false);
    }
  };

  const handleOpenSyncModal = async () => {
    setIsSyncModalOpen(true);
    setIsDiscovering(true);
    try {
      const data = await api.discoverAntigravityProjects();
      setDiscoveredProjects(data);
      // Pré-seleciona os que ainda não foram importados
      const toImport = data.filter((p) => !p.already_imported).map((p) => p.root_path);
      setSelectedToImport(toImport);
    } catch (err: any) {
      alert(`⚠️ Erro ao buscar projetos do Antigravity: ${err.message || 'Falha na comunicação'}`);
    } finally {
      setIsDiscovering(false);
    }
  };

  const handleImportSelected = async () => {
    if (selectedToImport.length === 0 || isImporting) return;
    setIsImporting(true);
    try {
      const targets = discoveredProjects
        .filter((p) => selectedToImport.includes(p.root_path))
        .map((p) => ({
          name: p.name,
          root_path: p.root_path,
          default_branch: 'main',
        }));

      const imported = await api.importAntigravityProjects(targets);
      if (onProjectsImported) {
        onProjectsImported(imported);
      }
      setIsSyncModalOpen(false);
    } catch (err: any) {
      alert(`⚠️ Erro ao importar projetos: ${err.message || 'Falha ao salvar'}`);
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <aside className="w-80 border-r border-[#262a3b] bg-[#12141c] flex flex-col shrink-0">
      {/* Header com Contagem, Botão Novo e Barra de Busca */}
      <div className="p-3.5 border-b border-[#262a3b]">
        <div className="flex items-center justify-between mb-2.5">
          <span className="text-xs font-semibold text-[#8a93a8] uppercase tracking-wider">
            Projetos ({projects.length})
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={handleOpenSyncModal}
              className="p-1 hover:bg-[#1a1d28] rounded text-[#8a93a8] hover:text-purple-400 transition"
              title="Sincronizar Projetos com Antigravity Desktop"
            >
              <RotateCw size={13} />
            </button>
            <button
              onClick={onOpenNewProject}
              className="p-1 hover:bg-[#1a1d28] rounded text-[#8a93a8] hover:text-white transition"
              title="Adicionar Novo Projeto"
            >
              <Plus size={15} />
            </button>
          </div>
        </div>

        {/* Input de Filtro Instantâneo para muitos projetos */}
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-2.5 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filtrar projetos por nome..."
            className="w-full bg-[#090a0f] border border-[#232738] focus:border-blue-500 rounded-lg pl-8 pr-7 py-1.5 text-xs text-white outline-none transition"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-2 top-2 text-slate-500 hover:text-white"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Lista de Projetos (100% da altura flexível) */}
      <div className="flex-1 overflow-y-auto custom-scroll p-2 space-y-1.5">
        {/* Item Global: Todos os Projetos */}
        <div
          onClick={() => onSelectProject('__ALL__')}
          className={`w-full text-left p-2.5 rounded-lg border transition flex items-center gap-2 cursor-pointer ${
            activeProjectId === '__ALL__'
              ? 'bg-[#1a1d28] border-amber-500/50 text-white'
              : 'border-transparent text-[#8a93a8] hover:bg-[#1a1d28] hover:text-white'
          }`}
        >
          <Layers size={14} className="shrink-0 text-amber-400" />
          <span className="font-medium text-xs">Visão Global (Todos os Projetos)</span>
        </div>

        {filteredProjects.length === 0 ? (
          <div className="text-center py-6 text-xs text-slate-500">
            Nenhum projeto encontrado para "{searchQuery}"
          </div>
        ) : (
          filteredProjects.map((p) => {
            const isActive = p.id === activeProjectId;
            const isActing = runningActionProjectId === p.id;
            const isOnline = !!p.is_service_running;

            return (
              <div
                key={p.id}
                onClick={() => onSelectProject(p.id)}
                className={`group relative w-full text-left p-2.5 rounded-lg border transition flex flex-col gap-1.5 cursor-pointer ${
                  isActive
                    ? 'bg-[#181f33] border-blue-500/50 text-white shadow-sm'
                    : 'bg-[#141620] border-transparent text-[#8a93a8] hover:bg-[#1a1d28] hover:text-white'
                }`}
              >
                {/* Linha 1: Nome, Status do Serviço e Contador */}
                <div className="flex items-center justify-between gap-1.5">
                  <div className="font-medium text-xs truncate flex items-center gap-1.5 flex-1">
                    <Folder size={13} className={isActive ? 'text-blue-400' : 'text-slate-400'} />
                    <span className="truncate">{p.name}</span>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {/* Badge Online/Parado */}
                    {isOnline ? (
                      <span className="flex items-center gap-1 text-[9px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-1.5 py-0.5 rounded">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        Online
                      </span>
                    ) : (
                      <span className="text-[9px] text-slate-500 bg-slate-800/80 px-1.5 py-0.5 rounded">
                        Parado
                      </span>
                    )}

                    {p.active_tasks_count > 0 && (
                      <span className="text-[9px] bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded-full font-mono">
                        {p.active_tasks_count}
                      </span>
                    )}
                  </div>
                </div>

                {/* Linha 2: Caminho no disco */}
                <div className="text-[10px] text-slate-500 truncate font-mono">
                  {p.root_path}
                </div>

                {/* Linha 3: Barra de Ações Rápidas (Rodar/Reiniciar, Terminal, Editar) */}
                <div className="flex items-center justify-between pt-1 border-t border-white/5 mt-0.5">
                  <div className="text-[9px] font-mono text-slate-400 truncate max-w-[150px]" title={p.dev_command || 'Comando padrão'}>
                    {p.dev_command || 'npm run dev'}
                  </div>

                  <div className="flex items-center gap-1">
                    {/* Botão de Rodar ou Reiniciar */}
                    <button
                      type="button"
                      disabled={isActing}
                      onClick={(e) => handleToggleOrRestartService(e, p)}
                      title={isOnline ? 'Reiniciar serviço (Parar e subir)' : 'Rodar serviço do projeto'}
                      className={`px-1.5 py-0.5 rounded text-[10px] font-medium flex items-center gap-1 transition ${
                        isOnline
                          ? 'bg-blue-950/80 hover:bg-blue-900 border border-blue-500/40 text-blue-300'
                          : 'bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-500/40 text-emerald-300'
                      }`}
                    >
                      {isActing ? (
                        <Loader2 size={10} className="animate-spin" />
                      ) : isOnline ? (
                        <>
                          <RotateCw size={10} />
                          <span>Reiniciar</span>
                        </>
                      ) : (
                        <>
                          <Play size={10} />
                          <span>Rodar</span>
                        </>
                      )}
                    </button>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleOpenTerminal(p);
                      }}
                      title={`Abrir terminal em ${p.root_path}`}
                      className="p-1 rounded hover:bg-[#262a3b] text-[#8a93a8] hover:text-emerald-300 transition"
                    >
                      <TerminalIcon size={12} />
                    </button>

                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingProject(p);
                        setEditName(p.name);
                        setEditDevCmd(p.dev_command || '');
                      }}
                      title="Configurar Projeto e Comando"
                      className="p-1 rounded hover:bg-[#262a3b] text-[#8a93a8] hover:text-blue-300 transition"
                    >
                      <Pencil size={12} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Seção Skills recolhível no rodapé */}
      <div className="border-t border-[#262a3b] bg-[#0d0f17]">
        <button
          type="button"
          onClick={() => setSkillsExpanded(!skillsExpanded)}
          className="w-full p-2.5 flex items-center justify-between text-xs text-[#8a93a8] hover:text-white transition"
        >
          <span className="font-semibold uppercase tracking-wider text-[10px]">
            Harness & Skills
          </span>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-emerald-400 font-mono">3 Ativas</span>
            {skillsExpanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </div>
        </button>

        {skillsExpanded && (
          <div className="p-3 pt-0 space-y-1.5 text-xs animate-in fade-in duration-150">
            <div className="p-1.5 rounded bg-[#090a0f] border border-[#1c2030] flex items-center justify-between">
              <span className="text-[11px] text-white">ui-ux-pro-max</span>
              <ShieldCheck size={13} className="text-blue-400" />
            </div>
            <div className="p-1.5 rounded bg-[#090a0f] border border-[#1c2030] flex items-center justify-between">
              <span className="text-[11px] text-white">test-driven-development</span>
              <ShieldCheck size={13} className="text-emerald-400" />
            </div>
            <div className="p-1.5 rounded bg-[#090a0f] border border-[#1c2030] flex items-center justify-between">
              <span className="text-[11px] text-white">fastapi-standards</span>
              <ShieldCheck size={13} className="text-purple-400" />
            </div>
          </div>
        )}
      </div>

      {/* Modal: Configurar Projeto e Comando */}
      {editingProject && (
        <div
          className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setEditingProject(null)}
        >
          <div
            className="bg-[#161822] border border-[#2d3247] rounded-xl max-w-sm w-full p-5 shadow-2xl animate-in fade-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold text-white text-sm flex items-center gap-2">
                <Pencil size={15} className="text-blue-400" />
                Configurar Projeto
              </h3>
              <button
                type="button"
                onClick={() => setEditingProject(null)}
                className="text-[#8a93a8] hover:text-white p-1 rounded hover:bg-[#262a3b]"
              >
                <X size={15} />
              </button>
            </div>

            <form onSubmit={handleSaveProject} className="space-y-3.5">
              <div>
                <label className="block text-[11px] font-medium text-[#8a93a8] uppercase mb-1">
                  Nome do Projeto
                </label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full bg-[#0c0d13] border border-[#222638] focus:border-blue-500 rounded-lg px-3 py-2 text-xs text-white outline-none transition"
                  placeholder="Ex: Patrimônio"
                />
              </div>

              <div>
                <label className="block text-[11px] font-medium text-[#8a93a8] uppercase mb-1">
                  Comando para Rodar o Projeto
                </label>
                <input
                  type="text"
                  value={editDevCmd}
                  onChange={(e) => setEditDevCmd(e.target.value)}
                  className="w-full bg-[#0c0d13] border border-[#222638] focus:border-blue-500 rounded-lg px-3 py-2 text-xs text-emerald-300 font-mono outline-none transition"
                  placeholder="Ex: dotnet run, npm run dev, docker compose up"
                />
                <p className="text-[10px] text-slate-500 mt-1">
                  Usado no botão <strong>Parar & Subir Novamente</strong>.
                </p>
              </div>

              <div>
                <label className="block text-[11px] font-medium text-[#8a93a8] uppercase mb-1">
                  Caminho no Disco (Fixo)
                </label>
                <div className="text-[10px] font-mono text-slate-400 bg-[#090a0f] p-2 rounded border border-[#1c2030] truncate select-all">
                  {editingProject.root_path}
                </div>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  disabled={isSaving}
                  onClick={() => setEditingProject(null)}
                  className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:bg-[#222638] transition disabled:opacity-50"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={isSaving || !editName.trim()}
                  className="px-4 py-1.5 rounded-lg text-xs font-medium bg-blue-600 hover:bg-blue-500 text-white transition flex items-center gap-1.5 disabled:opacity-50"
                >
                  {isSaving ? (
                    <>
                      <Loader2 size={13} className="animate-spin" />
                      Salvando...
                    </>
                  ) : (
                    'Salvar'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal de Sincronização de Projetos Antigravity */}
      {isSyncModalOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-[#141620] border border-[#262a3b] rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
            <div className="p-4 border-b border-[#262a3b] flex items-center justify-between bg-[#181a26]">
              <div className="flex items-center gap-2">
                <RotateCw size={16} className="text-purple-400" />
                <h3 className="font-semibold text-sm text-white">Sincronizar Projetos do Antigravity</h3>
              </div>
              <button
                onClick={() => setIsSyncModalOpen(false)}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-[#222638] transition"
              >
                <X size={16} />
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1 space-y-3 custom-scroll">
              <p className="text-xs text-slate-400">
                Detectamos workspaces e conversas no seu Antigravity Desktop local. Selecione quais projetos deseja importar para o Agent Orchestrator:
              </p>

              {isDiscovering ? (
                <div className="py-10 flex flex-col items-center justify-center gap-2 text-slate-400">
                  <Loader2 size={24} className="animate-spin text-purple-400" />
                  <span className="text-xs">Buscando workspaces do Antigravity...</span>
                </div>
              ) : discoveredProjects.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-500 border border-dashed border-[#262a3b] rounded-xl">
                  Nenhum projeto encontrado no Antigravity local.
                </div>
              ) : (
                <div className="space-y-2">
                  {discoveredProjects.map((dp) => {
                    const isSelected = selectedToImport.includes(dp.root_path);
                    return (
                      <div
                        key={dp.root_path}
                        onClick={() => {
                          if (dp.already_imported) return;
                          if (isSelected) {
                            setSelectedToImport(selectedToImport.filter((p) => p !== dp.root_path));
                          } else {
                            setSelectedToImport([...selectedToImport, dp.root_path]);
                          }
                        }}
                        className={`p-3 rounded-xl border transition flex items-center justify-between gap-3 ${
                          dp.already_imported
                            ? 'bg-[#10121a]/60 border-[#1f2333] opacity-60 cursor-not-allowed'
                            : isSelected
                            ? 'bg-purple-950/20 border-purple-500/50 cursor-pointer shadow-sm'
                            : 'bg-[#10121a] border-[#222638] hover:border-slate-600 cursor-pointer'
                        }`}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <Folder size={14} className={dp.already_imported ? 'text-slate-500' : isSelected ? 'text-purple-400' : 'text-slate-400'} />
                            <span className="text-xs font-semibold text-white truncate">{dp.name}</span>
                            {dp.already_imported && (
                              <span className="text-[10px] bg-slate-800 text-slate-400 px-1.5 py-0.5 rounded border border-slate-700 font-medium">
                                Já importado
                              </span>
                            )}
                          </div>
                          <div className="text-[10px] text-slate-500 font-mono truncate mt-0.5">
                            {dp.root_path}
                          </div>
                        </div>

                        {!dp.already_imported && (
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => {}} // handled by row click
                            className="rounded border-slate-700 text-purple-600 focus:ring-0 bg-[#090a0f] cursor-pointer"
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="p-3.5 border-t border-[#262a3b] bg-[#181a26] flex items-center justify-between">
              <span className="text-[11px] text-slate-400">
                {selectedToImport.length} selecionado(s) para importar
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={isImporting}
                  onClick={() => setIsSyncModalOpen(false)}
                  className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:bg-[#222638] transition disabled:opacity-50"
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  disabled={isImporting || selectedToImport.length === 0}
                  onClick={handleImportSelected}
                  className="px-4 py-1.5 rounded-lg text-xs font-medium bg-purple-600 hover:bg-purple-500 text-white transition flex items-center gap-1.5 disabled:opacity-50 shadow-sm"
                >
                  {isImporting ? (
                    <>
                      <Loader2 size={13} className="animate-spin" />
                      Importando...
                    </>
                  ) : (
                    'Importar Selecionados'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
};
