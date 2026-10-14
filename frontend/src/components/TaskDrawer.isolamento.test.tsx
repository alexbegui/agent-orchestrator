/**
 * Defeito D: o chat de uma tarefa mostrava a resposta de outra.
 *
 * O backend isola certo (canal por task_id, nenhuma sessão compartilhada, nada
 * de errado gravado no banco). O vazamento era só de tela: o App monta o
 * TaskDrawer sem `key`, então trocar de tarefa não remonta o componente — e o
 * estado `messages` da tarefa anterior seguia renderizado até a busca da nova
 * voltar da rede.
 *
 * O teste força exatamente essa janela: a segunda busca fica pendente, e
 * nenhuma mensagem da tarefa anterior pode aparecer nesse intervalo.
 */
import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { describe, test, expect, vi, beforeEach } from 'vitest';
import { TaskDrawer } from './TaskDrawer';
import type { Task } from '../types';

vi.mock('../services/api', () => ({
  api: {
    getMessages: vi.fn(),
    getTaskArtifacts: vi.fn().mockResolvedValue([]),
    getKnowledgeProposals: vi.fn().mockResolvedValue({ proposals: [] }),
    getDiff: vi.fn().mockResolvedValue({ diff: '' }),
  },
}));

// O WebSocket não existe no jsdom. O stub guarda o callback para o teste poder
// entregar uma mensagem à mão, como o servidor faria.
let entregarMensagem: ((msg: unknown) => void) | undefined;
vi.mock('../hooks/useTaskWebSocket', () => ({
  useTaskWebSocket: (_id: string, onNewMessage?: (m: unknown) => void) => {
    entregarMensagem = onNewMessage;
    return { logs: [], taskStatus: null };
  },
}));

vi.mock('./MarkdownRenderer', () => ({
  MarkdownRenderer: ({ content }: { content: string }) => <div>{content}</div>,
}));

import { api } from '../services/api';

const tarefa = (id: string, title: string): Task =>
  ({
    id,
    project_id: 'p1',
    title,
    raw_prompt: 'faça algo',
    status: 'SPEC_READY',
    runner_type: 'SUBPROCESS_CLI',
    runner_config: {},
    created_at: '2026-10-13T00:00:00Z',
    updated_at: '2026-10-13T00:00:00Z',
    is_alive: false,
    stalled: false,
    awaiting_you: false,
    card_state: 'NA_FILA',
  } as unknown as Task);

const mensagem = (id: string, taskId: string, content: string) => ({
  id,
  task_id: taskId,
  role: 'ASSISTANT',
  content,
  created_at: '2026-10-13T00:00:00Z',
  attachments: [],
});

const TAREFA_A = tarefa('aaaa-1111', 'Migrar a silver');
const TAREFA_B = tarefa('bbbb-2222', 'Criar o painel');
const RESPOSTA_DE_A = 'a silver foi migrada com deduplicação';

describe('isolamento do chat entre tarefas', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test('resposta de uma tarefa não aparece ao abrir outra', async () => {
    (api.getMessages as ReturnType<typeof vi.fn>).mockResolvedValueOnce([
      mensagem('m1', TAREFA_A.id, RESPOSTA_DE_A),
    ]);

    const props = {
      onClose: () => {},
      onTaskUpdated: () => {},
      onTaskDeleted: () => {},
    };

    const { rerender } = render(<TaskDrawer task={TAREFA_A} {...props} />);
    await screen.findByText(RESPOSTA_DE_A);

    // A busca da tarefa B fica pendente: é a janela em que o usuário via o
    // chat da tarefa anterior.
    (api.getMessages as ReturnType<typeof vi.fn>).mockReturnValueOnce(
      new Promise(() => {})
    );

    rerender(<TaskDrawer task={TAREFA_B} {...props} />);

    await waitFor(() => {
      expect(screen.queryByText(RESPOSTA_DE_A)).toBeNull();
    });
  });

  test('mensagem endereçada a outra tarefa é descartada', async () => {
    (api.getMessages as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    render(
      <TaskDrawer
        task={TAREFA_B}
        onClose={() => {}}
        onTaskUpdated={() => {}}
        onTaskDeleted={() => {}}
      />
    );

    await waitFor(() => expect(entregarMensagem).toBeDefined());

    // Chega pelo canal uma mensagem da tarefa A enquanto a B está aberta.
    await act(async () => {
      entregarMensagem!(mensagem('m9', TAREFA_A.id, RESPOSTA_DE_A));
    });

    expect(screen.queryByText(RESPOSTA_DE_A)).toBeNull();
  });
});
