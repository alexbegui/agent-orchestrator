import pytest
from app.services.git_service import GitWorktreeService

def test_generate_branch_name_basic():
    service = GitWorktreeService()
    branch = service.generate_branch_name("SIGMA", "Criar no projeto certo")
    assert branch == "task/sigma-criar-no-projeto-certo"

def test_generate_branch_name_accents_and_special_chars():
    service = GitWorktreeService()
    branch = service.generate_branch_name("Patrimônio", "Lançamento de Bens & Exportação!")
    assert branch == "task/patrimonio-lancamento-de-bens-exportacao"

def test_generate_branch_name_collision_avoidance():
    service = GitWorktreeService()
    existing = [
        "task/sigma-criar-no-projeto-certo",
        "task/sigma-criar-no-projeto-certo-2"
    ]
    branch = service.generate_branch_name(
        project_name="SIGMA",
        task_title="Criar no projeto certo",
        existing_branches=existing
    )
    assert branch == "task/sigma-criar-no-projeto-certo-3"
