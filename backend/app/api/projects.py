from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
import os

from app.core.database import get_db
from app.models.project import Project
from app.models.task import Task

router = APIRouter(prefix="/api/projects", tags=["projects"])


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
