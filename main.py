import os
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    inspect,
    text,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    Session,
    relationship,
)


# =========================================================
# CONFIGURAÇÕES
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./manutencao.db",
)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql://",
        1,
    )

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )

connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False,
    }

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


# =========================================================
# SEGURANÇA
# =========================================================

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto",
)


# =========================================================
# FASTAPI
# =========================================================

app = FastAPI(
    title="Sistema de Manutenção",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv(
        "SECRET_KEY",
        secrets.token_hex(32),
    ),
    same_site="lax",
    https_only=os.getenv(
        "COOKIE_SECURE",
        "false",
    ).lower() == "true",
)


# =========================================================
# ARQUIVOS ESTÁTICOS
# =========================================================

app.mount(
    "/static",
    StaticFiles(
        directory=BASE_DIR / "static",
    ),
    name="static",
)

app.mount(
    "/uploads",
    StaticFiles(
        directory=UPLOAD_DIR,
    ),
    name="uploads",
)

templates = Jinja2Templates(
    directory=BASE_DIR / "templates",
)


# =========================================================
# FUNCIONÁRIOS DA MANUTENÇÃO
# =========================================================

MAINTENANCE_EMPLOYEES = [
    "João Maria",
    "João Antunes",
    "Valdemir",
    "Alexandro",
    "Diego",
    "Claudinei",
]


# =========================================================
# BANCO DE DADOS
# =========================================================

class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
    )

    name = Column(
        String(120),
        nullable=False,
    )

    username = Column(
        String(80),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash = Column(
        String(255),
        nullable=False,
    )

    role = Column(
        String(30),
        nullable=False,
    )

    active = Column(
        Integer,
        default=1,
    )

    requests = relationship(
        "MaintenanceRequest",
        foreign_keys="MaintenanceRequest.requester_id",
        back_populates="requester",
    )


class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"

    id = Column(
        Integer,
        primary_key=True,
    )

    sector = Column(
        String(150),
        nullable=False,
    )

    equipment = Column(
        String(150),
        nullable=False,
    )

    description = Column(
        Text,
        nullable=False,
    )

    priority = Column(
        String(20),
        nullable=False,
        default="Média",
    )

    status = Column(
        String(30),
        nullable=False,
        default="PENDENTE",
    )

    requester_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    # Usuário que assumiu/agendou a solicitação
    assigned_to_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.now,
    )

    # =====================================================
    # EXECUÇÃO REAL
    # =====================================================

    started_at = Column(
        DateTime,
        nullable=True,
    )

    finished_at = Column(
        DateTime,
        nullable=True,
    )

    # =====================================================
    # AGENDAMENTO
    # =====================================================

    planned_at = Column(
        DateTime,
        nullable=True,
    )

    scheduled_employee = Column(
        String(120),
        nullable=True,
    )

    scheduling_note = Column(
        Text,
        nullable=True,
    )

    # Quem realmente executou o serviço
    executor_name = Column(
        String(120),
        nullable=True,
    )

    # =====================================================
    # RELATÓRIO
    # =====================================================

    diagnosis = Column(
        Text,
        nullable=True,
    )

    cause = Column(
        Text,
        nullable=True,
    )

    service_done = Column(
        Text,
        nullable=True,
    )

    parts_used = Column(
        Text,
        nullable=True,
    )

    observations = Column(
        Text,
        nullable=True,
    )

    requester = relationship(
        "User",
        foreign_keys=[requester_id],
        back_populates="requests",
    )

    assigned_to = relationship(
        "User",
        foreign_keys=[assigned_to_id],
    )

    attachments = relationship(
        "Attachment",
        back_populates="request",
        cascade="all, delete-orphan",
    )

    history = relationship(
        "History",
        back_populates="request",
        cascade="all, delete-orphan",
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(
        Integer,
        primary_key=True,
    )

    request_id = Column(
        Integer,
        ForeignKey("maintenance_requests.id"),
        nullable=False,
    )

    filename = Column(
        String(255),
        nullable=False,
    )

    original_name = Column(
        String(255),
        nullable=False,
    )

    request = relationship(
        "MaintenanceRequest",
        back_populates="attachments",
    )


class History(Base):
    __tablename__ = "history"

    id = Column(
        Integer,
        primary_key=True,
    )

    request_id = Column(
        Integer,
        ForeignKey("maintenance_requests.id"),
        nullable=False,
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
    )

    action = Column(
        String(255),
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=datetime.now,
    )

    request = relationship(
        "MaintenanceRequest",
        back_populates="history",
    )

    user = relationship(
        "User",
    )


# =========================================================
# CRIAÇÃO / ATUALIZAÇÃO DAS TABELAS
# =========================================================

Base.metadata.create_all(
    bind=engine,
)


def migrate_database():
    """
    Adiciona as novas colunas em bancos existentes
    sem apagar os dados atuais.
    """

    inspector = inspect(engine)

    tables = inspector.get_table_names()

    if "maintenance_requests" not in tables:
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns(
            "maintenance_requests"
        )
    }

    new_columns = {
        "planned_at": "DATETIME",
        "scheduled_employee": "VARCHAR(120)",
        "scheduling_note": "TEXT",
        "executor_name": "VARCHAR(120)",
    }

    with engine.begin() as connection:

        for column_name, column_type in new_columns.items():

            if column_name not in existing_columns:

                connection.execute(
                    text(
                        f"ALTER TABLE maintenance_requests "
                        f"ADD COLUMN {column_name} {column_type}"
                    )
                )


migrate_database()


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def current_user(
    request: Request,
    db: Session,
):
    user_id = request.session.get(
        "user_id",
    )

    if not user_id:
        return None

    return db.get(
        User,
        user_id,
    )


def require_role(
    user,
    roles,
):
    if not user or user.role not in roles:
        raise HTTPException(
            status_code=403,
            detail="Acesso não autorizado",
        )


def require_login(
    request: Request,
    db: Session,
):
    user = current_user(
        request,
        db,
    )

    if not user:
        return (
            None,
            RedirectResponse(
                "/login",
                status_code=303,
            ),
        )

    return user, None


def add_history(
    db,
    req,
    user,
    action,
):
    db.add(
        History(
            request_id=req.id,
            user_id=user.id,
            action=action,
        )
    )

    db.commit()


def parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value
        )
    except ValueError:
        return None


def get_status_counts(db: Session):
    """
    Centraliza a contagem de solicitações por status,
    usada no Dashboard e no badge da sidebar.
    """

    counts = {}

    for key, status_value in (
        ("pendente", "PENDENTE"),
        ("agendada", "AGENDADA"),
        ("atendimento", "EM ATENDIMENTO"),
        ("concluida", "CONCLUÍDA"),
    ):
        counts[key] = (
            db.query(MaintenanceRequest)
            .filter(MaintenanceRequest.status == status_value)
            .count()
        )

    return counts


# =========================================================
# USUÁRIOS INICIAIS
# =========================================================

def seed_admin():
    db = SessionLocal()

    try:

        if not db.query(User).first():

            db.add_all(
                [
                    User(
                        name="Administrador",
                        username="admin",
                        password_hash=pwd_context.hash(
                            "admin123"
                        ),
                        role="adm",
                    ),
                    User(
                        name="Líder de Manutenção",
                        username="manutencao",
                        password_hash=pwd_context.hash(
                            "manutencao123"
                        ),
                        role="manutencao",
                    ),
                    User(
                        name="Líder de Produção",
                        username="lider",
                        password_hash=pwd_context.hash(
                            "lider123"
                        ),
                        role="lider",
                    ),
                ]
            )

            db.commit()

    finally:
        db.close()


seed_admin()


# =========================================================
# PÁGINA INICIAL
# =========================================================

@app.get(
    "/",
    response_class=HTMLResponse,
)
def index(
    request: Request,
    db: Session = Depends(get_db),
):
    user = current_user(
        request,
        db,
    )

    if not user:
        return RedirectResponse(
            "/login",
            status_code=303,
        )

    if user.role == "lider":
        return RedirectResponse(
            "/minhas-solicitacoes",
            status_code=303,
        )

    return RedirectResponse(
        "/painel",
        status_code=303,
    )


# =========================================================
# LOGIN
# =========================================================

@app.get(
    "/login",
    response_class=HTMLResponse,
)
def login_page(
    request: Request,
):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": None,
        },
    )


@app.post(
    "/login",
    response_class=HTMLResponse,
)
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(
            User.username == username,
            User.active == 1,
        )
        .first()
    )

    if not user or not pwd_context.verify(
        password,
        user.password_hash,
    ):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Usuário ou senha inválidos.",
            },
        )

    request.session["user_id"] = user.id

    return RedirectResponse(
        "/",
        status_code=303,
    )


@app.get("/logout")
def logout(
    request: Request,
):
    request.session.clear()

    return RedirectResponse(
        "/login",
        status_code=303,
    )


# =========================================================
# NOVA SOLICITAÇÃO
# =========================================================

@app.get(
    "/nova-solicitacao",
    response_class=HTMLResponse,
)
def new_request_page(
    request: Request,
    db: Session = Depends(get_db),
):
    user, redirect = require_login(
        request,
        db,
    )

    if redirect:
        return redirect

    require_role(
        user,
        ["lider", "adm"],
    )

    return templates.TemplateResponse(
        request=request,
        name="nova_solicitacao.html",
        context={
            "user": user,
        },
    )


@app.post("/nova-solicitacao")
async def create_request(
    request: Request,
    sector: str = Form(...),
    equipment: str = Form(...),
    description: str = Form(...),
    priority: str = Form(...),
    files: list[UploadFile] = File(
        default=[]
    ),
    db: Session = Depends(get_db),
):
    user, redirect = require_login(
        request,
        db,
    )

    if redirect:
        return redirect

    require_role(
        user,
        ["lider", "adm"],
    )

    if priority not in {
        "Baixa",
        "Média",
        "Alta",
        "Crítica",
    }:
        priority = "Média"

    req = MaintenanceRequest(
        sector=sector.strip(),
        equipment=equipment.strip(),
        description=description.strip(),
        priority=priority,
        requester_id=user.id,
    )

    db.add(req)
    db.commit()
    db.refresh(req)

    allowed = {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".mp4",
        ".mov",
        ".webm",
    }

    for upload in files:

        if not upload.filename:
            continue

        ext = Path(
            upload.filename
        ).suffix.lower()

        if ext not in allowed:
            continue

        content = await upload.read()

        if len(content) > 25 * 1024 * 1024:
            continue

        safe_name = (
            f"{req.id}_"
            f"{secrets.token_hex(8)}"
            f"{ext}"
        )

        (
            UPLOAD_DIR / safe_name
        ).write_bytes(content)

        db.add(
            Attachment(
                request_id=req.id,
                filename=safe_name,
                original_name=upload.filename,
            )
        )

    db.commit()

    add_history(
        db,
        req,
        user,
        "Solicitação aberta",
    )

    return RedirectResponse(
        f"/solicitacao/{req.id}",
        status_code=303,
    )


# =========================================================
# MINHAS SOLICITAÇÕES
# =========================================================

@app.get(
    "/minhas-solicitacoes",
    response_class=HTMLResponse,
)
def my_requests(
    request: Request,
    db: Session = Depends(get_db),
):
    user, redirect = require_login(
        request,
        db,
    )

    if redirect:
        return redirect

    require_role(
        user,
        ["lider"],
    )

    rows = (
        db.query(MaintenanceRequest)
        .filter(
            MaintenanceRequest.requester_id
            == user.id
        )
        .order_by(
            MaintenanceRequest.id.desc()
        )
        .all()
    )

    counts = {
        "pendente": sum(1 for r in rows if r.status == "PENDENTE"),
        "agendada": sum(1 for r in rows if r.status == "AGENDADA"),
        "atendimento": sum(1 for r in rows if r.status == "EM ATENDIMENTO"),
        "concluida": sum(1 for r in rows if r.status == "CONCLUÍDA"),
    }

    return templates.TemplateResponse(
        request=request,
        name="minhas_solicitacoes.html",
        context={
            "user": user,
            "rows": rows,
            "counts": counts,
        },
    )


# =========================================================
# PAINEL
# =========================================================

@app.get(
    "/painel",
    response_class=HTMLResponse,
)
def dashboard(
    request: Request,
    status: str = "",
    priority: str = "",
    db: Session = Depends(get_db),
):
    user, redirect = require_login(
        request,
        db,
    )

    if redirect:
        return redirect

    require_role(
        user,
        ["manutencao", "adm"],
    )

    query = db.query(
        MaintenanceRequest
    )

    if status:
        query = query.filter(
            MaintenanceRequest.status == status
        )

    if priority:
        query = query.filter(
            MaintenanceRequest.priority == priority
        )

    rows = (
        query
        .order_by(
            MaintenanceRequest.id.desc()
        )
        .all()
    )

    counts = get_status_counts(db)

    return templates.TemplateResponse(
        request=request,
        name="painel.html",
        context={
            "user": user,
            "rows": rows,
            "counts": counts,
            "status": status,
            "priority": priority,
        },
    )


# =========================================================
# RELATÓRIOS
# =========================================================

@app.get(
    "/relatorios",
    response_class=HTMLResponse,
)
def relatorios(
    request: Request,
    db: Session = Depends(get_db),
):
    user, redirect = require_login(
        request,
        db,
    )

    if redirect:
        return redirect

    require_role(
        user,
        ["manutencao", "adm"],
    )

    concluded = (
        db.query(MaintenanceRequest)
        .filter(MaintenanceRequest.status == "CONCLUÍDA")
        .all()
    )

    # ---------------------------------------------------
    # Atendimentos por funcionário
    # ---------------------------------------------------

    employee_stats = {}

    for req in concluded:

        name = req.executor_name or "Não informado"

        if name not in employee_stats:
            employee_stats[name] = {
                "count": 0,
                "total_hours": 0.0,
            }

        employee_stats[name]["count"] += 1

        if req.started_at and req.finished_at:
            hours = (
                req.finished_at - req.started_at
            ).total_seconds() / 3600

            employee_stats[name]["total_hours"] += hours

    employee_labels = sorted(
        employee_stats.keys(),
        key=lambda n: employee_stats[n]["count"],
        reverse=True,
    )

    employee_counts = [
        employee_stats[n]["count"] for n in employee_labels
    ]

    employee_avg_hours = [
        round(
            employee_stats[n]["total_hours"]
            / employee_stats[n]["count"],
            1,
        )
        if employee_stats[n]["count"]
        else 0
        for n in employee_labels
    ]

    # ---------------------------------------------------
    # Tempo médio por prioridade (abertura -> conclusão)
    # ---------------------------------------------------

    priority_order = ["Baixa", "Média", "Alta", "Crítica"]

    priority_stats = {
        p: {"count": 0, "total_hours": 0.0}
        for p in priority_order
    }

    for req in concluded:

        p = req.priority if req.priority in priority_stats else "Média"

        priority_stats[p]["count"] += 1

        if req.created_at and req.finished_at:
            hours = (
                req.finished_at - req.created_at
            ).total_seconds() / 3600

            priority_stats[p]["total_hours"] += hours

    priority_counts = [
        priority_stats[p]["count"] for p in priority_order
    ]

    priority_avg_hours = [
        round(
            priority_stats[p]["total_hours"]
            / priority_stats[p]["count"],
            1,
        )
        if priority_stats[p]["count"]
        else 0
        for p in priority_order
    ]

    counts = get_status_counts(db)

    return templates.TemplateResponse(
        request=request,
        name="relatorios.html",
        context={
            "user": user,
            "counts": counts,
            "total_concluded": len(concluded),
            "employee_labels": employee_labels,
            "employee_counts": employee_counts,
            "employee_avg_hours": employee_avg_hours,
            "priority_labels": priority_order,
            "priority_counts": priority_counts,
            "priority_avg_hours": priority_avg_hours,
        },
    )


# =========================================================
# DETALHE DA SOLICITAÇÃO
# =========================================================

@app.get(
    "/solicitacao/{request_id}",
    response_class=HTMLResponse,
)
def request_detail(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db),
):
    user = current_user(
        request,
        db,
    )

    if not user:
        return RedirectResponse(
            "/login",
            status_code=303,
        )

    req = db.get(
        MaintenanceRequest,
        request_id,
    )

    if not req:
        raise HTTPException(
            status_code=404,
            detail="Solicitação não encontrada",
        )

    if (
        user.role == "lider"
        and req.requester_id != user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="Acesso não autorizado",
        )

    return templates.TemplateResponse(
        request=request,
        name="detalhe.html",
        context={
            "user": user,
            "item": req,
            "maintenance_employees": MAINTENANCE_EMPLOYEES,
            "now_datetime": datetime.now().strftime(
                "%Y-%m-%dT%H:%M"
            ),
        },
    )


# =========================================================
# AGENDAR ATENDIMENTO
# =========================================================

@app.post(
    "/solicitacao/{request_id}/agendar"
)
def schedule_request(
    request: Request,
    request_id: int,
    scheduled_employee: str = Form(...),
    planned_at: str = Form(...),
    scheduling_note: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = require_login(
        request,
        db,
    )

    if redirect:
        return redirect

    require_role(
        user,
        ["manutencao", "adm"],
    )

    req = db.get(
        MaintenanceRequest,
        request_id,
    )

    if not req:
        raise HTTPException(
            status_code=404,
            detail="Solicitação não encontrada",
        )

    if scheduled_employee not in MAINTENANCE_EMPLOYEES:
        raise HTTPException(
            status_code=400,
            detail="Funcionário inválido",
        )

    planned_datetime = parse_datetime(
        planned_at
    )

    if not planned_datetime:
        raise HTTPException(
            status_code=400,
            detail="Data e horário do agendamento inválidos",
        )

    req.scheduled_employee = scheduled_employee
    req.planned_at = planned_datetime
    req.scheduling_note = scheduling_note.strip()
    req.assigned_to_id = user.id
    req.status = "AGENDADA"

    db.commit()

    add_history(
        db,
        req,
        user,
        (
            f"Atendimento agendado para "
            f"{scheduled_employee} em "
            f"{planned_datetime.strftime('%d/%m/%Y %H:%M')}"
        ),
    )

    return RedirectResponse(
        f"/solicitacao/{request_id}",
        status_code=303,
    )


# =========================================================
# LEGADO - ASSUMIR SOLICITAÇÃO
# Mantido para não quebrar registros antigos.
# =========================================================

@app.post(
    "/solicitacao/{request_id}/assumir"
)
def take_request(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db),
):
    user, redirect = require_login(
        request,
        db,
    )

    if redirect:
        return redirect

    require_role(
        user,
        ["manutencao", "adm"],
    )

    req = db.get(
        MaintenanceRequest,
        request_id,
    )

    if not req:
        raise HTTPException(
            status_code=404,
            detail="Solicitação não encontrada",
        )

    req.assigned_to_id = user.id
    req.status = "EM ATENDIMENTO"

    if not req.started_at:
        req.started_at = datetime.now()

    db.commit()

    add_history(
        db,
        req,
        user,
        f"Atendimento assumido por {user.name}",
    )

    return RedirectResponse(
        f"/solicitacao/{request_id}",
        status_code=303,
    )


# =========================================================
# CONCLUIR SOLICITAÇÃO
# =========================================================

@app.post(
    "/solicitacao/{request_id}/concluir"
)
def finish_request(
    request: Request,
    request_id: int,
    executor_name: str = Form(...),
    started_at: str = Form(...),
    finished_at: str = Form(...),
    diagnosis: str = Form(""),
    cause: str = Form(""),
    service_done: str = Form(""),
    parts_used: str = Form(""),
    observations: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = require_login(
        request,
        db,
    )

    if redirect:
        return redirect

    require_role(
        user,
        ["manutencao", "adm"],
    )

    req = db.get(
        MaintenanceRequest,
        request_id,
    )

    if not req:
        raise HTTPException(
            status_code=404,
            detail="Solicitação não encontrada",
        )

    if executor_name not in MAINTENANCE_EMPLOYEES:
        raise HTTPException(
            status_code=400,
            detail="Funcionário executor inválido",
        )

    real_start = parse_datetime(
        started_at
    )

    real_finish = parse_datetime(
        finished_at
    )

    if not real_start or not real_finish:
        raise HTTPException(
            status_code=400,
            detail="Data ou horário da execução inválidos",
        )

    if real_finish < real_start:
        raise HTTPException(
            status_code=400,
            detail="O término não pode ser anterior ao início",
        )

    req.status = "CONCLUÍDA"

    req.started_at = real_start
    req.finished_at = real_finish

    req.executor_name = executor_name

    req.diagnosis = diagnosis.strip()
    req.cause = cause.strip()
    req.service_done = service_done.strip()
    req.parts_used = parts_used.strip()
    req.observations = observations.strip()

    if not req.assigned_to_id:
        req.assigned_to_id = user.id

    db.commit()

    add_history(
        db,
        req,
        user,
        (
            f"Solicitação concluída. "
            f"Execução realizada por {executor_name}"
        ),
    )

    return RedirectResponse(
        f"/solicitacao/{request_id}",
        status_code=303,
    )


# =========================================================
# ALTERAR PRIORIDADE
# =========================================================

@app.post(
    "/solicitacao/{request_id}/prioridade"
)
def change_priority(
    request: Request,
    request_id: int,
    priority: str = Form(...),
    db: Session = Depends(get_db),
):
    user, redirect = require_login(
        request,
        db,
    )

    if redirect:
        return redirect

    require_role(
        user,
        ["manutencao", "adm"],
    )

    req = db.get(
        MaintenanceRequest,
        request_id,
    )

    if not req:
        raise HTTPException(
            status_code=404,
            detail="Solicitação não encontrada",
        )

    if priority not in {
        "Baixa",
        "Média",
        "Alta",
        "Crítica",
    }:
        raise HTTPException(
            status_code=400,
            detail="Prioridade inválida",
        )

    old_priority = req.priority

    req.priority = priority

    db.commit()

    add_history(
        db,
        req,
        user,
        (
            f"Prioridade alterada de "
            f"{old_priority} para {priority}"
        ),
    )

    return RedirectResponse(
        f"/solicitacao/{request_id}",
        status_code=303,
    )


# =========================================================
# IMPRIMIR ORDEM DE SERVIÇO
# =========================================================

@app.get("/solicitacao/{request_id}/imprimir", response_class=HTMLResponse)
def imprimir_ordem(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db)
):
    user = current_user(request, db)

    if not user:
        return RedirectResponse("/login", status_code=303)

    if user.role != "adm":
        return RedirectResponse(
            f"/solicitacao/{request_id}",
            status_code=303
        )

    item = db.get(MaintenanceRequest, request_id)

    if not item:
        return RedirectResponse("/painel", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="ordem_servico.html",
        context={
            "user": user,
            "item": item,
        },
    )
