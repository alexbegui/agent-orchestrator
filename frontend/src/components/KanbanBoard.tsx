import React from 'react';
import { Task, CardState } from '../types';
import { TaskCard } from './TaskCard';

interface KanbanBoardProps {
  tasks: Task[];
  onSelectTask: (task: Task) => void;
}

/**
 * As colunas agora refletem o ESTADO REAL do agente, não o status gravado
 * no banco. "Te perguntou" e "Entregou" ficam separados de propósito:
 * responder leva segundos, revisar um diff leva minutos — o usuário escolhe
 * pelo tempo que tem.
 */
const COLUMNS: { id: CardState; label: string; sub: string; dot: string; border: string }[] = [
  {
    id: 'EXECUTANDO',
    label: '🔵 Executando',
    sub: 'Trabalhando agora no que você pediu. Nada a fazer.',
    dot: 'bg-blue-500',
    border: 'border-blue-500/40',
  },
  {
    id: 'TE_PERGUNTOU',
    label: '🟡 Te perguntou',
    sub: 'Parou e precisa da sua resposta para seguir.',
    dot: 'bg-amber-500',
    border: 'border-amber-500/40',
  },
  {
    id: 'ENTREGOU',
    label: '🟣 Entregou',
    sub: 'Terminou e tem diff para você revisar.',
    dot: 'bg-purple-500',
    border: 'border-purple-500/40',
  },
  {
    id: 'PAROU',
    label: '🔴 Parou',
    sub: 'Morreu sem concluir — travou ou foi encerrado.',
    dot: 'bg-rose-500',
    border: 'border-rose-500/40',
  },
  {
    id: 'CONCLUIDO',
    label: '🟢 Concluído',
    sub: 'Revisado e mergeado. Já está no seu projeto.',
    dot: 'bg-emerald-500',
    border: 'border-[#262a3b]',
  },
  {
    id: 'NA_FILA',
    label: '⚪ Na fila',
    sub: 'Ainda não começaram. Esperando você mandar rodar.',
    dot: 'bg-slate-500',
    border: 'border-[#262a3b]',
  },
];

export const KanbanBoard: React.FC<KanbanBoardProps> = ({ tasks, onSelectTask }) => {
  return (
    <div className="flex gap-4 min-w-[1250px] h-[calc(100vh-140px)] pb-2 overflow-x-auto custom-scroll">
      {COLUMNS.map((col) => {
        const colTasks = tasks.filter((t) => (t.card_state || 'NA_FILA') === col.id);
        return (
          <div
            key={col.id}
            className={`flex-1 flex flex-col bg-[#12141c] border ${col.border} rounded-xl p-3 min-w-[232px]`}
          >
            <div className="flex items-center justify-between mb-1 px-1">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${col.dot}`} />
                <span className="font-semibold text-xs text-slate-200">{col.label}</span>
              </div>
              <span className="text-[11px] font-mono text-[#8a93a8] bg-[#090a0f] px-2 py-0.5 rounded">
                {colTasks.length}
              </span>
            </div>
            <p className="text-[10px] text-[#8a93a8] leading-snug px-1 mb-3 min-h-[26px]">{col.sub}</p>

            <div className="flex-1 overflow-y-auto space-y-3 custom-scroll pr-1">
              {colTasks.map((task) => (
                <TaskCard key={task.id} task={task} onClick={() => onSelectTask(task)} />
              ))}
              {colTasks.length === 0 && (
                <div className="h-20 border border-dashed border-[#1c2030] rounded-lg flex items-center justify-center text-[11px] text-[#8a93a8]">
                  Vazio
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};
