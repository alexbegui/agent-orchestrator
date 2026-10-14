/**
 * Parte do defeito D: os logs vazavam entre tarefas.
 *
 * O hook só zerava `logs` quando o taskId virava null (painel fechado). Ao
 * TROCAR de tarefa ele mantinha o acumulado, então a aba Logs da tarefa B
 * mostrava o que o agente da tarefa A tinha escrito — para sempre, já que
 * nada mais limpava.
 */
import { renderHook, act } from '@testing-library/react';
import { describe, test, expect, beforeEach, vi } from 'vitest';
import { useTaskWebSocket } from './useTaskWebSocket';

const sockets: FakeSocket[] = [];

class FakeSocket {
  onmessage: ((e: { data: string }) => void) | null = null;
  close = vi.fn();
  constructor(public url: string) {
    sockets.push(this);
  }
}

beforeEach(() => {
  sockets.length = 0;
  vi.stubGlobal('WebSocket', FakeSocket);
});

describe('useTaskWebSocket', () => {
  test('logs da tarefa anterior não sobrevivem à troca de tarefa', () => {
    const { result, rerender } = renderHook(
      ({ id }: { id: string }) => useTaskWebSocket(id),
      { initialProps: { id: 'aaaa-1111' } }
    );

    act(() => {
      sockets[0].onmessage?.({
        data: JSON.stringify({ type: 'LOG', content: 'compilando a silver' }),
      });
    });
    expect(result.current.logs).toEqual(['compilando a silver']);

    rerender({ id: 'bbbb-2222' });

    expect(result.current.logs).toEqual([]);
  });
});
