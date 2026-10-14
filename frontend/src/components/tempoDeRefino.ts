/**
 * O que o botão mostra enquanto lapida o prompt.
 *
 * Medido num refino real de ponta a ponta, 13/10/2026:
 *
 *     claude → ~50s
 *     agy    → ~371s   (seis minutos)
 *
 * O aviso antes dizia "cerca de um minuto" para todo mundo, e para o agy
 * errava por seis vezes — do jeito pior: o usuário espera um minuto, conclui
 * que travou, e clica de novo ou fecha a tarefa. Era exatamente o problema
 * que o aviso existia para resolver.
 */

/** O refino é lento porque a IA lê o projeto — e é isso que faz a spec ser boa. */
const OQUE_ESTA_FAZENDO = 'a IA está lendo o projeto';

export function tempoDeRefino(runnerConfig: { cli?: string } | null | undefined): string {
  const cli = (runnerConfig?.cli ?? '').toLowerCase();

  if (cli.includes('claude')) {
    return `${OQUE_ESTA_FAZENDO} — costuma levar cerca de um minuto`;
  }

  // Tudo que não é claude cai aqui, inclusive motor desconhecido: prometer
  // rápido e demorar irrita; prometer devagar e ser rápido, não. Na dúvida o
  // aviso erra para o lado que não faz o usuário desistir no meio.
  return `${OQUE_ESTA_FAZENDO} — pode levar vários minutos`;
}
