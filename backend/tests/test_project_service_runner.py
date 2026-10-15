import os
import pytest
from app.services.project_service_runner import ProjectServiceRunner


def test_infer_default_command(tmp_path):
    runner = ProjectServiceRunner()

    # 1. dotnet
    (tmp_path / "App.sln").write_text("")
    assert runner.infer_default_command(str(tmp_path)) == "dotnet run"
    (tmp_path / "App.sln").unlink()

    # 2. node dev
    (tmp_path / "package.json").write_text('{"scripts": {"dev": "vite"}}')
    assert runner.infer_default_command(str(tmp_path)) == "npm run dev"

    # 3. docker compose
    (tmp_path / "package.json").unlink()
    (tmp_path / "docker-compose.yml").write_text("version: '3'")
    assert runner.infer_default_command(str(tmp_path)) == "docker compose up"


def test_start_and_stop_service(tmp_path):
    runner = ProjectServiceRunner()
    root = str(tmp_path)

    # Inicia um comando rápido no Windows (ping em localhost)
    cmd = "cmd.exe /c ping 127.0.0.1 -n 5" if os.name == "nt" else "sleep 5"
    res = runner.start_service("proj-1", root, cmd)

    assert res["is_running"] is True
    assert res["pid"] > 0
    assert runner.is_alive(root) is True

    status = runner.get_status(root)
    assert status["is_running"] is True
    assert status["pid"] == res["pid"]

    # Para o serviço
    stopped = runner.stop_service(root)
    assert stopped is True
    assert runner.is_alive(root) is False


def test_restart_service(tmp_path):
    runner = ProjectServiceRunner()
    root = str(tmp_path)

    cmd = "cmd.exe /c ping 127.0.0.1 -n 5" if os.name == "nt" else "sleep 5"
    first = runner.start_service("proj-1", root, cmd)
    pid1 = first["pid"]

    second = runner.restart_service("proj-1", root, cmd)
    pid2 = second["pid"]

    assert second["is_running"] is True
    # O PID novo deve ser diferente ou reatribuído
    runner.stop_service(root)


def test_get_logs_and_detect_urls(tmp_path):
    runner = ProjectServiceRunner()
    root = str(tmp_path)
    os.makedirs(runner.service_dir(root), exist_ok=True)

    # Escreve um log simulando Vite / ASP.NET
    log_content = """
  VITE v5.4.14  ready in 230 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
  ➜  press h + enter to show help
"""
    with open(runner.log_path(root), "w", encoding="utf-8") as f:
        f.write(log_content)

    logs = runner.get_logs(root)
    assert "http://localhost:5173/" in logs

    urls = runner.detect_access_urls(root)
    assert "http://localhost:5173" in urls

