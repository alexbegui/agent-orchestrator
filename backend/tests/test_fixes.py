import os
import subprocess
import pytest
from app.services.git_service import GitWorktreeService
from app.services.runner_service import RunnerService


@pytest.fixture
def temp_git_repo(tmp_path):
    repo_dir = tmp_path / "repo-conflict"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    
    file_a = repo_dir / "file.txt"
    file_a.write_text("Linha base\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_dir, check=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo_dir, check=True)
    return str(repo_dir)


def test_merge_conflict_aborts_and_keeps_repo_clean(temp_git_repo):
    git_svc = GitWorktreeService()
    task_id = "task-conflict"

    # 1. Cria worktree
    worktree_path = git_svc.create_worktree(temp_git_repo, task_id)

    # 2. Altera o arquivo no main
    file_main = os.path.join(temp_git_repo, "file.txt")
    with open(file_main, "w", encoding="utf-8") as f:
        f.write("Alteracao na main\n")
    subprocess.run(["git", "add", "file.txt"], cwd=temp_git_repo, check=True)
    subprocess.run(["git", "commit", "-m", "main edit"], cwd=temp_git_repo, check=True)

    # 3. Altera a mesma linha na worktree
    file_worktree = os.path.join(worktree_path, "file.txt")
    with open(file_worktree, "w", encoding="utf-8") as f:
        f.write("Alteracao concorrente na worktree\n")
    subprocess.run(["git", "add", "file.txt"], cwd=worktree_path, check=True)
    subprocess.run(["git", "commit", "-m", "worktree edit"], cwd=worktree_path, check=True)

    # 4. Tenta o merge - deve retornar False e ABORTAR o merge
    merged = git_svc.merge_task(temp_git_repo, task_id, target_branch="main")
    assert merged is False

    # 5. O repositório não pode estar em estado MERGING
    merge_head = os.path.join(temp_git_repo, ".git", "MERGE_HEAD")
    assert not os.path.exists(merge_head)

    # Limpa
    git_svc.remove_worktree(temp_git_repo, task_id)


def test_diff_includes_uncommitted_worktree_changes(temp_git_repo):
    git_svc = GitWorktreeService()
    task_id = "task-uncommitted"

    worktree_path = git_svc.create_worktree(temp_git_repo, task_id)
    new_file = os.path.join(worktree_path, "uncommitted.txt")
    with open(new_file, "w", encoding="utf-8") as f:
        f.write("Texto nao commitado pelo agente\n")

    diff = git_svc.get_diff(temp_git_repo, task_id, base_branch="main")
    assert "+Texto nao commitado pelo agente" in diff

    git_svc.remove_worktree(temp_git_repo, task_id)


def test_runner_resolves_claude_and_agy_commands():
    runner = RunnerService()
    
    # Com config explicita
    cmd_claude = runner.resolve_cli_command("SUBPROCESS_CLI", "Refatorar", {"cli": "claude"})
    assert "claude" in cmd_claude[0].lower()
    assert "-p" in cmd_claude
    assert "Refatorar" in cmd_claude

    cmd_agy = runner.resolve_cli_command("SUBPROCESS_CLI", "Criar tela", {"cli": "agy"})
    assert "agy" in cmd_agy[0].lower() or "agentapi" in cmd_agy[0].lower()
    assert "Criar tela" in cmd_agy
