import React, { useState, useEffect } from 'react';
import { Task, Message } from '../types';
import { api } from '../services/api';
import { useTaskWebSocket } from '../hooks/useTaskWebSocket';
import { DiffViewer } from './DiffViewer';
import { X, Play, Square, Sparkles, CheckCircle2, MessageSquare, Terminal, FileCode, Check } from 'lucide-react';

interface TaskDrawerProps {
  task: Task;
  onClose: () => void;
  onTaskUpdated: (updated: Task) => void;
}

export const TaskDrawer: React.FC<TaskDrawerProps> = ({ task, onClose, onTaskUpdated }) => {
  const [activeTab, setActiveTab] = useState<'chat' | 'diff' | 'logs' | 'spec'>('chat');
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMsg, setInputMsg] = useState('');
  const [diffText, setDiffText] = useState('');
  const [loadingAction, setLoadingAction] = useState(false);

  const { logs, taskStatus } = useTaskWebSocket(task.id);

  // Carrega histórico de mensagens
  useEffect(() => {
    api.getMessages(task.id).then(setMessages).catch(console.error);
  }, [task.id]);

  // Carrega diff quando estiver pronto para revisão ou ao abrir aba de diff
  useEffect(() => {
    if (activeTab === 'diff' || task.status === 'REVIEW_READY') {
      api.getDiff(task.id).then((res) => setDiffText(res.diff)).catch(console.error);
    }
  }, [activeTab, task.id, task.status]);

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMsg.trim()) return;
    try {
      const newMsg = await api.sendMessage(task.id, inputMsg.trim());
      setMessages((prev) => [...prev, newMsg]);
      setInputMsg('');
    } catch (err) {
      console.error(err);
    }
  };

  const handleRefinePrompt = async () => {
    setLoadingAction(true);
    try {
      const updated = await api.refineTask(task.id);
      onTaskUpdated(updated);
      setActiveTab('spec');
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingAction(false);
    }
  };

  const handleRunTask = async () => {
    setLoadingAction(true);
    try {
      const updated = await api.runTask(task.id);
      onTaskUpdated(updated);
      setActiveTab('logs');
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingAction(false);
    }
  };

  const handleStopTask = async () => {
    try {
      await api.stopTask(task.id);
      const updated = { ...task, status: 'SPEC_READY' as const };
      onTaskUpdated(updated);
    } catch (err) {
      console.error(err);
    }
  };

  const handleMergeTask = async () => {
    setLoadingAction(true);
    try {
      const res = await api.mergeTask(task.id);
      const updated = { ...task, status: 'DONE' as const };
      onTaskUpdated(updated);
      alert('Branch incorporada com sucesso na main e worktree removida!');
      onClose();
    } catch (err: any) {
      alert(`⚠️ Não foi possível efetuar o merge: ${err.message || 'Conflito detectado'}.\nA branch principal permaneceu limpa e sem corrupção.`);
    } finally {
      setLoadingAction(false);
    }
  };

  return (
    <section className="w-[580px] border-l border-[#262a3b] bg-[#12141c] flex flex-col shrink-0 shadow-2xl transition-all duration-200">
      {/* Drawer Header */}
      <div className="p-4 border-b border-[#262a3b] flex items-center justify-between bg-[#1a1d28]">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-amber-400 font-bold">#{task.id.slice(0, 8)}</span>
            <span className="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded font-medium">
              {taskStatus || task.status}
            </span>
          </div>
          <h2 className="font-bold text-sm text-white mt-1 line-clamp-1">{task.title}</h2>
        </div>
        <button onClick={onClose} className="text-[#8a93a8] hover:text-white p-1 rounded hover:bg-[#262a3b]">
          <X size={16} />
        </button>
      </div>

      {/* Runner Bar */}
      <div className="px-4 py-2 bg-[#090a0f] border-b border-[#262a3b] flex items-center justify-between text-xs">
        <span className="text-[#8a93a8] text-[11px]">
          Runner: <strong className="text-slate-200 font-mono">{task.runner_type}</strong>
        </span>
        <div className="flex items-center gap-2">
          {task.status === 'RUNNING' && (
            <button
              onClick={handleStopTask}
              className="bg-rose-600 hover:bg-rose-500 text-white text-[11px] px-2.5 py-1 rounded flex items-center gap-1 font-medium"
            >
              <Square size={10} /> Parar Agente
            </button>
          )}
          {task.status === 'DRAFT' && (
            <button
              onClick={handleRefinePrompt}
              disabled={loadingAction}
              className="bg-purple-600 hover:bg-purple-500 text-white text-[11px] px-2.5 py-1 rounded flex items-center gap-1 font-medium"
            >
              <Sparkles size={11} /> Lapidar Prompt
            </button>
          )}
          {task.status === 'SPEC_READY' && (
            <button
              onClick={handleRunTask}
              disabled={loadingAction}
              className="bg-blue-600 hover:bg-blue-500 text-white text-[11px] px-2.5 py-1 rounded flex items-center gap-1 font-medium"
            >
              <Play size={11} /> Despachar no Worktree
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#262a3b] bg-[#12141c] px-4">
        <button
          onClick={() => setActiveTab('chat')}
          className={`px-3 py-2.5 text-xs font-medium border-b-2 transition flex items-center gap-1.5 ${
            activeTab === 'chat'
              ? 'border-blue-400 text-blue-300 font-semibold'
              : 'border-transparent text-[#8a93a8] hover:text-white'
          }`}
        >
          <MessageSquare size={13} /> Chat Isolado
        </button>
        <button
          onClick={() => setActiveTab('diff')}
          className={`px-3 py-2.5 text-xs font-medium border-b-2 transition flex items-center gap-1.5 ${
            activeTab === 'diff'
              ? 'border-amber-400 text-amber-300 font-semibold'
              : 'border-transparent text-[#8a93a8] hover:text-white'
          }`}
        >
          <FileCode size={13} /> Diffs & Revisão
        </button>
        <button
          onClick={() => setActiveTab('logs')}
          className={`px-3 py-2.5 text-xs font-medium border-b-2 transition flex items-center gap-1.5 ${
            activeTab === 'logs'
              ? 'border-blue-400 text-blue-300 font-semibold'
              : 'border-transparent text-[#8a93a8] hover:text-white'
          }`}
        >
          <Terminal size={13} /> Terminal & Logs
        </button>
        <button
          onClick={() => setActiveTab('spec')}
          className={`px-3 py-2.5 text-xs font-medium border-b-2 transition flex items-center gap-1.5 ${
            activeTab === 'spec'
              ? 'border-purple-400 text-purple-300 font-semibold'
              : 'border-transparent text-[#8a93a8] hover:text-white'
          }`}
        >
          <Sparkles size={13} /> Spec Lapidada
        </button>
      </div>

      {/* Tab Contents */}
      <div className="flex-1 overflow-y-auto custom-scroll p-4">
        {activeTab === 'chat' && (
          <div className="flex flex-col h-full">
            <div className="flex-1 space-y-3 overflow-y-auto pr-1 text-xs">
              <div className="p-2.5 rounded-lg bg-[#1a1d28] border border-[#262a3b] text-[#8a93a8] text-[11px]">
                💡 Esta thread é 100% isolada. Conversas aqui nunca vazam para outras tarefas.
              </div>
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`flex gap-2.5 ${m.role === 'USER' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`p-3 rounded-xl max-w-[85%] leading-relaxed ${
                      m.role === 'USER'
                        ? 'bg-blue-600 text-white rounded-tr-none'
                        : 'bg-[#1a1d28] border border-[#262a3b] text-slate-200 rounded-tl-none'
                    }`}
                  >
                    {m.content}
                  </div>
                </div>
              ))}
            </div>

            <form onSubmit={handleSendMessage} className="mt-3 pt-3 border-t border-[#262a3b] flex gap-2">
              <input
                type="text"
                value={inputMsg}
                onChange={(e) => setInputMsg(e.target.value)}
                placeholder="Converse ou peça ajustes para este agente..."
                className="flex-1 bg-[#090a0f] border border-[#262a3b] rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
              />
              <button
                type="submit"
                className="bg-blue-600 hover:bg-blue-500 text-white px-3.5 py-2 rounded-lg text-xs font-medium"
              >
                Enviar
              </button>
            </form>
          </div>
        )}

        {activeTab === 'diff' && (
          <div className="space-y-4">
            {task.status === 'REVIEW_READY' && (
              <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs flex items-center justify-between">
                <div>
                  <span className="font-bold">Aguardando Aprovação Humana</span>
                  <p className="text-[11px] text-amber-300/80 mt-0.5">Revise o código abaixo e aprove o merge.</p>
                </div>
                <button
                  onClick={handleMergeTask}
                  disabled={loadingAction}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-3 py-1.5 rounded text-xs shadow flex items-center gap-1"
                >
                  <Check size={12} /> Aprovar & Merge
                </button>
              </div>
            )}
            <DiffViewer diffText={diffText} />
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="bg-black/90 rounded-lg p-3 font-mono text-[11px] text-slate-300 border border-slate-800 space-y-1 custom-scroll max-h-[480px] overflow-y-auto">
            {logs.length === 0 ? (
              <div className="text-slate-500 italic">Aguardando saída de terminal do agente...</div>
            ) : (
              logs.map((l, i) => <div key={i}>{l}</div>)
            )}
          </div>
        )}

        {activeTab === 'spec' && (
          <div className="space-y-3 text-xs">
            <div className="p-3 bg-[#1a1d28] rounded-lg border border-[#262a3b]">
              <div className="text-[10px] text-[#8a93a8] uppercase font-semibold">Prompt Bruto Original</div>
              <p className="text-slate-200 mt-1 italic">{task.raw_prompt}</p>
            </div>
            {task.refined_spec ? (
              <div className="p-3 bg-[#090a0f] rounded-lg border border-purple-500/30">
                <div className="text-[10px] text-purple-400 uppercase font-semibold mb-2">Especificação Lapidada (Spec)</div>
                <pre className="text-slate-300 whitespace-pre-wrap font-sans text-[11px] leading-relaxed">
                  {task.refined_spec}
                </pre>
              </div>
            ) : (
              <div className="p-4 rounded-lg border border-dashed border-[#262a3b] text-center text-[#8a93a8]">
                Clique no botão "Lapidar Prompt" acima para gerar a especificação atômica.
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
};
