from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from typing import List, Optional
import os

from app.core.database import get_db
from app.models.project import Project
from app.models.task import Task
from app.services.terminal_service import terminal_service
from app.services.project_service_runner import project_service_runner

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
    dev_command: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    root_path: str
    default_branch: str
    dev_command: Optional[str] = None
    is_service_running: bool = False
    service_pid: Optional[int] = None
    access_urls: List[str] = []
    active_tasks_count: int = 0

    model_config = ConfigDict(from_attributes=True)


def _enrich_project_response(p: Project, active_count: int) -> ProjectResponse:
    status_info = project_service_runner.get_status(p.root_path)
    # Se não tiver comando cadastrado no banco, infere o padrão para conveniência
    effective_dev_command = p.dev_command or project_service_runner.infer_default_command(p.root_path)
    return ProjectResponse(
        id=p.id,
        name=p.name,
        root_path=p.root_path,
        default_branch=p.default_branch,
        dev_command=effective_dev_command,
        is_service_running=status_info.get("is_running", False),
        service_pid=status_info.get("pid"),
        access_urls=status_info.get("access_urls", []),
        active_tasks_count=active_count
    )


@router.get("", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    results = []
    for p in projects:
        active_count = db.query(Task).filter(
            Task.project_id == p.id,
            Task.status.in_(["RUNNING", "REVIEW_READY"])
        ).count()
        results.append(_enrich_project_response(p, active_count))
    return results


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    normalized_path = os.path.abspath(data.root_path)
    if not os.path.isdir(normalized_path):
        try:
            os.makedirs(normalized_path, exist_ok=True)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Não foi possível criar o diretório informado: {e}"
            )

    proj = Project(
        name=data.name,
        root_path=normalized_path,
        default_branch=data.default_branch or "main",
        dev_command=data.dev_command.strip() if data.dev_command and data.dev_command.strip() else None
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return _enrich_project_response(proj, active_count=0)


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    default_branch: Optional[str] = None
    dev_command: Optional[str] = None


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    active_count = db.query(Task).filter(
        Task.project_id == proj.id,
        Task.status.in_(["RUNNING", "REVIEW_READY"])
    ).count()
    return _enrich_project_response(proj, active_count)


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

    if data.dev_command is not None:
        proj.dev_command = data.dev_command.strip() if data.dev_command.strip() else None

    db.commit()
    db.refresh(proj)

    active_count = db.query(Task).filter(
        Task.project_id == proj.id,
        Task.status.in_(["RUNNING", "REVIEW_READY"])
    ).count()

    return _enrich_project_response(proj, active_count)


# ==============================================================================
# ENDPOINTS DO RUNNER DO SERVIÇO DO PROJETO (START / STOP / RESTART / STATUS)
# ==============================================================================

@router.get("/{project_id}/service-status")
def get_project_service_status(project_id: str, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return project_service_runner.get_status(proj.root_path)


@router.get("/{project_id}/service-logs")
def get_project_service_logs(project_id: str, lines: int = 150, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    logs = project_service_runner.get_logs(proj.root_path, max_lines=lines)
    return {"logs": logs}


class ProjectCommandOverride(BaseModel):
    command: Optional[str] = None


@router.post("/{project_id}/start")
def start_project_service(project_id: str, body: Optional[ProjectCommandOverride] = None, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    cmd = (body.command.strip() if body and body.command and body.command.strip() else None) \
        or proj.dev_command \
        or project_service_runner.infer_default_command(proj.root_path)

    try:
        res = project_service_runner.start_service(proj.id, proj.root_path, cmd)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao iniciar projeto: {e}")


@router.post("/{project_id}/stop")
def stop_project_service(project_id: str, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    stopped = project_service_runner.stop_service(proj.root_path)
    return {"stopped": stopped, "is_running": False}


@router.post("/{project_id}/restart")
def restart_project_service(project_id: str, body: Optional[ProjectCommandOverride] = None, db: Session = Depends(get_db)):
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    cmd = (body.command.strip() if body and body.command and body.command.strip() else None) \
        or proj.dev_command \
        or project_service_runner.infer_default_command(proj.root_path)

    try:
        res = project_service_runner.restart_service(proj.id, proj.root_path, cmd)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao reiniciar projeto: {e}")
