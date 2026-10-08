import React from 'react';

interface DiffViewerProps {
  diffText: string;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({ diffText }) => {
  if (!diffText || diffText.trim() === '') {
    return (
      <div className="p-4 rounded-lg bg-[#090a0f] border border-[#262a3b] text-center text-xs text-[#8a93a8]">
        Nenhuma alteração detectada no worktree ainda.
      </div>
    );
  }

  const lines = diffText.split('\n');

  return (
    <div className="border border-[#262a3b] rounded-lg overflow-hidden bg-[#090a0f] text-xs font-mono">
      <div className="bg-[#1a1d28] px-3 py-2 border-b border-[#262a3b] flex items-center justify-between text-[11px]">
        <span className="text-white font-medium">Git Diff Unificado</span>
        <span className="text-emerald-400">Alterações no Worktree</span>
      </div>
      <div className="p-2 leading-relaxed custom-scroll overflow-x-auto max-h-[420px] overflow-y-auto">
        {lines.map((line, idx) => {
          let lineClass = 'text-slate-400 px-2 py-0.5';
          if (line.startsWith('+') && !line.startsWith('+++')) {
            lineClass = 'bg-emerald-950/40 text-emerald-300 border-l-2 border-emerald-500 px-2 py-0.5';
          } else if (line.startsWith('-') && !line.startsWith('---')) {
            lineClass = 'bg-rose-950/40 text-rose-300 border-l-2 border-rose-500 px-2 py-0.5';
          } else if (line.startsWith('diff --git') || line.startsWith('@@')) {
            lineClass = 'text-blue-300 bg-blue-950/30 font-semibold px-2 py-1 mt-1';
          }
          return (
            <div key={idx} className={lineClass}>
              {line || ' '}
            </div>
          );
        })}
      </div>
    </div>
  );
};
