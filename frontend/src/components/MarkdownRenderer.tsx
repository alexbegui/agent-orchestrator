import React, { useState } from 'react';
import { marked } from 'marked';
import { Copy, Check, Terminal, Code2 } from 'lucide-react';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

interface ParsedPart {
  type: 'markdown' | 'code';
  content: string;
  lang?: string;
}

// Configura o marked para GFM padrão
marked.setOptions({
  gfm: true,
  breaks: true,
});

const CodeBlock: React.FC<{ code: string; lang?: string }> = ({ code, lang }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Falha ao copiar código:', err);
    }
  };

  const displayLang = (lang || 'code').trim().toLowerCase();

  return (
    <div className="my-3 rounded-lg overflow-hidden border border-[#262a3b] bg-[#0c0d14] shadow-md">
      {/* Barra de cabeçalho do código */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-[#141722] border-b border-[#262a3b] text-[11px]">
        <div className="flex items-center gap-1.5 text-slate-400 font-mono">
          <Code2 size={13} className="text-blue-400" />
          <span className="font-semibold uppercase tracking-wider">{displayLang}</span>
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-white px-2 py-0.5 rounded hover:bg-[#202538] transition font-medium"
          title="Copiar código para a área de transferência"
        >
          {copied ? (
            <>
              <Check size={11} className="text-emerald-400" />
              <span className="text-emerald-400 font-semibold">Copiado!</span>
            </>
          ) : (
            <>
              <Copy size={11} />
              <span>Copiar</span>
            </>
          )}
        </button>
      </div>

      {/* Conteúdo do código formatado */}
      <pre className="p-3.5 text-[11.5px] font-mono leading-relaxed overflow-x-auto text-slate-100 bg-[#08090f] custom-scroll select-text">
        <code>{code}</code>
      </pre>
    </div>
  );
};

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content, className = '' }) => {
  // Separa trechos comuns de blocos de código com cercas ```
  const parts: ParsedPart[] = [];
  const codeBlockRegex = /```([a-zA-Z0-9_\-\+]*)[^\S\r\n]*\r?\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      parts.push({
        type: 'markdown',
        content: content.slice(lastIndex, match.index),
      });
    }
    parts.push({
      type: 'code',
      lang: match[1] || 'text',
      content: match[2].replace(/\r?\n$/, ''),
    });
    lastIndex = codeBlockRegex.lastIndex;
  }

  if (lastIndex < content.length) {
    parts.push({
      type: 'markdown',
      content: content.slice(lastIndex),
    });
  }

  // Fallback caso a string não tenha blocos fechados
  if (parts.length === 0) {
    parts.push({ type: 'markdown', content });
  }

  return (
    <div className={`space-y-1 ${className}`}>
      {parts.map((part, index) => {
        if (part.type === 'code') {
          return <CodeBlock key={index} code={part.content} lang={part.lang} />;
        }

        const html = marked.parse(part.content) as string;
        return (
          <div
            key={index}
            className="markdown-body"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        );
      })}
    </div>
  );
};
