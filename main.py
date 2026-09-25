import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import quote

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
# DATA/HORA DO BRASIL
# =========================================================

BRASIL_TZ = ZoneInfo("America/Sao_Paulo")

def brasil_now():
    """Retorna a data/hora atual no fuso de São Paulo."""
    return datetime.now(BRASIL_TZ).replace(tzinfo=None)


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
        default=brasil_now,
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
        default=brasil_now,
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
    Adiciona colunas novas em bancos existentes
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
        "diagnosis": "TEXT",
        "cause": "TEXT",
        "service_done": "TEXT",
        "parts_used": "TEXT",
        "observations": "TEXT",
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


def redirect_with_error(
    request_id: int,
    message: str,
):
    return RedirectResponse(
        f"/solicitacao/{request_id}?error={quote(message)}",
        status_code=303,
    )


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
            .filter(
                MaintenanceRequest.status
                == status_value
            )
            .count()
        )

    return counts


# =========================================================
# USUÁRIOS INICIAIS
# =========================================================

def seed_admin():
    db = SessionLocal()

    try:
        # Cria somente os usuários que ainda não existem.
        # Assim, adicionar novos usuários não apaga nem recria os atuais.
        default_users = [
            {
                "name": "Administrador",
                "username": "admin",
                "password": "admin123",
                "role": "adm",
            },
            {
                "name": "Líder de Manutenção",
                "username": "manutencao",
                "password": "manutencao123",
                "role": "manutencao",
            },
            {
                "name": "Líder de Produção",
                "username": "lider",
                "password": "lider123",
                "role": "lider",
            },
            {
                "name": "Painel",
                "username": "painel",
                "password": "painel123",
                "role": "lider",
            },
            {
                "name": "Externo",
                "username": "externo",
                "password": "externo123",
                "role": "lider",
            },
        ]

        created = False

        for data in default_users:
            exists = (
                db.query(User)
                .filter(User.username == data["username"])
                .first()
            )

            if not exists:
                db.add(
                    User(
                        name=data["name"],
                        username=data["username"],
                        password_hash=pwd_context.hash(data["password"]),
                        role=data["role"],
                    )
                )
                created = True

        if created:
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
        "pendente": sum(
            1 for r in rows
            if r.status == "PENDENTE"
        ),
        "agendada": sum(
            1 for r in rows
            if r.status == "AGENDADA"
        ),
        "atendimento": sum(
            1 for r in rows
            if r.status == "EM ATENDIMENTO"
        ),
        "concluida": sum(
            1 for r in rows
            if r.status == "CONCLUÍDA"
        ),
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
            MaintenanceRequest.status
            == status
        )

    if priority:
        query = query.filter(
            MaintenanceRequest.priority
            == priority
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
    periodo: str = "mes",
    data_filtro: str = "",
    db: Session = Depends(get_db),
):
    user, redirect = require_login(
        request,
        db,
    )

    if redirect:
        return redirect

    # Relatórios são exclusivos do ADM
    require_role(
        user,
        ["adm"],
    )

    # -----------------------------------------------------
    # DEFINIÇÃO DO PERÍODO
    # -----------------------------------------------------

    inicio = None
    fim = None

    hoje = brasil_now()

    if periodo == "dia":

        if data_filtro:

            try:
                data_base = datetime.strptime(
                    data_filtro,
                    "%Y-%m-%d",
                )

            except ValueError:
                data_base = hoje

        else:
            data_base = hoje

        inicio = data_base.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        fim = inicio.replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=999999,
        )

    elif periodo == "ano":

        if data_filtro:

            try:
                ano = int(data_filtro)

            except ValueError:
                ano = hoje.year

        else:
            ano = hoje.year

        inicio = datetime(
            ano,
            1,
            1,
            0,
            0,
            0,
        )

        fim = datetime(
            ano + 1,
            1,
            1,
            0,
            0,
            0,
        )

    else:

        # Padrão: mês atual
        periodo = "mes"

        if data_filtro:

            try:
                data_base = datetime.strptime(
                    data_filtro,
                    "%Y-%m",
                )

            except ValueError:
                data_base = hoje

        else:
            data_base = hoje

        inicio = data_base.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        if inicio.month == 12:

            fim = datetime(
                inicio.year + 1,
                1,
                1,
                0,
                0,
                0,
            )

        else:

            fim = datetime(
                inicio.year,
                inicio.month + 1,
                1,
                0,
                0,
                0,
            )

    # -----------------------------------------------------
    # BUSCAR SERVIÇOS CONCLUÍDOS NO PERÍODO
    # -----------------------------------------------------

    concluded = (
        db.query(MaintenanceRequest)
        .filter(
            MaintenanceRequest.status
            == "CONCLUÍDA",

            MaintenanceRequest.finished_at
            >= inicio,

            MaintenanceRequest.finished_at
            < fim,
        )
        .order_by(
            MaintenanceRequest.finished_at.asc()
        )
        .all()
    )

    # -----------------------------------------------------
    # SERVIÇOS POR COLABORADOR
    # -----------------------------------------------------

    employee_stats = {}

    # Todos os colaboradores começam com zero
    for employee in MAINTENANCE_EMPLOYEES:

        employee_stats[employee] = {
            "count": 0,
            "total_hours": 0.0,
        }

    # Registros antigos sem executor
    employee_stats["Não informado"] = {
        "count": 0,
        "total_hours": 0.0,
    }

    for req in concluded:

        name = (
            req.executor_name
            or "Não informado"
        )

        if name not in employee_stats:

            employee_stats[name] = {
                "count": 0,
                "total_hours": 0.0,
            }

        employee_stats[name]["count"] += 1

        if (
            req.started_at
            and req.finished_at
        ):

            hours = (
                req.finished_at
                - req.started_at
            ).total_seconds() / 3600

            employee_stats[name][
                "total_hours"
            ] += hours

    # -----------------------------------------------------
    # ORDEM DOS COLABORADORES
    # -----------------------------------------------------

    employee_labels = list(
        MAINTENANCE_EMPLOYEES
    )

    # Só aparece se existir serviço sem executor
    if (
        employee_stats["Não informado"]["count"]
        > 0
    ):

        employee_labels.append(
            "Não informado"
        )

    employee_counts = [
        employee_stats[name]["count"]
        for name in employee_labels
    ]

    employee_avg_hours = []

    for name in employee_labels:

        count = employee_stats[name]["count"]

        if count > 0:

            avg = (
                employee_stats[name][
                    "total_hours"
                ]
                / count
            )

            employee_avg_hours.append(
                round(avg, 1)
            )

        else:

            employee_avg_hours.append(0)

    # -----------------------------------------------------
    # TOTAL DE SERVIÇOS
    # -----------------------------------------------------

    total_concluded = len(
        concluded
    )

    # -----------------------------------------------------
    # TEMPO MÉDIO POR PRIORIDADE
    # -----------------------------------------------------

    priority_order = [
        "Baixa",
        "Média",
        "Alta",
        "Crítica",
    ]

    priority_stats = {
        priority: {
            "count": 0,
            "total_hours": 0.0,
        }

        for priority in priority_order
    }

    for req in concluded:

        priority = req.priority

        if priority not in priority_stats:

            priority = "Média"

        priority_stats[priority][
            "count"
        ] += 1

        if (
            req.created_at
            and req.finished_at
        ):

            hours = (
                req.finished_at
                - req.created_at
            ).total_seconds() / 3600

            priority_stats[priority][
                "total_hours"
            ] += hours

    priority_counts = [
        priority_stats[p]["count"]
        for p in priority_order
    ]

    priority_avg_hours = []

    for priority in priority_order:

        count = priority_stats[priority][
            "count"
        ]

        if count > 0:

            avg = (
                priority_stats[priority][
                    "total_hours"
                ]
                / count
            )

            priority_avg_hours.append(
                round(avg, 1)
            )

        else:

            priority_avg_hours.append(0)

    # -----------------------------------------------------
    # CONTADORES GERAIS
    # -----------------------------------------------------

    counts = get_status_counts(db)

    # -----------------------------------------------------
    # TELA
    # -----------------------------------------------------

    return templates.TemplateResponse(
        request=request,
        name="relatorios.html",
        context={
            "user": user,
            "counts": counts,

            "periodo": periodo,
            "data_filtro": data_filtro,

            "inicio": inicio,
            "fim": fim,

            "total_concluded": total_concluded,

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
    error: str = "",
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
            "now_datetime": brasil_now().strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "error": error,
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

    if not scheduled_employee or not scheduled_employee.strip():

        return redirect_with_error(
            request_id,
            "É obrigatório selecionar o funcionário responsável pelo atendimento.",
        )

    if (
        scheduled_employee
        not in MAINTENANCE_EMPLOYEES
    ):

        return redirect_with_error(
            request_id,
            "Funcionário inválido.",
        )

    planned_datetime = parse_datetime(
        planned_at
    )

    if not planned_datetime:

        return redirect_with_error(
            request_id,
            "Data e horário do agendamento inválidos.",
        )

    # O agendamento precisa acontecer depois da abertura da O.S.
    # Não é permitido agendar no mesmo horário ou antes da solicitação.
    if req.created_at and planned_datetime <= req.created_at:

        return redirect_with_error(
            request_id,
            "O agendamento deve ser posterior à data e horário da solicitação.",
        )

    req.scheduled_employee = (
        scheduled_employee
    )

    req.planned_at = (
        planned_datetime
    )

    req.scheduling_note = (
        scheduling_note.strip()
    )

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

        req.started_at = brasil_now()

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

    if (
        executor_name
        not in MAINTENANCE_EMPLOYEES
    ):

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

    # A execução nunca pode começar antes da abertura da O.S.
    if req.created_at and real_start < req.created_at:

        raise HTTPException(
            status_code=400,
            detail="O início da execução não pode ser anterior à data e horário da solicitação.",
        )

    # O término também não pode ser anterior à abertura da O.S.
    if req.created_at and real_finish < req.created_at:

        raise HTTPException(
            status_code=400,
            detail="O término da execução não pode ser anterior à data e horário da solicitação.",
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
            f"Execução realizada por "
            f"{executor_name}"
        ),
    )

    return RedirectResponse(
        f"/solicitacao/{request_id}",
        status_code=303,
    )


# =========================================================
# IMPRIMIR AGENDAMENTO
# =========================================================

@app.get(
    "/solicitacao/{request_id}/imprimir-agendamento",
    response_class=HTMLResponse,
)
def imprimir_agendamento(
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

    # A impressão do agendamento é restrita à manutenção e ao ADM.
    if user.role not in ["adm", "manutencao"]:

        return RedirectResponse(
            f"/solicitacao/{request_id}",
            status_code=303,
        )

    item = db.get(
        MaintenanceRequest,
        request_id,
    )

    if not item:

        return RedirectResponse(
            "/painel",
            status_code=303,
        )

    if not item.scheduled_employee:

        raise HTTPException(
            status_code=400,
            detail="Esta solicitação ainda não possui funcionário agendado.",
        )

    return templates.TemplateResponse(
        request=request,
        name="imprimir_agendamento.html",
        context={
            "user": user,
            "item": item,
        },
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

@app.get(
    "/solicitacao/{request_id}/imprimir",
    response_class=HTMLResponse,
)
def imprimir_ordem(
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

    if user.role != "adm":

        return RedirectResponse(
            f"/solicitacao/{request_id}",
            status_code=303,
        )

    item = db.get(
        MaintenanceRequest,
        request_id,
    )

    if not item:

        return RedirectResponse(
            "/painel",
            status_code=303,
        )

    return templates.TemplateResponse(
        request=request,
        name="ordem_servico.html",
        context={
            "user": user,
            "item": item,
        },
    )
