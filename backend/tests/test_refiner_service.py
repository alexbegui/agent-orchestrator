import pytest
from app.services.refiner_service import PromptRefinerService, RefinedSpec


def test_refiner_format_spec():
    refiner = PromptRefinerService()
    spec = RefinedSpec(
        objective="Criar tela de checkout com resumo de carrinho",
        target_files=["src/components/Checkout.tsx", "src/pages/Cart.tsx"],
        steps=["Criar componente", "Adicionar validação de cupom", "Adicionar testes"],
        acceptance_criteria=["Resumo de valor correto", "Teste unitário 100% verde"]
    )

    markdown = refiner.to_markdown(spec)
    assert "## Objetivo" in markdown
    assert "Criar tela de checkout" in markdown
    assert "## Arquivos Alvo" in markdown
    assert "src/components/Checkout.tsx" in markdown
    assert "## Passos de Execução" in markdown
    assert "## Critérios de Aceite" in markdown


# O antigo `test_refiner_heuristic_refine` foi removido junto com o regex que
# ele cobria. Ele não podia falhar: três das quatro asserções eram verdadeiras
# por construção (listas fixas no código), e a quarta — `any("shipping" in f)`,
# a única que tentava provar o context pruning — passava por acidente. Nenhuma
# palavra do prompt casava com o caminho; o arquivo entrava pelo fallback
# `"app" in f`, ou seja, pelo prefixo de diretório do próprio exemplo. Trocando
# `app/services/shipping.py` por `src/services/shipping.py` o teste falhava com
# o mesmo código. O contrato novo está em test_refiner_ia.py.
