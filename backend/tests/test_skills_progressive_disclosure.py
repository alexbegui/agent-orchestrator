"""
Testes de Progressive Disclosure para Skills do Antigravity/Superpowers.
Verifica que o skills_service descobre skills, extrai apenas nome e descrição
(frontmatter YAML) e formata um sumário leve, evitando inchaço de tokens no prompt.
"""
import os
import tempfile
import pytest

from app.services.skills_service import SkillsService


@pytest.fixture
def temp_skills_dir():
    with tempfile.TemporaryDirectory() as d:
        # Cria skill 1
        s1 = os.path.join(d, "skill-tdd")
        os.makedirs(s1)
        with open(os.path.join(s1, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: test-driven-development\ndescription: Use when implementing any feature\n---\n# Instrucoes longas aqui...")

        # Cria skill 2
        s2 = os.path.join(d, "skill-ui")
        os.makedirs(s2)
        with open(os.path.join(s2, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: ui-ux-pro-max\ndescription: Design intelligence and styles\n---\n# Muito texto de design...")

        yield d


def test_extrai_metadados_de_skill(temp_skills_dir):
    service = SkillsService(custom_paths=[temp_skills_dir])
    skills = service.list_skills()

    assert len(skills) == 2
    nomes = [s["name"] for s in skills]
    assert "test-driven-development" in nomes
    assert "ui-ux-pro-max" in nomes

    s_tdd = next(s for s in skills if s["name"] == "test-driven-development")
    assert s_tdd["description"] == "Use when implementing any feature"
    # Garante que o corpo longo NÃO está no resumo para não gastar tokens
    assert "Instrucoes longas" not in s_tdd.get("description", "")


def test_formata_sumario_compacto(temp_skills_dir):
    service = SkillsService(custom_paths=[temp_skills_dir])
    skills = service.list_skills()
    summary = service.format_summary(skills)

    assert "## Available Skills" in summary
    assert "- **test-driven-development**:" in summary
    assert "- **ui-ux-pro-max**:" in summary
    # Deve ser compacto (menos de 500 caracteres para 2 skills)
    assert len(summary) < 500


def test_api_endpoint_skills_available():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/api/tasks/skills/available")
        assert resp.status_code == 200
        dados = resp.json()
        assert isinstance(dados, list)
