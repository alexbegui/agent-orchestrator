/**
 * O botão de lapidar não dizia que estava trabalhando.
 *
 * Medido: o refino pelo CLI leva ~50 segundos (contra ~4s pela API direta).
 * O botão só ficava desabilitado nesse intervalo — e 50 segundos sem
 * informação é indistinguível de travamento. O usuário clica de novo, ou
 * fecha a tarefa achando que não funcionou.
 *
 * O número importa mais que a animação: saber que demora cerca de um minuto
 * transforma espera em expectativa.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { describe, test, expect, vi, beforeEach } from 'vitest';
import { TaskDrawer } from './TaskDrawer';
import type { Task } from '../types';

vi.mock('../services/api', () => ({
  api: {
    getMessages: vi.fn().mockResolvedValue([]),
    getTaskArtifacts: vi.fn().mockResolvedValue({ base: null, artifacts: [], walkthrough: null }),
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
  raw_prompt: 'arruma o frete',
  status: 'DRAFT',
  runner_type: 'SUBPROCESS_CLI',
  runner_config: {},
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
} as Task;

function montar() {
  return render(
    <TaskDrawer task={tarefa} onClose={() => {}} onTaskUpdated={() => {}} onTaskDeleted={() => {}} />
  );
}

async function clicarEmLapidar() {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /lapidar/i }));
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('enquanto lapida', () => {
  test('o botão diz que está trabalhando, não fica mudo', async () => {
    const { api } = await import('../services/api');
    (api.refineTask as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    montar();
    await clicarEmLapidar();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /lapidando/i })).toBeInTheDocument();
    });
  });

  test('avisa quanto tempo costuma levar', async () => {
    /** 50 segundos sem número parece travamento; com número, vira espera. */
    const { api } = await import('../services/api');
    (api.refineTask as ReturnType<typeof vi.fn>).mockReturnValue(new Promise(() => {}));

    montar();
    await clicarEmLapidar();

    await waitFor(() => {
      expect(screen.getByText(/minuto/i)).toBeInTheDocument();
    });
  });

  test('o aviso some quando termina', async () => {
    const { api } = await import('../services/api');
    (api.refineTask as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...tarefa, status: 'SPEC_READY', refined_spec: '## Objetivo\npronto',
    });

    montar();
    await clicarEmLapidar();

    await waitFor(() => {
      expect(screen.queryByText(/minuto/i)).not.toBeInTheDocument();
    });
  });

  test('o aviso some também quando falha', async () => {
    /** Deixar "lapidando..." na tela depois do erro seria mentir duas vezes. */
    const { api } = await import('../services/api');
    (api.refineTask as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('sem motor'));

    montar();
    await clicarEmLapidar();

    await waitFor(() => {
      expect(screen.getByText(/sem motor/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/minuto/i)).not.toBeInTheDocument();
  });
});
