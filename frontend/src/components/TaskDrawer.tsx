import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { Task, Message, Attachment } from '../types';
import { api } from '../services/api';
import { useTaskWebSocket } from '../hooks/useTaskWebSocket';
import { DiffViewer } from './DiffViewer';
import { MarkdownRenderer } from './MarkdownRenderer';
import { QuestionNavigator } from './QuestionNavigator';
import {
  X,
  Play,
  Square,
  Sparkles,
  CheckCircle2,
  MessageSquare,
  Terminal,
  FileCode,
  Check,
  Loader2,
  Trash2,
  AlertTriangle,
  Maximize2,
  Minimize2,
  Copy,
  RefreshCw,
  Paperclip,
  FileText,
  Image as ImageIcon,
  ExternalLink,
  Download,
  ChevronRight,
} from 'lucide-react';

interface TaskDrawerProps {
  task: Task;
  onClose: () => void;
  onTaskUpdated: (updated: Task) => void;
  onTaskDeleted: (taskId: string) => void;
}

export const TaskDrawer: React.FC<TaskDrawerProps> = ({ task, onClose, onTaskUpdated, onTaskDeleted }) => {
  const [activeTab, setActiveTab] = useState<'chat' | 'artifacts' | 'diff' | 'logs' | 'spec'>('chat');
  const [artifacts, setArtifacts] = useState<
    {
      name: string;
      kind: 'markdown' | 'html' | 'mermaid' | 'other';
      category: 'documento' | 'mockup' | 'diagrama' | 'imagem' | 'dados' | 'outro';
      preview: string;
      size: number;
      modified_at: number;
      path: string;
      outside_task?: boolean;
      rel_path?: string | null;
    }[]
  >([]);
  const [openArtifact, setOpenArtifact] = useState<{ name: string; content: string } | null>(null);
  const [loadingArtifacts, setLoadingArtifacts] = useState(false);
  const [proposals, setProposals] = useState<string[]>([]);
  const [approved, setApproved] = useState<Set<string>>(new Set());
  const [savingKnowledge, setSavingKnowledge] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMsg, setInputMsg] = useState('');
  const [diffText, setDiffText] = useState('');
  const [loadingAction, setLoadingAction] = useState(false);
  const [erroRefino, setErroRefino] = useState<string | null>(null);
  const [walkthrough, setWalkthrough] = useState<
    { conteudo: string; truncado: boolean; fora_da_pasta: boolean } | null
  >(null);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncFeedback, setSyncFeedback] = useState<string | null>(null);

  // Estados para Navegador Q&A e Anexos Multimodais
  const [activeQuestionId, setActiveQuestionId] = useState<string | null>(null);
  const [highlightedMsgId, setHighlightedMsgId] = useState<string | null>(null);
  const [pendingAttachments, setPendingAttachments] = useState<Attachment[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [previewImageModal, setPreviewImageModal] = useState<string | null>(null);

  const chatBottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  /** O campo cresce para baixo conforme o texto, até um teto; depois rola. */
  const MAX_ALTURA_INPUT = 180;
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_ALTURA_INPUT)}px`;
  }, [inputMsg]);

  // Descarta o que não é desta tarefa. O canal já é por task_id, então isto é
  // defesa em profundidade: uma mensagem que chegue por um socket antigo,
  // durante a troca de tarefa, apareceria no chat errado.
  const handleNewMessage = useCallback((incoming: Message) => {
    if (incoming.task_id && incoming.task_id !== task.id) return;
    setMessages((prev) => {
      if (prev.some((m) => m.id === incoming.id)) return prev;
      return [...prev, incoming];
    });
  }, [task.id]);

  const { logs, taskStatus } = useTaskWebSocket(task.id, handleNewMessage);

  // Carrega histórico de mensagens.
  //
  // Zera ANTES de buscar: sem isso, as mensagens da tarefa anterior seguiam na
  // tela durante toda a ida à rede, e o usuário via a resposta de uma tarefa no
  // chat de outra. O `cancelado` descarta resposta que chega depois de o
  // usuário já ter trocado de tarefa — ela encheria o chat errado.
  useEffect(() => {
    let cancelado = false;
    setMessages([]);
    api.getMessages(task.id)
      .then((msgs) => {
        if (!cancelado) setMessages(msgs);
      })
      .catch(console.error);
    return () => {
      cancelado = true;
    };
  }, [task.id]);

  // Rola suavemente para a última mensagem ao enviar ou receber nova
  useEffect(() => {
    if (activeTab === 'chat' && !highlightedMsgId) {
      chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isSendingMessage, activeTab, highlightedMsgId]);

  const carregarArtefatos = useCallback(() => {
    setLoadingArtifacts(true);
    setOpenArtifact(null);
    api
      .getTaskArtifacts(task.id)
      .then((res) => {
        setArtifacts(res.artifacts);
        // `undefined` distingue "ainda não buscamos" de "buscamos e o agente
        // não escreveu" (`null`) — a tela diz coisas diferentes nos dois casos.
        setWalkthrough(res.walkthrough ?? null);
      })
      .catch(console.error)
      .finally(() => setLoadingArtifacts(false));
  }, [task.id]);

  // Carrega ao abrir a aba. O agente pode criar arquivo a qualquer momento,
  // por isso o botão de recarregar logo abaixo.
  //
  // A aba de revisão também busca: o sumário de entrega vem nesta mesma
  // resposta, e é lido ANTES do diff. Carregar só em "Artefatos" faria o
  // sumário nunca aparecer para quem vai direto revisar — que é o caminho
  // normal quando o card avisa "Entregou".
  useEffect(() => {
    if (activeTab !== 'artifacts' && activeTab !== 'diff') return;
    carregarArtefatos();
  }, [activeTab, carregarArtefatos]);

  // Propostas de conhecimento aparecem junto do diff — é lá que o usuário
  // já está decidindo se aprova o trabalho.
  useEffect(() => {
    if (activeTab !== 'diff') return;
    api
      .getKnowledgeProposals(task.id)
      .then((res) => {
        setProposals(res.proposals);
        setApproved(new Set()); // nada marcado: o padrão é descartar
      })
      .catch(console.error);
  }, [activeTab, task.id]);

  // Carrega diff quando estiver pronto para revisão ou ao abrir aba de diff
  useEffect(() => {
    if (activeTab === 'diff' || task.status === 'REVIEW_READY') {
      api.getDiff(task.id).then((res) => setDiffText(res.diff)).catch(console.error);
    }
  }, [activeTab, task.id, task.status]);

  // Mapeamento entre cada Pergunta e sua respectiva Resposta
  const questionMetaMap = useMemo(() => {
    const map = new Map<string, { qNum: number; linkedId?: string }>();
    let qCount = 0;
    let lastUserMsgId: string | null = null;

    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      if (msg.role === 'USER') {
        qCount++;
        lastUserMsgId = msg.id;
        map.set(msg.id, { qNum: qCount });
      } else if (msg.role === 'ASSISTANT' && lastUserMsgId) {
        const uMeta = map.get(lastUserMsgId);
        if (uMeta) {
          map.set(msg.id, { qNum: uMeta.qNum, linkedId: lastUserMsgId });
          if (!uMeta.linkedId) {
            uMeta.linkedId = msg.id;
          }
        }
      }
    }
    return map;
  }, [messages]);

  const scrollToMsg = (targetId: string) => {
    setHighlightedMsgId(targetId);
    const el = document.getElementById(`msg-${targetId}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    setTimeout(() => {
      setHighlightedMsgId((prev) => (prev === targetId ? null : prev));
    }, 2500);
  };

  const handleSelectQuestion = (questionId: string, responseId?: string) => {
    setActiveQuestionId(questionId);
    const targetId = responseId || questionId;
    scrollToMsg(targetId);
  };

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleUploadFiles = async (files: FileList | File[]) => {
    if (!files || files.length === 0) return;
    setIsUploading(true);
    setUploadError(null);
    const uploaded: Attachment[] = [];
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        if (file.size > 25 * 1024 * 1024) {
          setUploadError(`Arquivo "${file.name}" excede o limite de 25MB.`);
          continue;
        }
        const att = await api.uploadTaskFile(task.id, file);
        uploaded.push(att);
      }
      if (uploaded.length > 0) {
        setPendingAttachments((prev) => [...prev, ...uploaded]);
      }
    } catch (err: any) {
      setUploadError(err.message || 'Erro ao carregar anexo.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleRemovePendingAttachment = (indexToRemove: number) => {
    setPendingAttachments((prev) => prev.filter((_, idx) => idx !== indexToRemove));
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const files: File[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind === 'file') {
        const f = item.getAsFile();
        if (f) files.push(f);
      }
    }
    if (files.length > 0) {
      e.preventDefault();
      handleUploadFiles(files);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
      handleUploadFiles(e.dataTransfer.files);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if ((!inputMsg.trim() && pendingAttachments.length === 0) || isSendingMessage) return;
    const text = inputMsg.trim();
    const attachmentsToSend = [...pendingAttachments];
    setInputMsg('');
    setPendingAttachments([]);
    setIsSendingMessage(true);

    try {
      await api.sendMessage(
        task.id,
        text,
        attachmentsToSend.length > 0 ? attachmentsToSend : undefined
      );
      // Atualiza com a lista fresca do servidor
      api.getMessages(task.id).then(setMessages).catch(console.error);
    } catch (err) {
      console.error(err);
    } finally {
      setIsSendingMessage(false);
    }
  };

  const handleSyncAntigravity = async () => {
    setIsSyncing(true);
    setSyncFeedback(null);
    try {
      const res = await api.syncTaskAntigravity(task.id);
      const updatedMsgs = await api.getMessages(task.id);
      setMessages(updatedMsgs);
      if (res.synced > 0) {
        setSyncFeedback(`${res.synced} nova(s) resposta(s) sincronizada(s)!`);
      } else {
        setSyncFeedback('Tudo atualizado.');
      }
      setTimeout(() => setSyncFeedback(null), 3500);
    } catch (err: any) {
      setSyncFeedback(err.message || 'Erro ao sincronizar.');
      setTimeout(() => setSyncFeedback(null), 3500);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleRefinePrompt = async () => {
    setLoadingAction(true);
    // Limpa o erro da tentativa anterior ANTES de tentar: deixá-lo na tela
    // enquanto a nova chamada roda faz a tentativa em curso parecer uma falha.
    setErroRefino(null);
    try {
      const updated = await api.refineTask(task.id);
      onTaskUpdated(updated);
      setActiveTab('spec');
    } catch (err) {
      // O backend manda o motivo real no corpo do 502 ("sem chave", "HTTP 401",
      // "a IA não devolveu JSON"). Engolir isso num console.error deixava a
      // tela idêntica a "não aconteceu nada" — e o usuário sem saber se devia
      // esperar, clicar de novo, ou configurar uma chave.
      setErroRefino(err instanceof Error ? err.message : String(err));
      setActiveTab('spec');
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
      await api.mergeTask(task.id);
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

  const handleDeleteTask = async () => {
    setIsDeleting(true);
    try {
      await api.deleteTask(task.id);
      setIsDeleteModalOpen(false);
      onTaskDeleted(task.id);
    } catch (err: any) {
      alert(`⚠️ Erro ao excluir tarefa: ${err.message || 'Falha na exclusão'}`);
      setIsDeleting(false);
    }
  };

  const renderAttachments = (attachments?: Attachment[]) => {
    if (!attachments || attachments.length === 0) return null;
    const imageAttachments = attachments.filter((att) => att.content_type?.startsWith('image/'));
    const docAttachments = attachments.filter((att) => !att.content_type?.startsWith('image/'));

    return (
      <div className="mt-2.5 space-y-2">
        {imageAttachments.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {imageAttachments.map((att, idx) => (
              <div
                key={idx}
                onClick={() => setPreviewImageModal(att.file_url)}
                className="group relative cursor-pointer rounded-lg overflow-hidden border border-white/20 bg-black/40 hover:border-blue-400 transition"
              >
                <img
                  src={att.file_url}
                  alt={att.original_name}
                  className="h-28 max-w-[220px] object-cover transition-transform group-hover:scale-105"
                />
                <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition gap-1.5 text-white text-[11px] font-medium">
                  <Maximize2 size={13} />
                  <span>Ampliar</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {docAttachments.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {docAttachments.map((att, idx) => (
              <a
                key={idx}
                href={att.file_url}
                target="_blank"
                rel="noopener noreferrer"
                download={att.original_name}
                className="flex items-center justify-between p-2 rounded-lg bg-black/30 hover:bg-black/50 border border-white/10 hover:border-blue-400 text-xs text-slate-200 transition group"
              >
                <div className="flex items-center gap-2 min-w-0 pr-2">
                  <div className="p-1.5 rounded bg-blue-500/20 text-blue-400 group-hover:text-blue-300">
                    <FileText size={14} />
                  </div>
                  <div className="min-w-0">
                    <div className="truncate font-medium text-slate-200 group-hover:text-white">
                      {att.original_name}
                    </div>
                    <div className="text-[10px] text-slate-400">
                      {formatFileSize(att.size)}
                    </div>
                  </div>
                </div>
                <Download size={13} className="text-slate-400 group-hover:text-blue-400 shrink-0" />
              </a>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <section
      className={`${
        isExpanded ? 'w-[940px]' : 'w-[640px]'
      } border-l border-[#262a3b] bg-[#12141c] flex flex-col shrink-0 shadow-2xl transition-all duration-200 z-20`}
    >
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
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            title={isExpanded ? 'Restaurar largura (640px)' : 'Expandir largura (940px)'}
            className="text-[#8a93a8] hover:text-white p-1.5 rounded hover:bg-[#262a3b] transition flex items-center"
          >
            {isExpanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
          <button
            onClick={() => setIsDeleteModalOpen(true)}
            title="Cancelar e Excluir Tarefa"
            className="text-rose-400/80 hover:text-rose-300 p-1.5 rounded hover:bg-rose-950/40 transition flex items-center gap-1 text-[11px] font-medium"
          >
            <Trash2 size={15} />
            <span className="hidden sm:inline">Excluir</span>
          </button>
          <button onClick={onClose} className="text-[#8a93a8] hover:text-white p-1 rounded hover:bg-[#262a3b]">
            <X size={16} />
          </button>
        </div>
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
          onClick={() => setActiveTab('artifacts')}
          title="Mockups, specs e análises produzidos nesta tarefa — viram documentação do projeto no merge"
          className={`px-3 py-2.5 text-xs font-medium border-b-2 transition flex items-center gap-1.5 ${
            activeTab === 'artifacts'
              ? 'border-emerald-400 text-emerald-300 font-semibold'
              : 'border-transparent text-[#8a93a8] hover:text-white'
          }`}
        >
          <FileText size={13} /> Artefatos
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
      <div className="flex-1 overflow-y-auto custom-scroll p-4 flex flex-col">
        {activeTab === 'chat' && (
          <div className="flex flex-col h-full">
            {/* Banner de Sincronização */}
            <div className="p-2.5 rounded-lg bg-[#1a1d28] border border-[#262a3b] text-[#8a93a8] text-[11px] flex items-center justify-between gap-2 mb-3">
              <span>💡 Conversa isolada vinculada ao projeto.</span>
              {task.runner_config?.antigravity_conversation_id && (
                <div className="flex items-center gap-2">
                  {syncFeedback && (
                    <span className="text-[10px] text-emerald-400 font-medium">
                      {syncFeedback}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={handleSyncAntigravity}
                    disabled={isSyncing}
                    className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-[#222638] border border-purple-500/30 hover:bg-purple-600/20 text-purple-300 hover:text-white text-[11px] font-medium transition"
                    title="Puxar respostas recentes do Antigravity"
                  >
                    <RefreshCw size={11} className={isSyncing ? "animate-spin text-purple-400" : "text-purple-400"} />
                    <span>{isSyncing ? "Sincronizando..." : "Sincronizar Antigravity"}</span>
                  </button>
                </div>
              )}
            </div>

            {/* Navegador de Perguntas & Respostas */}
            <QuestionNavigator
              messages={messages}
              activeQuestionId={activeQuestionId}
              onSelectQuestion={handleSelectQuestion}
            />

            {/* Lista de Mensagens */}
            <div className="flex-1 space-y-3 overflow-y-auto pr-1 text-xs custom-scroll">
              {messages.map((m) => {
                const meta = questionMetaMap.get(m.id);
                const isHighlighted = highlightedMsgId === m.id;

                return (
                  <div
                    key={m.id}
                    id={`msg-${m.id}`}
                    className={`flex ${m.role === 'USER' ? 'justify-end' : 'justify-start'} transition-all`}
                  >
                    {m.role === 'USER' ? (
                      <div
                        className={`p-3 rounded-xl max-w-[85%] bg-blue-600 text-white rounded-tr-none shadow-sm leading-relaxed text-xs transition-all duration-300 ${
                          isHighlighted ? 'ring-2 ring-amber-400 ring-offset-2 ring-offset-[#12141c]' : ''
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3 border-b border-blue-500/40 pb-1 mb-1.5 text-[10px] text-blue-200">
                          <span className="font-bold uppercase tracking-wider bg-blue-700/60 px-1.5 py-0.5 rounded">
                            Pergunta #{meta?.qNum}
                          </span>
                          {meta?.linkedId && (
                            <button
                              type="button"
                              onClick={() => scrollToMsg(meta.linkedId!)}
                              className="hover:text-white underline transition flex items-center gap-0.5 text-[10px]"
                              title="Rolar direto para a resposta do assistente"
                            >
                              <span>Ver resposta</span>
                              <ChevronRight size={11} />
                            </button>
                          )}
                        </div>
                        {m.content && <div className="whitespace-pre-wrap">{m.content}</div>}
                        {renderAttachments(m.attachments)}
                      </div>
                    ) : (
                      <div
                        className={`p-3.5 rounded-xl w-full max-w-[98%] bg-[#151722] border border-[#262a3b] text-slate-200 rounded-tl-none shadow-sm font-sans transition-all duration-300 ${
                          isHighlighted ? 'ring-2 ring-purple-400 ring-offset-2 ring-offset-[#12141c]' : ''
                        }`}
                      >
                        <div className="flex items-center justify-between border-b border-[#222638] pb-1.5 mb-2.5 text-[11px]">
                          <div className="flex items-center gap-2 flex-wrap">
                            <div className="text-blue-400 font-semibold flex items-center gap-1.5">
                              <Sparkles size={12} />
                              <span>Assistente Antigravity</span>
                            </div>
                            {meta?.qNum && (
                              <button
                                type="button"
                                onClick={() => meta.linkedId && scrollToMsg(meta.linkedId)}
                                className="text-[10px] text-slate-400 hover:text-blue-300 bg-[#1c202e] hover:bg-[#23293c] px-2 py-0.5 rounded border border-[#2c3246] transition flex items-center gap-1 font-medium"
                                title={`Pular para a Pergunta #${meta.qNum}`}
                              >
                                <span>Em resposta à Pergunta #{meta.qNum}</span>
                              </button>
                            )}
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              navigator.clipboard.writeText(m.content);
                              setCopiedMsgId(m.id);
                              setTimeout(() => setCopiedMsgId(null), 2000);
                            }}
                            title="Copiar resposta inteira"
                            className="flex items-center gap-1 text-[10px] text-[#8a93a8] hover:text-white px-2 py-0.5 rounded hover:bg-[#202538] transition font-medium"
                          >
                            {copiedMsgId === m.id ? (
                              <>
                                <Check size={11} className="text-emerald-400" />
                                <span className="text-emerald-400 font-semibold">Copiado</span>
                              </>
                            ) : (
                              <>
                                <Copy size={11} />
                                <span>Copiar</span>
                              </>
                            )}
                          </button>
                        </div>
                        <MarkdownRenderer content={m.content} />
                        {renderAttachments(m.attachments)}
                      </div>
                    )}
                  </div>
                );
              })}

              {isSendingMessage && (
                <div className="flex gap-2.5 justify-start">
                  <div className="p-3 rounded-xl max-w-[85%] bg-[#1a1d28] border border-blue-500/30 text-blue-300 rounded-tl-none flex items-center gap-2 text-xs">
                    <Loader2 size={13} className="animate-spin text-blue-400" />
                    <span>Assistente processando resposta...</span>
                  </div>
                </div>
              )}
              <div ref={chatBottomRef} />
            </div>

            {/* Formulário de Envio com Drag-and-Drop, Cola e Anexos */}
            <form
              onSubmit={handleSendMessage}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              className="mt-3 pt-3 border-t border-[#262a3b] flex flex-col gap-2"
            >
              {/* Chips de Anexos Pendentes */}
              {pendingAttachments.length > 0 && (
                <div className="flex flex-wrap gap-2 p-2 bg-[#161824] border border-[#252a3c] rounded-lg">
                  {pendingAttachments.map((att, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-2 bg-[#202538] border border-[#2e344d] px-2 py-1 rounded-md text-[11px] text-slate-200"
                    >
                      {att.content_type?.startsWith('image/') ? (
                        <img src={att.file_url} alt="" className="w-5 h-5 rounded object-cover" />
                      ) : (
                        <FileText size={13} className="text-blue-400" />
                      )}
                      <span className="truncate max-w-[140px] font-medium">{att.original_name}</span>
                      <span className="text-[9px] text-slate-400 font-mono">({formatFileSize(att.size)})</span>
                      <button
                        type="button"
                        onClick={() => handleRemovePendingAttachment(idx)}
                        className="text-slate-400 hover:text-rose-400 p-0.5 rounded transition"
                        title="Remover anexo"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {uploadError && (
                <div className="text-[11px] text-rose-400 bg-rose-500/10 border border-rose-500/20 px-2.5 py-1 rounded-md flex items-center justify-between">
                  <span>{uploadError}</span>
                  <button type="button" onClick={() => setUploadError(null)} className="text-rose-400 hover:text-white">
                    <X size={11} />
                  </button>
                </div>
              )}

              <div className="flex items-end gap-2">
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={(e) => {
                    if (e.target.files && e.target.files.length > 0) {
                      handleUploadFiles(e.target.files);
                      e.target.value = '';
                    }
                  }}
                  multiple
                  className="hidden"
                  accept="image/*,.pdf,.txt,.md,.json,.csv,.py,.ts,.tsx,.js,.html,.css"
                />

                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isSendingMessage || isUploading}
                  title="Anexar imagens ou documentos (ou arraste e cole com Ctrl+V)"
                  className="p-2 rounded-lg bg-[#161824] hover:bg-[#202538] border border-[#262a3b] hover:border-slate-600 text-slate-400 hover:text-slate-200 transition disabled:opacity-50 flex items-center justify-center shrink-0"
                >
                  {isUploading ? <Loader2 size={15} className="animate-spin text-blue-400" /> : <Paperclip size={15} />}
                </button>

                <textarea
                  ref={textareaRef}
                  rows={1}
                  value={inputMsg}
                  disabled={isSendingMessage}
                  onChange={(e) => setInputMsg(e.target.value)}
                  onPaste={handlePaste}
                  onKeyDown={(e) => {
                    // Enter envia; Shift+Enter quebra linha — convenção de chat.
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage(e as unknown as React.FormEvent);
                    }
                  }}
                  placeholder={
                    isSendingMessage
                      ? 'Aguarde o assistente responder...'
                      : 'Digite uma mensagem (Shift+Enter quebra linha), cole imagens ou anexe arquivos...'
                  }
                  className="flex-1 bg-[#090a0f] border border-[#262a3b] rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500 disabled:opacity-50 resize-none overflow-y-auto custom-scroll leading-relaxed"
                />

                <button
                  type="submit"
                  disabled={isSendingMessage || (!inputMsg.trim() && pendingAttachments.length === 0)}
                  className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-3.5 py-2 rounded-lg text-xs font-medium flex items-center gap-1.5 transition shrink-0"
                >
                  {isSendingMessage ? <Loader2 size={12} className="animate-spin" /> : null}
                  <span>Enviar</span>
                </button>
              </div>
            </form>
          </div>
        )}

        {activeTab === 'artifacts' && (
          <div className="space-y-3">
            <div className="flex items-start gap-2">
              <div className="flex-1 p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20 text-[11px] text-emerald-200/90 leading-relaxed">
                Mockups, specs, mapas mentais e análises que esta tarefa produziu —
                onde quer que o agente tenha salvado. No merge, viram documentação do
                projeto, consultável pelos próximos agentes.
              </div>
              <button
                onClick={carregarArtefatos}
                disabled={loadingArtifacts}
                title="Recarregar — o agente pode ter criado algo agora"
                className="shrink-0 p-2.5 rounded-lg bg-[#161824] border border-[#252a3c] text-slate-400 hover:text-emerald-300 hover:border-emerald-500/40 transition disabled:opacity-50"
              >
                <RefreshCw size={14} className={loadingArtifacts ? 'animate-spin' : ''} />
              </button>
            </div>

            {loadingArtifacts && (
              <div className="flex items-center gap-2 text-xs text-[#8a93a8] py-4">
                <Loader2 size={14} className="animate-spin" /> Carregando artefatos...
              </div>
            )}

            {!loadingArtifacts && artifacts.length === 0 && (
              <div className="py-10 text-center text-xs text-[#8a93a8]">
                <FileText size={26} className="mx-auto mb-2 opacity-40" />
                Nenhum artefato ainda.
                <p className="text-[10px] mt-1.5 max-w-sm mx-auto leading-relaxed">
                  Peça ao agente para salvar o que produzir — por exemplo:
                  "salve este mapa mental em docs/mapa.md". Qualquer documento que a
                  tarefa criar aparece aqui, em qualquer pasta.
                </p>
              </div>
            )}

            {!loadingArtifacts &&
              (
                [
                  { id: 'diagrama', label: '🧠 Mapas mentais e diagramas', cor: 'text-fuchsia-300' },
                  { id: 'mockup', label: '🖼 Mockups e telas', cor: 'text-blue-300' },
                  { id: 'documento', label: '📄 Documentos e análises', cor: 'text-emerald-300' },
                  { id: 'imagem', label: '🏞 Imagens', cor: 'text-amber-300' },
                  { id: 'dados', label: '🗃 Dados', cor: 'text-slate-300' },
                  { id: 'outro', label: '📎 Outros', cor: 'text-slate-400' },
                ] as const
              ).map((grupo) => {
                const doGrupo = artifacts.filter((a) => a.category === grupo.id);
                if (doGrupo.length === 0) return null;
                return (
                  <div key={grupo.id} className="space-y-2">
                    <div className={`text-[10px] font-bold uppercase tracking-wide ${grupo.cor} pt-1`}>
                      {grupo.label} <span className="text-[#8a93a8] font-normal">({doGrupo.length})</span>
                    </div>

                    {doGrupo.map((a) => {
                      const aberto = openArtifact?.name === a.name;
                      // `name` é o rótulo curto; `rel_path` é o endereço real,
                      // a partir da raiz do projeto. Ler pelo nome achava o
                      // arquivo só quando ele estava na pasta da tarefa.
                      const chave = a.rel_path || a.name;
                      const url = api.artifactUrl(task.id, chave);
                      const textual = a.kind === 'markdown' || a.kind === 'mermaid';
                      const visualizavel = textual || a.category === 'imagem' || a.category === 'mockup';
                      return (
                        <div
                          key={a.name}
                          className="p-3 rounded-lg bg-[#161824] border border-[#252a3c] hover:border-emerald-500/40 transition"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0 flex-1">
                              <div className="text-xs font-medium text-white truncate">
                                {a.name.split('/').pop()}
                              </div>
                              {a.name.includes('/') && (
                                <div className="text-[9.5px] font-mono text-[#64748b] truncate">
                                  {a.name.slice(0, a.name.lastIndexOf('/'))}/
                                </div>
                              )}
                              {/* O agente salvou fora da pasta da tarefa.
                                  Mostrar é melhor que simplesmente não achar. */}
                              {a.outside_task && (
                                <span
                                  title="Salvo fora da pasta desta tarefa — o agente navegou durante o trabalho"
                                  className="inline-block mt-1 text-[9px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/25"
                                >
                                  fora da tarefa
                                </span>
                              )}
                              {a.preview && (
                                <div className="text-[10.5px] text-[#8fa0b8] mt-1 line-clamp-2 leading-snug">
                                  {a.preview}
                                </div>
                              )}
                              <div className="text-[9.5px] font-mono text-[#64748b] mt-1">
                                {(a.size / 1024).toFixed(1)} KB
                              </div>
                            </div>
                            <div className="flex items-center gap-1.5 shrink-0">
                              {visualizavel && (
                                <button
                                  onClick={async () => {
                                    if (aberto) return setOpenArtifact(null);
                                    if (textual) {
                                      try {
                                        const lido = await api.readTaskArtifact(task.id, chave);
                                        setOpenArtifact({ name: a.name, content: lido.content });
                                      } catch (err: any) {
                                        alert(`⚠️ ${err.message || 'Falha ao ler o artefato'}`);
                                      }
                                    } else {
                                      setOpenArtifact({ name: a.name, content: '' });
                                    }
                                  }}
                                  className="text-[10px] px-2.5 py-1 rounded-md bg-[#1a1d28] border border-[#262a3b] text-slate-300 hover:border-emerald-500/50 hover:text-white transition"
                                >
                                  {aberto ? 'Fechar' : 'Ver aqui'}
                                </button>
                              )}
                              <a
                                href={url}
                                target="_blank"
                                rel="noreferrer"
                                title="Abrir em uma aba nova do navegador"
                                className="text-[10px] px-2.5 py-1 rounded-md bg-[#1a1d28] border border-[#262a3b] text-slate-300 hover:border-blue-500/50 hover:text-white transition flex items-center gap-1"
                              >
                                <ExternalLink size={10} /> Abrir
                              </a>
                            </div>
                          </div>

                          {aberto && (
                            <div className="mt-3 pt-3 border-t border-[#252a3c]">
                              {a.kind === 'markdown' && <MarkdownRenderer content={openArtifact!.content} />}
                              {/* .mmd é mermaid puro: embrulha numa cerca para o
                                  renderizador desenhar, em vez de mostrar texto */}
                              {a.kind === 'mermaid' && (
                                <MarkdownRenderer content={'```mermaid\n' + openArtifact!.content + '\n```'} />
                              )}
                              {a.category === 'imagem' && (
                                <img src={url} alt={a.name} className="max-w-full rounded-lg border border-[#262a3b]" />
                              )}
                              {a.category === 'mockup' && (
                                <iframe
                                  src={url}
                                  title={a.name}
                                  className="w-full h-[460px] rounded-lg border border-[#262a3b] bg-white"
                                />
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
          </div>
        )}

        {activeTab === 'diff' && (
          <div className="space-y-4">
            {/* O sumário vem ANTES do diff porque é o que se lê antes dele.
                Três linhas aqui mudam a economia de revisar 500 linhas ali. */}
            {walkthrough ? (
              <div className="p-3.5 rounded-lg bg-emerald-500/5 border border-emerald-500/30">
                <div className="text-xs font-bold text-emerald-200 mb-2">
                  O agente resumiu a entrega
                </div>
                {walkthrough.fora_da_pasta && (
                  <p className="text-[10.5px] text-amber-300/80 mb-2">
                    Salvo fora da pasta desta tarefa — achamos assim mesmo.
                  </p>
                )}
                <div className="text-slate-200 text-xs">
                  <MarkdownRenderer content={walkthrough.conteudo} />
                </div>
                {walkthrough.truncado && (
                  <p className="text-[10.5px] text-[#8a93a8] mt-2">
                    Sumário longo demais — mostrando só o começo.
                  </p>
                )}
              </div>
            ) : (
              /* Dizer que não houve é diferente de não mostrar nada: aba vazia
                 é indistinguível de falha ao carregar, e o usuário conclui que
                 o sumário sumiu em vez de que não existe. */
              <div className="p-3 rounded-lg border border-dashed border-[#262a3b] text-[11px] text-[#8a93a8]">
                O agente não deixou um sumário de entrega. Leia o diff abaixo —
                e, se quiser, peça o resumo pelo chat da tarefa.
              </div>
            )}

            {proposals.length > 0 && (
              <div className="p-3.5 rounded-lg bg-fuchsia-500/5 border border-fuchsia-500/30">
                <div className="text-xs font-bold text-fuchsia-200 mb-1">
                  O agente aprendeu algo e propôs registrar
                </div>
                <p className="text-[10.5px] text-fuchsia-300/70 mb-3 leading-relaxed">
                  Marque só o que vale guardar — vai para o conhecimento do projeto e
                  os próximos agentes vão ler. Sem marcar nada, é descartado.
                </p>

                <div className="space-y-2">
                  {proposals.map((linha) => (
                    <label
                      key={linha}
                      className="flex items-start gap-2.5 p-2 rounded-md bg-[#141620] border border-[#252a3c] cursor-pointer hover:border-fuchsia-500/40 transition"
                    >
                      <input
                        type="checkbox"
                        checked={approved.has(linha)}
                        onChange={() =>
                          setApproved((prev) => {
                            const next = new Set(prev);
                            next.has(linha) ? next.delete(linha) : next.add(linha);
                            return next;
                          })
                        }
                        className="accent-fuchsia-500 mt-0.5"
                      />
                      <span className="text-[11px] text-slate-200 leading-snug">{linha}</span>
                    </label>
                  ))}
                </div>

                <div className="flex items-center gap-2 mt-3">
                  <button
                    disabled={savingKnowledge}
                    onClick={async () => {
                      setSavingKnowledge(true);
                      try {
                        const res = await api.approveKnowledge(task.id, Array.from(approved));
                        setProposals([]);
                        if (res.registered > 0) {
                          setSyncFeedback(`${res.registered} linha(s) no conhecimento do projeto`);
                          setTimeout(() => setSyncFeedback(null), 4000);
                        }
                      } catch (err: any) {
                        alert(`⚠️ ${err.message || 'Falha ao registrar'}`);
                      } finally {
                        setSavingKnowledge(false);
                      }
                    }}
                    className="text-[11px] px-3 py-1.5 rounded-md bg-fuchsia-600 hover:bg-fuchsia-500 text-white font-medium transition disabled:opacity-50"
                  >
                    {savingKnowledge
                      ? 'Salvando...'
                      : approved.size > 0
                      ? `Registrar ${approved.size}`
                      : 'Descartar tudo'}
                  </button>
                  <span className="text-[10px] text-[#8a93a8]">
                    {approved.size === 0 && 'nada marcado'}
                  </span>
                </div>
              </div>
            )}

            {task.status === 'REVIEW_READY' && (
              <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs flex items-center justify-between">
                <div>
                  <span className="font-bold">Aguardando Aprovação Humana</span>
                  <p className="text-[11px] text-amber-300/80 mt-0.5">Revise o código abaixo e aprove o merge.</p>
                </div>
                <button
                  onClick={handleMergeTask}
                  disabled={loadingAction}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white font-semibold px-3.5 py-1.5 rounded text-xs shadow flex items-center gap-1"
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
            {erroRefino && (
              <div className="p-3 rounded-lg border border-red-500/40 bg-red-500/10">
                <div className="text-[10px] text-red-300 uppercase font-semibold">
                  Não foi possível lapidar o prompt
                </div>
                <p className="text-red-200 mt-1">{erroRefino}</p>
                <p className="text-[#8a93a8] mt-2 text-[11px]">
                  A tarefa continua como rascunho — nenhuma especificação foi gravada.
                </p>
              </div>
            )}
            {task.refined_spec ? (
              <div className="p-3 bg-[#090a0f] rounded-lg border border-purple-500/30">
                <div className="text-slate-200">
                  <MarkdownRenderer content={task.refined_spec} />
                </div>
              </div>
            ) : (
              <div className="p-4 rounded-lg border border-dashed border-[#262a3b] text-center text-[#8a93a8]">
                Clique no botão "Lapidar Prompt" acima para gerar a especificação atômica.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modal Lightbox para Visualização de Imagem */}
      {previewImageModal && (
        <div
          className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-150"
          onClick={() => setPreviewImageModal(null)}
        >
          <div
            className="relative max-w-4xl max-h-[90vh] flex flex-col items-center bg-[#10121a] border border-[#262a3b] rounded-xl overflow-hidden shadow-2xl p-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-full flex items-center justify-between pb-2 mb-2 border-b border-[#262a3b] px-1 text-xs">
              <span className="text-slate-300 font-medium">Visualização da Imagem</span>
              <div className="flex items-center gap-2">
                <a
                  href={previewImageModal}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1.5 rounded hover:bg-[#202538] text-slate-400 hover:text-white transition flex items-center gap-1"
                  title="Abrir imagem original em nova aba"
                >
                  <ExternalLink size={14} />
                  <span className="text-[11px]">Abrir original</span>
                </a>
                <button
                  type="button"
                  onClick={() => setPreviewImageModal(null)}
                  className="p-1.5 rounded hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 transition"
                  title="Fechar"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            <img
              src={previewImageModal}
              alt="Visualização"
              className="max-h-[75vh] max-w-full object-contain rounded"
            />
          </div>
        </div>
      )}

      {/* Modal de Confirmação de Exclusão */}
      {isDeleteModalOpen && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#161822] border border-[#2d3247] rounded-xl max-w-md w-full p-5 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3 text-rose-400 mb-3">
              <div className="p-2 rounded-lg bg-rose-500/10 border border-rose-500/20">
                <AlertTriangle size={22} />
              </div>
              <div>
                <h3 className="font-bold text-white text-sm">Cancelar e Excluir Tarefa?</h3>
                <p className="text-[11px] text-[#8a93a8]">Esta ação é permanente e não poderá ser desfeita.</p>
              </div>
            </div>

            <div className="bg-[#0c0d13] p-3 rounded-lg border border-[#222638] text-xs space-y-2 text-slate-300 my-4">
              <div className="flex items-start gap-2 text-rose-300/90 font-medium">
                <span className="text-rose-400">•</span>
                <span>Processos em execução serão finalizados imediatamente.</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-slate-500">•</span>
                <span>A pasta da worktree e a branch git <code className="text-amber-300 bg-slate-900 px-1 py-0.5 rounded font-mono text-[10px]">task/{task.id.slice(0, 8)}</code> serão removidas.</span>
              </div>
              <div className="flex items-start gap-2 text-purple-300/90">
                <span className="text-purple-400">•</span>
                <span>A conversa vinculada no Antigravity será apagada.</span>
              </div>
              <div className="flex items-start gap-2 text-slate-400">
                <span className="text-slate-500">•</span>
                <span>Mensagens e histórico da tarefa serão excluídos do banco local.</span>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => setIsDeleteModalOpen(false)}
                className="px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:bg-[#222638] transition disabled:opacity-50"
              >
                Voltar
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={handleDeleteTask}
                className="px-4 py-1.5 rounded-lg text-xs font-medium bg-rose-600 hover:bg-rose-500 text-white transition flex items-center gap-1.5 disabled:opacity-50"
              >
                {isDeleting ? (
                  <>
                    <Loader2 size={13} className="animate-spin" />
                    Excluindo...
                  </>
                ) : (
                  <>
                    <Trash2 size={13} />
                    Sim, Excluir Tarefa
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};

