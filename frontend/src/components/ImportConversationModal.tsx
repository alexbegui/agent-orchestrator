import React, { useState, useEffect } from 'react';
import { api } from '../services/api';
import { Task, Project } from '../types';
import {
  X,
  Search,
  Sparkles,
  Loader2,
  CheckCircle2,
  Clock,
  MessageSquare,
  ArrowRight,
  RefreshCw,
  FolderGit2
} from 'lucide-react';

interface AntigravityConversationItem {
  conversation_id: string;
  title: string;
  preview: string;
  step_count: number;
  last_modified: string;
  workspace: string;
  status: string;
  already_imported: boolean;
}

interface ImportConversationModalProps {
  project: Project;
  isOpen: boolean;
  onClose: () => void;
  onTaskImported: (task: Task) => void;
  /** Chamado após uma importação em lote, para a tela recarregar a lista. */
  onBulkImported?: () => void;
}

export const ImportConversationModal: React.FC<ImportConversationModalProps> = ({
  project,
  isOpen,
  onClose,
  onTaskImported,
  onBulkImported,
}) => {
  const [conversations, setConversations] = useState<AntigravityConversationItem[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [importingId, setImportingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkImporting, setBulkImporting] = useState(false);
  const [bulkResult, setBulkResult] = useState<string | null>(null);

  const fetchConversations = async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await api.getAntigravityConversations(project.id);
      setConversations(items);
    } catch (err: any) {
      setError(err.message || 'Erro ao carregar conversas do Antigravity.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setSearchQuery('');
      setSelected(new Set());
      setBulkResult(null);
      fetchConversations();
    }
  }, [isOpen, project.id]);

  const toggleSelected = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const handleImportSelected = async (ids: string[]) => {
    if (ids.length === 0 || bulkImporting) return;
    setBulkImporting(true);
    setError(null);
    setBulkResult(null);
    try {
      const res = await api.importAntigravityBulk(project.id, ids);
      const partes = [`${res.imported} importada(s)`];
      if (res.skipped > 0) partes.push(`${res.skipped} já existia(m)`);
      if (res.failed.length > 0) partes.push(`${res.failed.length} falhou/falharam`);
      setBulkResult(partes.join(' · '));
      setSelected(new Set());
      await fetchConversations();
      onBulkImported?.();
    } catch (err: any) {
      setError(err.message || 'Falha ao importar em lote.');
    } finally {
      setBulkImporting(false);
    }
  };

  if (!isOpen) return null;

  const filtered = conversations.filter((c) => {
    const q = searchQuery.toLowerCase();
    return (
      c.title.toLowerCase().includes(q) ||
      c.preview.toLowerCase().includes(q) ||
      c.conversation_id.toLowerCase().includes(q)
    );
  });

  const handleImport = async (item: AntigravityConversationItem) => {
    if (item.already_imported) return;
    setImportingId(item.conversation_id);
    setError(null);
    try {
      const task = await api.importAntigravityConversation({
        project_id: project.id,
        conversation_id: item.conversation_id,
        title: item.title,
      });
      onTaskImported(task);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Falha ao importar conversa.');
      setImportingId(null);
    }
  };

  const handleSyncConversation = async (conversationId: string) => {
    setImportingId(conversationId);
    setError(null);
    try {
      const res = await api.syncAntigravityConversation(conversationId);
      const allTasks = await api.getTasks(project.id);
      const target = allTasks.find((t) => t.id === res.task_id);
      if (target) {
        onTaskImported(target);
      }
      onClose();
    } catch (err: any) {
      setError(err.message || 'Falha ao sincronizar conversa.');
      setImportingId(null);
    }
  };

  const formatDate = (dateStr: string) => {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr.replace(' ', 'T'));
      if (isNaN(d.getTime())) return dateStr;
      return d.toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#141620] border border-[#272b3c] rounded-2xl max-w-2xl w-full flex flex-col max-h-[85vh] shadow-2xl animate-in fade-in zoom-in-95 duration-150 overflow-hidden">
        {/* Cabeçalho */}
        <div className="p-5 border-b border-[#242838] flex items-center justify-between bg-[#181a26]">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-purple-500/10 border border-purple-500/25 text-purple-400">
              <Sparkles size={20} />
            </div>
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                Importar Conversa do Antigravity
              </h2>
              <p className="text-xs text-[#8a93a8] mt-0.5">
                Vincule uma sessão já existente para continuar acompanhando e conversando pelo Kanban
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-[#252a3b] transition"
          >
            <X size={18} />
          </button>
        </div>

        {/* Barra de Pesquisa e Atualização */}
        <div className="p-4 border-b border-[#222534] bg-[#12131c] flex items-center gap-3">
          <div className="relative flex-1">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Buscar por título, resumo ou ID da sessão..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#181a26] border border-[#272b3c] rounded-xl pl-10 pr-4 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500/60 focus:ring-1 focus:ring-purple-500/60 transition"
              autoFocus
            />
          </div>
          <button
            onClick={fetchConversations}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium text-slate-300 bg-[#181a26] border border-[#272b3c] hover:bg-[#222638] hover:text-white transition disabled:opacity-50"
            title="Recarregar conversas locais"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            <span>Atualizar</span>
          </button>
        </div>

        {/* Ações em lote */}
        {(() => {
          const pendentes = filtered.filter((c) => !c.already_imported);
          const todasMarcadas = pendentes.length > 0 && pendentes.every((c) => selected.has(c.conversation_id));
          if (pendentes.length === 0) return null;
          return (
            <div className="px-4 py-2.5 border-b border-[#222534] bg-[#141620] flex items-center gap-3">
              <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={todasMarcadas}
                  onChange={() =>
                    setSelected(todasMarcadas ? new Set() : new Set(pendentes.map((c) => c.conversation_id)))
                  }
                  className="accent-purple-500"
                />
                Selecionar todas ({pendentes.length} pendentes)
              </label>

              {bulkResult && <span className="text-xs text-emerald-300">{bulkResult}</span>}

              <button
                onClick={() => handleImportSelected(Array.from(selected))}
                disabled={selected.size === 0 || bulkImporting}
                className="ml-auto flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-medium bg-purple-600 hover:bg-purple-500 text-white transition disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {bulkImporting ? <Loader2 size={13} className="animate-spin" /> : <ArrowRight size={13} />}
                Importar selecionadas ({selected.size})
              </button>
            </div>
          );
        })()}

        {/* Alerta de Erro */}
        {error && (
          <div className="mx-4 mt-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/25 text-rose-300 text-xs">
            {error}
          </div>
        )}

        {/* Lista de Conversas */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2.5 custom-scroll">
          {loading ? (
            <div className="py-16 flex flex-col items-center justify-center text-slate-400 gap-3">
              <Loader2 size={28} className="animate-spin text-purple-400" />
              <span className="text-xs">Buscando conversas salvas no Antigravity...</span>
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-16 text-center text-slate-500 text-xs">
              {searchQuery
                ? 'Nenhuma conversa corresponde aos termos pesquisados.'
                : 'Nenhuma conversa encontrada no banco de dados local do Antigravity.'}
            </div>
          ) : (
            filtered.map((item) => {
              const isImporting = importingId === item.conversation_id;
              return (
                <div
                  key={item.conversation_id}
                  className={`p-3.5 rounded-xl border transition flex flex-col md:flex-row items-start md:items-center justify-between gap-3 ${
                    item.already_imported
                      ? 'bg-[#10111a]/60 border-[#1f2230] opacity-60'
                      : 'bg-[#181a26] border-[#25293a] hover:border-purple-500/40 hover:bg-[#1c1f2e]'
                  }`}
                >
                  {!item.already_imported && (
                    <input
                      type="checkbox"
                      checked={selected.has(item.conversation_id)}
                      onChange={() => toggleSelected(item.conversation_id)}
                      onClick={(e) => e.stopPropagation()}
                      className="accent-purple-500 shrink-0 mt-1 md:mt-0"
                      title="Selecionar para importar em lote"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-xs text-white truncate max-w-[340px]">
                        {item.title}
                      </span>
                      {item.already_imported && (
                        <span className="inline-flex items-center gap-1 text-[10px] bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded-full font-medium">
                          <CheckCircle2 size={11} /> Já Importado
                        </span>
                      )}
                      <span className="text-[10px] text-slate-400 bg-slate-800/80 px-2 py-0.5 rounded-md border border-slate-700/50 flex items-center gap-1">
                        <MessageSquare size={10} />
                        {item.step_count} passos
                      </span>
                    </div>

                    {item.preview && (
                      <p className="text-[11px] text-slate-400 mt-1 line-clamp-1 italic">
                        "{item.preview}"
                      </p>
                    )}

                    <div className="flex items-center gap-3 mt-2 text-[10px] text-slate-500">
                      {item.last_modified && (
                        <span className="flex items-center gap-1">
                          <Clock size={11} />
                          {formatDate(item.last_modified)}
                        </span>
                      )}
                      <span className="font-mono text-slate-600 truncate max-w-[180px]">
                        ID: {item.conversation_id.slice(0, 8)}...
                      </span>
                    </div>
                  </div>

                  <div className="flex-shrink-0 self-end md:self-center">
                    <button
                      type="button"
                      disabled={isImporting}
                      onClick={() =>
                        item.already_imported
                          ? handleSyncConversation(item.conversation_id)
                          : handleImport(item)
                      }
                      className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold transition active:scale-95 ${
                        item.already_imported
                          ? 'bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 shadow-sm'
                          : 'bg-purple-600 hover:bg-purple-500 text-white shadow-lg shadow-purple-600/20'
                      }`}
                      title={
                        item.already_imported
                          ? 'Sincronizar novas mensagens do Antigravity para esta tarefa'
                          : 'Vincular ao projeto'
                      }
                    >
                      {isImporting ? (
                        <>
                          <Loader2 size={13} className="animate-spin" />
                          <span>{item.already_imported ? 'Sincronizando...' : 'Importando...'}</span>
                        </>
                      ) : item.already_imported ? (
                        <>
                          <RefreshCw size={12} className="text-blue-400" />
                          <span>Sincronizar</span>
                        </>
                      ) : (
                        <>
                          <span>Vincular</span>
                          <ArrowRight size={13} />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Rodapé informativo */}
        <div className="p-3.5 border-t border-[#222534] bg-[#11121b] text-center text-[11px] text-[#8a93a8] flex items-center justify-between px-5">
          <span className="flex items-center gap-1.5">
            <FolderGit2 size={13} className="text-purple-400" />
            <span>Projeto destino: <strong className="text-slate-200">{project.name}</strong></span>
          </span>
          <span className="text-slate-500">
            A tarefa entrará na coluna <strong>Em Execução</strong>
          </span>
        </div>
      </div>
    </div>
  );
};
