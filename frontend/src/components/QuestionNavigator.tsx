import React from 'react';
import { Message } from '../types';
import { HelpCircle, ChevronRight, Hash, Sparkles } from 'lucide-react';

interface QuestionNavigatorProps {
  messages: Message[];
  activeQuestionId: string | null;
  onSelectQuestion: (questionId: string, responseId?: string) => void;
}

export interface QuestionPair {
  index: number;
  question: Message;
  response?: Message;
  summary: string;
}

export const QuestionNavigator: React.FC<QuestionNavigatorProps> = ({
  messages,
  activeQuestionId,
  onSelectQuestion,
}) => {
  // Constrói pares de Pergunta (USER) e Resposta (ASSISTANT)
  const pairs: QuestionPair[] = [];
  let currentPair: Partial<QuestionPair> | null = null;
  let qCount = 0;

  for (let i = 0; i < messages.length; i++) {
    const msg = messages[i];
    if (msg.role === 'USER') {
      qCount++;
      // Gera resumo curto da pergunta (até 45 caracteres)
      const cleanText = msg.content.replace(/\n/g, ' ').trim();
      const summary = cleanText.length > 42 ? `${cleanText.slice(0, 42)}...` : cleanText || `Pergunta #${qCount}`;

      currentPair = {
        index: qCount,
        question: msg,
        summary,
      };
      pairs.push(currentPair as QuestionPair);
    } else if (msg.role === 'ASSISTANT' && currentPair && !currentPair.response) {
      currentPair.response = msg;
    }
  }

  if (pairs.length === 0) return null;

  return (
    <div className="bg-[#10121a] border border-[#222534] rounded-xl p-2.5 mb-3 shadow-inner">
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#1c1f2d] text-[11px]">
        <div className="flex items-center gap-1.5 text-slate-400 font-medium">
          <HelpCircle size={13} className="text-blue-400" />
          <span>Navegador de Perguntas & Respostas</span>
          <span className="text-[10px] bg-blue-500/10 text-blue-400 px-1.5 py-0.2 rounded border border-blue-500/20 font-semibold">
            {pairs.length} {pairs.length === 1 ? 'dúvida' : 'dúvidas'}
          </span>
        </div>
        <span className="text-[10px] text-slate-500 hidden sm:inline">
          Clique para rolar direto para a pergunta e resposta
        </span>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1 custom-scroll">
        {pairs.map((pair) => {
          const isActive = activeQuestionId === pair.question.id;
          return (
            <button
              key={pair.question.id}
              type="button"
              onClick={() => onSelectQuestion(pair.question.id, pair.response?.id)}
              className={`flex-shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs transition border text-left ${
                isActive
                  ? 'bg-blue-600/20 border-blue-500/60 text-blue-200 shadow-sm shadow-blue-500/10'
                  : 'bg-[#161824] border-[#25293a] text-slate-300 hover:bg-[#1d2030] hover:border-slate-700 hover:text-white'
              }`}
              title={`Pergunta #${pair.index}: ${pair.question.content}`}
            >
              <span className={`flex items-center justify-center w-4 h-4 rounded text-[10px] font-bold ${
                isActive ? 'bg-blue-500 text-white' : 'bg-slate-800 text-slate-400'
              }`}>
                {pair.index}
              </span>
              <span className="truncate max-w-[200px] font-medium">
                {pair.summary}
              </span>
              {pair.response && (
                <span title="Resposta do assistente disponível">
                  <Sparkles size={11} className="text-blue-400 flex-shrink-0 ml-0.5" />
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
