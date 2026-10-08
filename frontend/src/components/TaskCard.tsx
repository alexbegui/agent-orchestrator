import React from 'react';
import { Task } from '../types';
import { Sparkles, Terminal, Clock, CheckCircle2, AlertCircle } from 'lucide-react';

interface TaskCardProps {
  task: Task;
  onClick: () => void;
}

export const TaskCard: React.FC<TaskCardProps> = ({ task, onClick }) => {
  const isRunning = task.status === 'RUNNING';
  const isReviewReady = task.status === 'REVIEW_READY';
  const isSpecReady = task.status === 'SPEC_READY';

  return (
    <div
      onClick={onClick}
      className={`p-3.5 rounded-lg border cursor-pointer transition shadow-sm group ${
        isRunning
          ? 'bg-[#1a1d28] border-blue-500/60 shadow-blue-950/30'
          : isReviewReady
          ? 'bg-[#1a1d28] border-amber-500/50 hover:border-amber-400'
          : isSpecReady
          ? 'bg-[#1a1d28] border-purple-500/40 hover:border-purple-400'
          : 'bg-[#1a1d28] border-[#262a3b] hover:border-blue-500/50'
      }`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] font-mono text-[#8a93a8]">#{task.id.slice(0, 8)}</span>
        {isRunning && (
          <span className="text-[10px] bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded-full font-medium flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-ping" />
            Rodando
          </span>
        )}
        {isReviewReady && (
          <span className="text-[10px] bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded-full font-semibold flex items-center gap-1">
            <AlertCircle size={10} />
            Revisar Diffs
          </span>
        )}
        {task.status === 'DONE' && (
          <span className="text-[10px] bg-emerald-500/20 text-emerald-300 px-2 py-0.5 rounded-full font-mono flex items-center gap-1">
            <CheckCircle2 size={10} />
            Mergeado
          </span>
        )}
        {task.status === 'DRAFT' && (
          <span className="text-[10px] bg-slate-800 text-slate-300 px-1.5 py-0.5 rounded">Rascunho</span>
        )}
        {task.status === 'SPEC_READY' && (
          <span className="text-[10px] bg-purple-500/20 text-purple-300 px-1.5 py-0.5 rounded">Spec Pronta</span>
        )}
      </div>

      <h3 className="font-medium text-xs text-white group-hover:text-blue-300 transition line-clamp-2">
        {task.title}
      </h3>

      {task.worktree_path && (
        <div className="mt-2 p-1 rounded bg-[#090a0f] border border-[#1c2030] text-[9px] font-mono text-slate-400 truncate">
          🌿 {task.worktree_path.split('\\').pop() || task.worktree_path}
        </div>
      )}

      <div className="mt-3 pt-2 border-t border-[#1c2030] flex items-center justify-between text-[10px] text-[#8a93a8]">
        <span className="font-mono text-slate-400">{task.runner_type}</span>
        {isReviewReady && <span className="text-amber-400 font-medium">👀 Pronto</span>}
        {task.status === 'DRAFT' && (
          <span className="text-blue-400 font-medium flex items-center gap-1">
            <Sparkles size={10} /> Lapidar
          </span>
        )}
      </div>
    </div>
  );
};
