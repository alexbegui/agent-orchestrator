import React from 'react';
import { Task, CardState } from '../types';
import { Sparkles, Terminal } from 'lucide-react';
import { api } from '../services/api';

interface TaskCardProps {
  task: Task;
  onClick: () => void;
}

/**
 * Cada estado aparece ESCRITO no card, não só pela cor — ler "TE PERGUNTOU"
 * é mais rápido e mais seguro do que interpretar um tom de amarelo.
 */
const ESTADOS: Record<CardState, { texto: string; cor: string; borda: string; pulsa?: boolean }> = {
  EXECUTANDO:   { texto: 'Executando',          cor: 'text-blue-300',   borda: 'border-l-blue-500',   pulsa: true },
  TE_PERGUNTOU: { texto: 'Te perguntou',        cor: 'text-amber-300',  borda: 'border-l-amber-500' },
  ENTREGOU:     { texto: 'Entregou · revisar',  cor: 'text-purple-300', borda: 'border-l-purple-500' },
  PAROU:        { texto: 'Parou sem concluir',  cor: 'text-rose-300',   borda: 'border-l-rose-500' },
  CONCLUIDO:    { texto: 'Concluído · mergeado',cor: 'text-emerald-300',borda: 'border-l-emerald-500' },
  NA_FILA:      { texto: 'Na fila',             cor: 'text-slate-400',  borda: 'border-l-slate-600' },
};

/** "há 4min" a partir de um epoch em segundos. */
const decorrido = (epoch?: number): string => {
  if (!epoch) return '';
  const seg = Math.max(0, Math.floor(Date.now() / 1000 - epoch));
  if (seg < 60) return `${seg}s`;
  const min = Math.floor(seg / 60);
  if (min < 60) return `${min}min`;
  const h = Math.floor(min / 60);
  return `${h}h${String(min % 60).padStart(2, '0')}`;
};

export const TaskCard: React.FC<TaskCardProps> = ({ task, onClick }) => {
  const estado = ESTADOS[task.card_state || 'NA_FILA'];
  const mexeu = (task.changed_files || 0) > 0;

  return (
    <div
      onClick={onClick}
      className={`p-3.5 rounded-lg border border-l-[3px] bg-[#1a1d28] border-[#262a3b] ${estado.borda} cursor-pointer transition hover:border-blue-500/50 shadow-sm group`}
    >
      {/* O estado, escrito */}
      <div className={`flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide mb-1.5 ${estado.cor}`}>
        {estado.pulsa ? (
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-ping shrink-0" />
        ) : (
          <span className="w-1.5 h-1.5 rounded-sm bg-current shrink-0 opacity-80" />
        )}
        {estado.texto}
      </div>

      <div className="text-[10px] font-mono text-[#8a93a8] mb-1">
        {task.project_name ? task.project_name : `#${task.id.slice(0, 8)}`}
      </div>

      <h3 className="font-medium text-xs text-white group-hover:text-blue-300 transition line-clamp-2">
        {task.title}
      </h3>

      {/* O que você pediu — devolve o contexto sem abrir a tarefa */}
      {task.raw_prompt && (
        <p className="mt-1.5 pl-2 border-l-2 border-[#2d3247] text-[10px] leading-snug text-[#8fa0b8] line-clamp-2">
          {task.raw_prompt}
        </p>
      )}

      {/* Quanto mexeu — direto do git, é fato e não interpretação */}
      {mexeu && (
        <div className="mt-2 p-1.5 rounded bg-[#090a0f] border border-[#1c2030] text-[9px] font-mono flex gap-2.5">
          <span className="text-[#8a93a8]">{task.changed_files} arq.</span>
          {(task.lines_added || 0) > 0 && <span className="text-emerald-400">+{task.lines_added}</span>}
          {(task.lines_removed || 0) > 0 && <span className="text-rose-400">−{task.lines_removed}</span>}
        </div>
      )}

      <div className="mt-3 pt-2 border-t border-[#1c2030] flex items-center justify-between text-[10px] text-[#8a93a8]">
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-slate-400">{task.runner_type}</span>
          <button
            type="button"
            onClick={async (e) => {
              e.stopPropagation();
              try {
                await api.openTaskTerminal(task.id);
              } catch (err: any) {
                alert(`⚠️ Não foi possível abrir o terminal: ${err.message || 'falha desconhecida'}`);
              }
            }}
            title={task.worktree_path ? 'Abrir terminal no worktree da tarefa' : 'Abrir terminal na pasta do projeto'}
            className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-[#262a3b] text-[#8a93a8] hover:text-emerald-300 transition"
          >
            <Terminal size={11} />
          </button>
        </div>

        {task.card_state === 'EXECUTANDO' && task.started_at && (
          <span className="text-blue-300 font-medium">rodando há {decorrido(task.started_at)}</span>
        )}
        {task.card_state === 'PAROU' && <span className="text-rose-300 font-medium">processo sumiu</span>}
        {task.card_state === 'TE_PERGUNTOU' && <span className="text-amber-400 font-medium">responder</span>}
        {task.card_state === 'ENTREGOU' && <span className="text-purple-300 font-medium">👀 revisar diff</span>}
        {task.card_state === 'NA_FILA' && task.status === 'DRAFT' && (
          <span className="text-blue-400 font-medium flex items-center gap-1">
            <Sparkles size={10} /> Lapidar
          </span>
        )}
      </div>
    </div>
  );
};
