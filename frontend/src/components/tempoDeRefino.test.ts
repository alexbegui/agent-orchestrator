/**
 * Quanto tempo o refino costuma levar, por motor.
 *
 * O aviso do botão dizia "cerca de um minuto" para todo mundo. Medido depois,
 * num refino real de ponta a ponta:
 *
 *     claude → ~50s
 *     agy    → ~371s   (seis minutos)
 *
 * Para o agy a mensagem errava por seis vezes, e errava do jeito pior: o
 * usuário espera um minuto, conclui que travou, e clica de novo ou fecha a
 * tarefa — exatamente o problema que o aviso existia para resolver.
 *
 * O erro foi generalizar: medi o agy uma vez (38s, UMA chamada, árvore
 * pequena) e apliquei ao refino inteiro, que são duas chamadas sobre um
 * projeto real.
 */
import { describe, test, expect } from 'vitest';
import { tempoDeRefino } from './tempoDeRefino';

describe('aviso de tempo do refino', () => {
  test('o claude leva cerca de um minuto', () => {
    expect(tempoDeRefino({ cli: 'claude' })).toMatch(/um minuto/i);
  });

  test('o agy leva vários minutos, e o aviso precisa dizer isso', () => {
    const texto = tempoDeRefino({ cli: 'agy' });

    expect(texto).toMatch(/minutos/i);
    expect(texto).not.toMatch(/um minuto/i);
  });

  test('motor desconhecido recebe o aviso mais conservador', () => {
    /**
     * Prometer rápido e demorar irrita; prometer devagar e ser rápido, não.
     * Na dúvida, o aviso erra para o lado que não faz o usuário desistir.
     */
    const texto = tempoDeRefino({});

    expect(texto).toMatch(/minutos/i);
    expect(texto).not.toMatch(/um minuto/i);
  });

  test('todo aviso diz o que a IA está fazendo, não só que está ocupada', () => {
    /** "Lendo o projeto" é a razão de demorar — e o que torna a spec boa. */
    for (const cfg of [{ cli: 'claude' }, { cli: 'agy' }, {}]) {
      expect(tempoDeRefino(cfg)).toMatch(/lendo o projeto/i);
    }
  });

  test('o nome do motor pode vir com maiúscula ou descrito', () => {
    expect(tempoDeRefino({ cli: 'Claude Code CLI' })).toMatch(/um minuto/i);
    expect(tempoDeRefino({ cli: 'Antigravity (agy)' })).toMatch(/minutos/i);
  });
});
