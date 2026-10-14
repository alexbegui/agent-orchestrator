/**
 * Sumário de entrega na aba de revisão.
 *
 * O agente terminava, o card ficava roxo em "Entregou · revisar", e o usuário
 * abria um diff cru sem nenhuma pista do que procurar. Revisar 500 linhas é
 * caro, e ele faz isso várias vezes por dia com vários agentes.
 *
 * O sumário vem ACIMA do diff porque é o que se lê antes dele — não é mais um
 * item da galeria de artefatos.
 *
 * E quando o agente não escreveu, a tela precisa DIZER que não escreveu. Uma
 * aba que simplesmente não mostra nada é indistinguível de uma que falhou ao
 * carregar — e o usuário conclui que o sumário sumiu, não que não existe.
 */
import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import { describe, test, expect, vi, beforeEach } from 'vitest';
import { TaskDrawer } from './TaskDrawer';
import type { Task } from '../types';

vi.mock('../services/api', () => ({
  api: {
    getMessages: vi.fn().mockResolvedValue([]),
    getTaskArtifacts: vi.fn(),
    getKnowledgeProposals: vi.fn().mockResolvedValue({ proposals: [] }),
    getDiff: vi.fn().mockResolvedValue({ diff: 'diff --git a/x b/x' }),
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

const SUMARIO = `# O que mudou
Troquei o cálculo de frete para a tabela nova.

# Como validei
pytest tests/test_frete.py — 4 verdes.

# O que NÃO fiz
Não mexi no frete internacional.`;

const tarefa: Task = {
  id: 'tarefa-1',
  project_id: 'projeto-1',
  title: 'Calcular frete',
  raw_prompt: 'arruma o frete',
  status: 'REVIEW_READY',
  runner_type: 'SUBPROCESS_CLI',
  runner_config: {},
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
} as Task;

async function montarNaRevisao() {
  const r = render(
    <TaskDrawer task={tarefa} onClose={() => {}} onTaskUpdated={() => {}} onTaskDeleted={() => {}} />
  );
  // O usuário abre a aba de revisão — é lá que o sumário vive.
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /diffs & revis/i }));
  });
  return r;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('sumário de entrega', () => {
  test('aparece na revisão quando o agente escreveu', async () => {
    const { api } = await import('../services/api');
    (api.getTaskArtifacts as ReturnType<typeof vi.fn>).mockResolvedValue({
      base: '/proj',
      artifacts: [],
      walkthrough: { conteudo: SUMARIO, truncado: false, fora_da_pasta: false },
    });

    await montarNaRevisao();

    await waitFor(() => {
      expect(screen.getByText(/tabela nova/)).toBeInTheDocument();
    });
    // A parte que o revisor mais precisa e que o agente mais omite:
    expect(screen.getByText(/frete internacional/)).toBeInTheDocument();
  });

  test('diz que não houve sumário em vez de ficar em silêncio', async () => {
    const { api } = await import('../services/api');
    (api.getTaskArtifacts as ReturnType<typeof vi.fn>).mockResolvedValue({
      base: '/proj',
      artifacts: [],
      walkthrough: null,
    });

    await montarNaRevisao();

    await waitFor(() => {
      expect(screen.getByText(/não deixou um sumário/i)).toBeInTheDocument();
    });
  });

  test('avisa quando o agente salvou o sumário fora da pasta da tarefa', async () => {
    const { api } = await import('../services/api');
    (api.getTaskArtifacts as ReturnType<typeof vi.fn>).mockResolvedValue({
      base: '/proj',
      artifacts: [],
      walkthrough: { conteudo: SUMARIO, truncado: false, fora_da_pasta: true },
    });

    await montarNaRevisao();

    await waitFor(() => {
      expect(screen.getByText(/fora da pasta/i)).toBeInTheDocument();
    });
  });
});
