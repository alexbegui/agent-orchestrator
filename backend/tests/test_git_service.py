import os
import subprocess
import pytest
from app.services.git_service import GitWorktreeService


@pytest.fixture
def temp_git_repo(tmp_path):
    repo_dir = tmp_path / "sample-repo"
    repo_dir.mkdir()
    
    # Initialize real git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True)
    
    # Create initial file & commit
    init_file = repo_dir / "README.md"
    init_file.write_text("# Sample Project\nInitial line\n", encoding="utf-8")
    
    subprocess.run(["git", "add", "README.md"], cwd=repo_dir, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo_dir, check=True)
    
    # Ensure branch name is main
    subprocess.run(["git", "branch", "-M", "main"], cwd=repo_dir, check=True)
    
    return str(repo_dir)


def test_git_worktree_lifecycle(temp_git_repo):
    git_svc = GitWorktreeService()
    task_id = "test-task-123"

    # 1. Create worktree
    worktree_path = git_svc.create_worktree(temp_git_repo, task_id)
    assert os.path.exists(worktree_path)
    assert os.path.exists(os.path.join(worktree_path, "README.md"))

    # 2. Modify file inside worktree and commit
    task_file = os.path.join(worktree_path, "feature.txt")
    with open(task_file, "w", encoding="utf-8") as f:
        f.write("Nova funcionalidade isolada\n")

    subprocess.run(["git", "add", "feature.txt"], cwd=worktree_path, check=True)
    subprocess.run(["git", "commit", "-m", "feat: add feature in worktree"], cwd=worktree_path, check=True)

    # 3. Get diff against main
    diff = git_svc.get_diff(temp_git_repo, task_id)
    assert "+Nova funcionalidade isolada" in diff

    # 4. Merge back to main
    merged = git_svc.merge_task(temp_git_repo, task_id, target_branch="main")
    assert merged is True
    assert os.path.exists(os.path.join(temp_git_repo, "feature.txt"))

    # 5. Remove worktree
    removed = git_svc.remove_worktree(temp_git_repo, task_id)
    assert removed is True
    assert not os.path.exists(worktree_path)
