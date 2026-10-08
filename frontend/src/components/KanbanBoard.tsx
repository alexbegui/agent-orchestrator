import React from 'react';
import { Task, TaskStatus } from '../types';
import { TaskCard } from './TaskCard';

interface KanbanBoardProps {
  tasks: Task[];
  onSelectTask: (task: Task) => void;
}

const COLUMNS: { id: TaskStatus; label: string; dotColor: string }[] = [
  { id: 'DRAFT', label: '1. Rascunho', dotColor: 'bg-slate-500' },
  { id: 'SPEC_READY', label: '2. Prompt Lapidado', dotColor: 'bg-purple-500' },
  { id: 'RUNNING', label: '3. Em Execução (Worktree)', dotColor: 'bg-blue-500' },
  { id: 'REVIEW_READY', label: '4. Aguardando Revisão', dotColor: 'bg-amber-500' },
  { id: 'DONE', label: '5. Concluído & Mergeado', dotColor: 'bg-emerald-500' },
  { id: 'FAILED', label: '6. Falhou / Erro', dotColor: 'bg-rose-500' },
];

export const KanbanBoard: React.FC<KanbanBoardProps> = ({ tasks, onSelectTask }) => {
  return (
    <div className="flex gap-4 min-w-[1250px] h-[calc(100vh-140px)] pb-2 overflow-x-auto custom-scroll">
      {COLUMNS.map((col) => {
        const colTasks = tasks.filter((t) => t.status === col.id);
        return (
          <div
            key={col.id}
            className="flex-1 flex flex-col bg-[#12141c] border border-[#262a3b] rounded-xl p-3 min-w-[210px]"
          >
            <div className="flex items-center justify-between mb-3 px-1">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full ${col.dotColor}`} />
                <span className="font-semibold text-xs text-slate-300">{col.label}</span>
              </div>
              <span className="text-[11px] font-mono text-[#8a93a8] bg-[#090a0f] px-2 py-0.5 rounded">
                {colTasks.length}
              </span>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 custom-scroll pr-1">
              {colTasks.map((task) => (
                <TaskCard key={task.id} task={task} onClick={() => onSelectTask(task)} />
              ))}
              {colTasks.length === 0 && (
                <div className="h-24 border border-dashed border-[#1c2030] rounded-lg flex items-center justify-center text-[11px] text-[#8a93a8]">
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
