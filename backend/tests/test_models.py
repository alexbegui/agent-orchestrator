import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.project import Project
from app.models.task import Task, TaskStatus, RunnerType
from app.models.message import Message, MessageRole


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_create_project(db_session):
    proj = Project(
        name="Projeto Alpha",
        root_path="C:/dev/proj-a",
        default_branch="main"
    )
    db_session.add(proj)
    db_session.commit()
    db_session.refresh(proj)

    assert proj.id is not None
    assert proj.name == "Projeto Alpha"
    assert proj.default_branch == "main"


def test_create_task_with_statuses_and_messages(db_session):
    proj = Project(name="Projeto Alpha", root_path="C:/dev/proj-a")
    db_session.add(proj)
    db_session.commit()

    task = Task(
        project_id=proj.id,
        title="Implementar Carrinho",
        raw_prompt="Quero checkout com cupom",
        status=TaskStatus.DRAFT,
        runner_type=RunnerType.SUBPROCESS_CLI,
        runner_config={"cli_cmd": "claude"}
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.id is not None
    assert task.status == TaskStatus.DRAFT
    assert task.runner_type == RunnerType.SUBPROCESS_CLI

    # Adicionar mensagem na thread isolada
    msg = Message(
        task_id=task.id,
        role=MessageRole.USER,
        content="Preciso de desconto de 10%"
    )
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)

    assert msg.id is not None
    assert msg.task_id == task.id
    assert msg.role == MessageRole.USER
    assert len(task.messages) == 1
