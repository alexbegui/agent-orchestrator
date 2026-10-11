import React, { useState, useMemo, useRef, useEffect } from 'react';
import { Message } from '../types';
import { Search, ChevronDown, ChevronUp, X, CornerDownRight } from 'lucide-react';

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

/** Primeira linha útil, sem markdown, para caber numa prévia. */
const resumir = (texto: string, limite: number): string => {
  const limpo = texto
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#*_`>]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  return limpo.length > limite ? `${limpo.slice(0, limite)}…` : limpo;
};

export const QuestionNavigator: React.FC<QuestionNavigatorProps> = ({
  messages,
  activeQuestionId,
  onSelectQuestion,
}) => {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState('');
  const buscaRef = useRef<HTMLInputElement>(null);

  const pares: QuestionPair[] = useMemo(() => {
    const lista: QuestionPair[] = [];
    let atual: Partial<QuestionPair> | null = null;
    let n = 0;

    for (const msg of messages) {
      if (msg.role === 'USER') {
        n += 1;
        atual = { index: n, question: msg, summary: resumir(msg.content, 150) || `Pergunta #${n}` };
        lista.push(atual as QuestionPair);
      } else if (msg.role === 'ASSISTANT' && atual && !atual.response) {
        atual.response = msg;
      }
    }
    return lista;
  }, [messages]);

  // Busca na pergunta E na resposta: muitas vezes você lembra do que o agente
  // respondeu, não de como perguntou.
  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return pares;
    return pares.filter(
      (p) =>
        p.question.content.toLowerCase().includes(q) ||
        (p.response?.content || '').toLowerCase().includes(q)
    );
  }, [pares, busca]);

  useEffect(() => {
    if (aberto) buscaRef.current?.focus();
  }, [aberto]);

  if (pares.length === 0) return null;

  const ativo = pares.find((p) => p.question.id === activeQuestionId);

  return (
    <div className="mb-3">
      {/* Fechado: ocupa uma linha. A lista horizontal ficava impraticável
          com muitas perguntas — era preciso varrer para o lado. */}
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-[#10121a] border border-[#222534] text-xs text-slate-300 hover:border-blue-500/40 hover:text-white transition"
      >
        <Search size={13} className="text-blue-400 shrink-0" />
        <span className="font-medium">{pares.length} perguntas</span>
        {ativo && !aberto && (
          <span className="text-[10px] text-blue-300 font-mono">· na #{ativo.index}</span>
        )}
        <span className="ml-auto flex items-center gap-1 text-[10px] text-[#8a93a8]">
          {aberto ? 'fechar' : 'buscar e navegar'}
          {aberto ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </span>
      </button>

      {aberto && (
        <div className="mt-2 rounded-lg bg-[#10121a] border border-[#222534] overflow-hidden">
          <div className="p-2 border-b border-[#1c1f2d] relative">
            <Search size={13} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              ref={buscaRef}
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              onKeyDown={(e) => e.key === 'Escape' && (busca ? setBusca('') : setAberto(false))}
              placeholder="Buscar na pergunta ou na resposta…"
              className="w-full bg-[#090a0f] border border-[#262a3b] rounded-md pl-8 pr-8 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
            {busca && (
              <button
                type="button"
                onClick={() => setBusca('')}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white"
              >
                <X size={12} />
              </button>
            )}
          </div>

          {busca && (
            <div className="px-3 py-1.5 text-[10px] text-[#8a93a8] border-b border-[#1c1f2d]">
              {filtrados.length === 0
                ? 'nenhuma pergunta contém esse texto'
                : `${filtrados.length} de ${pares.length}`}
            </div>
          )}

          {/* Vertical: lê-se de cima para baixo, como a conversa. */}
          <div className="max-h-[340px] overflow-y-auto custom-scroll">
            {filtrados.map((p) => {
              const isActive = activeQuestionId === p.question.id;
              return (
                <button
                  key={p.question.id}
                  type="button"
                  onClick={() => {
                    onSelectQuestion(p.question.id, p.response?.id);
                    setAberto(false);
                  }}
                  className={`w-full text-left px-3 py-2.5 border-b border-[#1a1d2a] last:border-b-0 transition ${
                    isActive ? 'bg-blue-600/15' : 'hover:bg-[#161824]'
                  }`}
                >
                  <div className="flex gap-2.5">
                    <span
                      className={`shrink-0 flex items-center justify-center w-5 h-5 rounded text-[10px] font-bold mt-0.5 ${
                        isActive ? 'bg-blue-500 text-white' : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {p.index}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-[11.5px] text-slate-200 leading-snug line-clamp-2">
                        {p.summary}
                      </div>
                      {/* A resposta também, porque achar a pergunta não basta:
                          o que você procura costuma estar na resposta. */}
                      {p.response && (
                        <div className="flex gap-1.5 mt-1 text-[10.5px] text-[#8a93a8] leading-snug">
                          <CornerDownRight size={11} className="shrink-0 mt-0.5 opacity-60" />
                          <span className="line-clamp-2">{resumir(p.response.content, 160)}</span>
                        </div>
                      )}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
