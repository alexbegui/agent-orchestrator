from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
import os

from app.core.database import get_db
from app.models.project import Project
from app.models.task import Task
from app.services.terminal_service import terminal_service

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("/{project_id}/terminal")
def open_project_terminal(project_id: str, db: Session = Depends(get_db)):
    """Abre um terminal nativo na pasta do projeto."""
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    try:
        caminho = terminal_service.open_at(proj.root_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"opened_at": caminho}


class ProjectCreate(BaseModel):
    name: str
    root_path: str
    default_branch: Optional[str] = "main"


class ProjectResponse(BaseModel):
    id: str
    name: str
    root_path: str
    default_branch: str
    active_tasks_count: int = 0

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    results = []
    for p in projects:
        active_count = db.query(Task).filter(
            Task.project_id == p.id,
            Task.status.in_(["RUNNING", "REVIEW_READY"])
        ).count()
        results.append(ProjectResponse(
            id=p.id,
            name=p.name,
            root_path=p.root_path,
            default_branch=p.default_branch,
            active_tasks_count=active_count
        ))
    return results


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    normalized_path = os.path.abspath(data.root_path)
    if not os.path.isdir(normalized_path):
        raise HTTPException(status_code=400, detail="Diretório informado não existe no disco.")

    proj = Project(
        name=data.name,
        root_path=normalized_path,
        default_branch=data.default_branch or "main"
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return ProjectResponse(
        id=proj.id,
        name=proj.name,
        root_path=proj.root_path,
        default_branch=proj.default_branch,
        active_tasks_count=0
    )


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    default_branch: Optional[str] = None


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    active_count = db.query(Task).filter(
        Task.project_id == proj.id,
        Task.status.in_(["RUNNING", "REVIEW_READY"])
    ).count()
    return ProjectResponse(
        id=proj.id,
        name=proj.name,
        root_path=proj.root_path,
        default_branch=proj.default_branch,
        active_tasks_count=active_count
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, data: ProjectUpdate, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    if data.name is not None:
        trimmed = data.name.strip()
        if not trimmed:
            raise HTTPException(status_code=400, detail="O nome do projeto não pode ser vazio.")
        proj.name = trimmed

    if data.default_branch is not None and data.default_branch.strip():
        proj.default_branch = data.default_branch.strip()

    db.commit()
    db.refresh(proj)

    active_count = db.query(Task).filter(
        Task.project_id == proj.id,
        Task.status.in_(["RUNNING", "REVIEW_READY"])
    ).count()

    return ProjectResponse(
        id=proj.id,
        name=proj.name,
        root_path=proj.root_path,
        default_branch=proj.default_branch,
        active_tasks_count=active_count
    )
