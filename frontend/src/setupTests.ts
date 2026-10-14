/**
 * Preparo do ambiente de teste.
 *
 * O jsdom não implementa APIs de layout do navegador. Sem estes stubs, o teste
 * quebra por falta de `scrollIntoView` antes mesmo de chegar ao que investiga.
 */
import '@testing-library/jest-dom/vitest';

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
