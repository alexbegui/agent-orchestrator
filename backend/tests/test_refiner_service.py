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


def test_refiner_heuristic_refine():
    refiner = PromptRefinerService()
    raw = "Quero adicionar endpoint de calcular frete no projeto"
    available_files = [
        "app/main.py",
        "app/services/shipping.py",
        "tests/test_shipping.py",
        "README.md"
    ]
    
    spec = refiner.refine(raw, available_files=available_files)
    assert spec.objective is not None
    assert len(spec.target_files) > 0
    assert any("shipping" in f for f in spec.target_files)
    assert len(spec.steps) > 0
    assert len(spec.acceptance_criteria) > 0
