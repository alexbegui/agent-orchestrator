import React, { useState } from 'react';
import { Project } from '../types';
import { Folder, Plus, CheckCircle, ShieldCheck, Pencil, X, Loader2 } from 'lucide-react';
import { api } from '../services/api';

interface SidebarProps {
  projects: Project[];
  activeProjectId: string | null;
  onSelectProject: (id: string) => void;
  onOpenNewProject: () => void;
  onProjectUpdated?: (updated: Project) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  projects,
  activeProjectId,
  onSelectProject,
  onOpenNewProject,
  onProjectUpdated,
}) => {
  const [editingProject, setEditingProject] = useState<Project | null>(null);
  const [editName, setEditName] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const handleSaveProjectName = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingProject || !editName.trim() || isSaving) return;
    setIsSaving(true);
    try {
      const updated = await api.updateProject(editingProject.id, { name: editName.trim() });
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

  return (
    <aside className="w-64 border-r border-[#262a3b] bg-[#12141c] flex flex-col shrink-0">
      <div className="p-4 border-b border-[#262a3b]">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-[#8a93a8] uppercase tracking-wider">Projetos</span>
          <button
            onClick={onOpenNewProject}
            className="p-1 hover:bg-[#1a1d28] rounded text-[#8a93a8] hover:text-white transition"
            title="Novo Projeto"
          >
            <Plus size={14} />
          </button>
        </div>
        <div className="space-y-1.5 max-h-56 overflow-y-auto custom-scroll pr-1">
          {projects.map((p) => {
            const isActive = p.id === activeProjectId;
            return (
              <div
                key={p.id}
                onClick={() => onSelectProject(p.id)}
                className={`group relative w-full text-left p-2.5 rounded-lg border transition flex items-center justify-between cursor-pointer ${
                  isActive
                    ? 'bg-[#1a1d28] border-blue-500/40 text-white'
                    : 'border-transparent text-[#8a93a8] hover:bg-[#1a1d28] hover:text-white'
                }`}
              >
                <div className="truncate mr-2 flex-1">
                  <div className="font-medium text-xs truncate flex items-center gap-1.5">
                    <span>{p.name}</span>
                  </div>
                  <div className="text-[10px] text-[#8a93a8] truncate">{p.root_path}</div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {p.active_tasks_count > 0 && (
                    <span className="text-[10px] bg-blue-500/20 text-blue-300 px-1.5 py-0.5 rounded-full font-mono">
                      {p.active_tasks_count}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditingProject(p);
                      setEditName(p.name);
                    }}
                    title="Renomear Projeto"
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-[#262a3b] text-[#8a93a8] hover:text-blue-300 transition"
                  >
                    <Pencil size={12} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Skills & Harnesses Section */}
      <div className="p-4 flex-1 overflow-y-auto custom-scroll">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-[#8a93a8] uppercase tracking-wider">Harness & Skills</span>
          <span className="text-[10px] text-emerald-400 font-mono">Ativas</span>
        </div>
        <p className="text-[11px] text-[#8a93a8] mb-3 leading-relaxed">
          Injeção modular por tarefa para máxima economia de tokens:
        </p>
        <div className="space-y-2 text-xs">
          <div className="p-2 rounded bg-[#090a0f] border border-[#1c2030] flex items-center justify-between">
            <div>
              <span className="font-medium text-white block">ui-ux-pro-max</span>
              <span className="text-[10px] text-[#8a93a8]">Acessibilidade e anti-slop</span>
            </div>
            <ShieldCheck size={14} className="text-blue-400" />
          </div>
          <div className="p-2 rounded bg-[#090a0f] border border-[#1c2030] flex items-center justify-between">
            <div>
              <span className="font-medium text-white block">test-driven-development</span>
              <span className="text-[10px] text-[#8a93a8]">Ciclos Red-Green-Refactor</span>
            </div>
            <ShieldCheck size={14} className="text-emerald-400" />
          </div>
          <div className="p-2 rounded bg-[#090a0f] border border-[#1c2030] flex items-center justify-between">
            <div>
              <span className="font-medium text-white block">fastapi-standards</span>
              <span className="text-[10px] text-[#8a93a8]">Pydantic v2 + Async</span>
            </div>
            <ShieldCheck size={14} className="text-purple-400" />
          </div>
        </div>
      </div>

      {/* Windows Runners Detected */}
      <div className="p-3 border-t border-[#262a3b] bg-[#090a0f] text-[11px] space-y-1">
        <div className="text-[10px] text-[#8a93a8] font-semibold uppercase">Ambiente Local (Windows)</div>
        <div className="flex items-center justify-between text-slate-300">
          <span>Anthropic Claude Code</span>
          <span className="text-emerald-400 font-mono text-[10px]">claude.cmd ✓</span>
        </div>
        <div className="flex items-center justify-between text-slate-300">
          <span>Antigravity / Gemini</span>
          <span className="text-emerald-400 font-mono text-[10px]">agy.exe ✓</span>
        </div>
        <div className="flex items-center justify-between text-slate-300">
          <span>Git Worktrees</span>
          <span className="text-emerald-400 font-mono text-[10px]">ativo ✓</span>
        </div>
      </div>

      {/* Modal: Editar Nome do Projeto */}
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
                Editar Nome do Projeto
              </h3>
              <button
                type="button"
                onClick={() => setEditingProject(null)}
                className="text-[#8a93a8] hover:text-white p-1 rounded hover:bg-[#262a3b]"
              >
                <X size={15} />
              </button>
            </div>

            <form onSubmit={handleSaveProjectName} className="space-y-4">
              <div>
                <label className="block text-[11px] font-medium text-[#8a93a8] uppercase mb-1.5">
                  Nome do Projeto
                </label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full bg-[#0c0d13] border border-[#222638] focus:border-blue-500 rounded-lg px-3 py-2 text-xs text-white outline-none transition"
                  placeholder="Ex: Patrimônio"
                />
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
                    'Salvar Alterações'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </aside>
  );
};

