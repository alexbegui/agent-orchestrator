/**
 * O refino passou a poder falhar.
 *
 * Enquanto era regex no backend, `refineTask` nunca dava erro — e o
 * `catch` do handler só fazia `console.error`. Com IA de verdade a falha é
 * normal (chave ausente, 401, modelo fora do ar), e engolir o motivo deixa a
 * tela exatamente como estava: o usuário clica, nada muda, e ele não tem como
 * saber se o sistema está pensando, travado, ou sem chave configurada.
 *
 * O backend já manda o motivo real no corpo do 502. Estes testes exigem que
 * ele chegue aos olhos do usuário.
 */
import React from 'react';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { describe, test, expect, vi, beforeEach } from 'vitest';
import { TaskDrawer } from './TaskDrawer';
import type { Task } from '../types';

vi.mock('../services/api', () => ({
  api: {
    getMessages: vi.fn().mockResolvedValue([]),
    getTaskArtifacts: vi.fn().mockResolvedValue([]),
    getKnowledgeProposals: vi.fn().mockResolvedValue({ proposals: [] }),
    getDiff: vi.fn().mockResolvedValue({ diff: '' }),
    refineTask: vi.fn(),
  },
}));

class StubWebSocket {
  static OPEN = 1;
  readyState = 1;
  onmessage: ((e: unknown) => void) | null = null;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  send() {}
  close() {}
}
// @ts-expect-error jsdom não tem WebSocket
global.WebSocket = StubWebSocket;

const tarefa: Task = {
  id: 'tarefa-1',
  project_id: 'projeto-1',
  title: 'Calcular frete',
  raw_prompt: 'quero calcular frete',
  status: 'DRAFT',
  runner_type: 'SUBPROCESS_CLI',
  runner_config: {},
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
} as Task;

function montar() {
  return render(
    <TaskDrawer
      task={tarefa}
      onClose={() => {}}
      onTaskUpdated={() => {}}
      onTaskDeleted={() => {}}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('falha ao lapidar o prompt', () => {
  test('o motivo real da falha aparece na tela', async () => {
    const { api } = await import('../services/api');
    (api.refineTask as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Nenhuma chave de API configurada. Informe ANTHROPIC_API_KEY em Ajustes.')
    );

    montar();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /lapidar prompt/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/nenhuma chave de api configurada/i)).toBeInTheDocument();
    });
  });

  test('tentar de novo limpa o erro anterior', async () => {
    const { api } = await import('../services/api');
    const mock = api.refineTask as ReturnType<typeof vi.fn>;
    mock.mockRejectedValueOnce(new Error('A Anthropic devolveu HTTP 401'));

    montar();
    const botao = screen.getByRole('button', { name: /lapidar prompt/i });

    await act(async () => {
      fireEvent.click(botao);
    });
    await waitFor(() => expect(screen.getByText(/401/)).toBeInTheDocument());

    // Segunda tentativa fica pendente: o erro velho não pode continuar na tela
    // enquanto o sistema tenta de novo, senão parece que falhou outra vez.
    mock.mockReturnValue(new Promise(() => {}));
    await act(async () => {
      fireEvent.click(botao);
    });

    await waitFor(() => expect(screen.queryByText(/401/)).not.toBeInTheDocument());
  });
});
