"""
Testes para o JevService (System 1 Decision Engine).
Valida o Route-First (triagem e economia de tokens) e o Verify-After
(guardrails de conformidade sem custo de tokens de raciocínio).
"""
import pytest
from app.services.jev_service import JevService, TriageResult, GuardrailResult


def test_triage_tarefa_trivial_ou_exploracao():
    jev = JevService()
    # Pergunta ou leitura simples deve recomendar modelo leve (flash) e reportar economia
    result = jev.triage("onde fica o arquivo de configuracao .env no projeto?")
    assert isinstance(result, TriageResult)
    assert result.recommended_model in ("flash", "flash_lite")
    assert result.complexity_score < 0.5
    assert result.estimated_tokens_saved > 0
    assert result.confidence > 0.7


def test_triage_tarefa_complexa_recomenda_pro():
    jev = JevService()
    result = jev.triage("Refatorar toda a arquitetura de autenticacao migrando de NextAuth para Supabase com RBAC")
    assert isinstance(result, TriageResult)
    assert result.recommended_model == "pro"
    assert result.complexity_score >= 0.5
    assert result.task_type in ("FEATURE", "REFACTOR")


def test_guardrail_detecta_comando_proibido_no_diff():
    jev = JevService()
    diff_com_erro = """
    +++ b/package.json
    + "migrate": "npx prisma migrate dev"
    """
    result = jev.verify_diff(diff_com_erro, rules=["no_prisma_migrate_dev"])
    assert isinstance(result, GuardrailResult)
    assert result.passed is False
    assert any("prisma migrate dev" in v["description"].lower() for v in result.violations)


def test_guardrail_aprova_diff_limpo():
    jev = JevService()
    diff_limpo = """
    +++ b/src/components/Button.tsx
    + export const Button = () => <button>Click</button>;
    """
    result = jev.verify_diff(diff_limpo, rules=["no_prisma_migrate_dev"])
    assert isinstance(result, GuardrailResult)
    assert result.passed is True
    assert len(result.violations) == 0


def test_api_triage_e_verify_diff(tmp_path):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.main import app
    from app.core.database import Base, get_db

    db_file = tmp_path / "test_api_jev.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            proj_dir = tmp_path / "proj_jev"
            proj_dir.mkdir()
            p_resp = client.post("/api/projects", json={
                "name": "PJ", "root_path": str(proj_dir), "default_branch": "main"
            })
            proj_id = p_resp.json()["id"]

            t_resp = client.post("/api/tasks", json={
                "project_id": proj_id,
                "title": "Verificacao JEV",
                "raw_prompt": "onde fica a rota de login?"
            })
            task_id = t_resp.json()["id"]

            # 1. Testa endpoint de triagem
            triage_resp = client.post(f"/api/tasks/{task_id}/triage")
            assert triage_resp.status_code == 200
            t_data = triage_resp.json()
            assert t_data["recommended_model"] == "flash"
            assert t_data["estimated_tokens_saved"] > 0

            # 2. Testa endpoint de guardrails / verify-diff
            guard_resp = client.post(f"/api/tasks/{task_id}/verify-diff")
            assert guard_resp.status_code == 200
            g_data = guard_resp.json()
            assert g_data["passed"] is True
    finally:
        app.dependency_overrides.clear()


def test_remote_triage_mock(monkeypatch):
    from unittest.mock import MagicMock
    import httpx

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "model": "jev-1.13.0",
        "answers": {
            "task_type": {"choice": "REFACTOR", "confidence": 0.98},
            "is_complex": {"noul": 0.91},
            "complexity_level": {"score": 1.95}
        }
    }

    mock_client = MagicMock()
    mock_client.__enter__.return_value.post.return_value = mock_resp
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: mock_client)

    jev = JevService(api_key="ts_test_key")
    res = jev.triage("Reescrever sistema inteiro")
    assert res.task_type == "REFACTOR"
    assert res.recommended_model == "pro"
    assert "Jev System 1" in res.reasoning


def test_remote_triage_fallback_em_erro(monkeypatch):
    from unittest.mock import MagicMock
    import httpx

    def mock_post(*args, **kwargs):
        raise httpx.ConnectError("Erro de conexao simulado")

    mock_client = MagicMock()
    mock_client.__enter__.return_value.post.side_effect = mock_post
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: mock_client)

    jev = JevService(api_key="ts_test_key")
    # Deve acionar o fallback heurístico sem levantar exceção
    res = jev.triage("onde fica o arquivo .env?")
    assert res.task_type == "EXPLORATION"
    assert res.recommended_model == "flash"


