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
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./manutencao.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
# requirements.txt instala psycopg v3 ("psycopg[binary]"), mas o SQLAlchemy só usa esse
# driver se o dialeto pedir "postgresql+psycopg://". Sem isso, ele tenta psycopg2 (não
# instalado) e a conexão falha em produção (ex.: Render/Railway, que fornecem postgres://).
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

app = FastAPI(title="Sistema de Manutenção")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", secrets.token_hex(32)),
    same_site="lax",
    https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False)  # lider, manutencao, adm
    active = Column(Integer, default=1)
    requests = relationship("MaintenanceRequest", back_populates="requester")


class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"
    id = Column(Integer, primary_key=True)
    sector = Column(String(150), nullable=False)
    equipment = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    priority = Column(String(20), nullable=False, default="Média")
    status = Column(String(30), nullable=False, default="PENDENTE")
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    diagnosis = Column(Text, nullable=True)
    cause = Column(Text, nullable=True)
    service_done = Column(Text, nullable=True)
    parts_used = Column(Text, nullable=True)
    observations = Column(Text, nullable=True)

    requester = relationship("User", foreign_keys=[requester_id], back_populates="requests")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    attachments = relationship("Attachment", back_populates="request", cascade="all, delete-orphan")
    history = relationship("History", back_populates="request", cascade="all, delete-orphan")


class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("maintenance_requests.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    request = relationship("MaintenanceRequest", back_populates="attachments")


class History(Base):
    __tablename__ = "history"
    id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("maintenance_requests.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    request = relationship("MaintenanceRequest", back_populates="history")
    user = relationship("User")


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_role(user, roles):
    if not user or user.role not in roles:
        raise HTTPException(status_code=403, detail="Acesso não autorizado")


def require_login(request: Request, db: Session):
    """Retorna o usuário logado, ou None + já devolve o redirect para /login.
    Sem isso, qualquer pessoa não autenticada que acessasse uma rota protegida
    via URL direta recebia um erro 403 cru em vez de ser mandada para o login."""
    user = current_user(request, db)
    if not user:
        return None, RedirectResponse("/login", status_code=303)
    return user, None


def add_history(db, req, user, action):
    db.add(History(request_id=req.id, user_id=user.id, action=action))
    db.commit()


def seed_admin():
    db = SessionLocal()
    try:
        if not db.query(User).first():
            db.add_all([
                User(name="Administrador", username="admin", password_hash=pwd_context.hash("admin123"), role="adm"),
                User(name="Manutenção", username="manutencao", password_hash=pwd_context.hash("manutencao123"), role="manutencao"),
                User(name="Líder de Produção", username="lider", password_hash=pwd_context.hash("lider123"), role="lider"),
            ])
            db.commit()
    finally:
        db.close()


seed_admin()


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role == "lider":
        return RedirectResponse("/minhas-solicitacoes", status_code=303)
    return RedirectResponse("/painel", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username, User.active == 1).first()
    if not user or not pwd_context.verify(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Usuário ou senha inválidos."})
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/nova-solicitacao", response_class=HTMLResponse)
def new_request_page(request: Request, db: Session = Depends(get_db)):
    user, redirect = require_login(request, db)
    if redirect:
        return redirect
    require_role(user, ["lider", "adm"])
    return templates.TemplateResponse("nova_solicitacao.html", {"request": request, "user": user})


@app.post("/nova-solicitacao")
async def create_request(
    request: Request,
    sector: str = Form(...),
    equipment: str = Form(...),
    description: str = Form(...),
    priority: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
):
    user, redirect = require_login(request, db)
    if redirect:
        return redirect
    require_role(user, ["lider", "adm"])

    priority = priority if priority in {"Baixa", "Média", "Alta", "Crítica"} else "Média"
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

    allowed = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"}
    for upload in files:
        if not upload.filename:
            continue
        ext = Path(upload.filename).suffix.lower()
        if ext not in allowed:
            continue
        content = await upload.read()
        if len(content) > 25 * 1024 * 1024:
            continue
        safe_name = f"{req.id}_{secrets.token_hex(8)}{ext}"
        (UPLOAD_DIR / safe_name).write_bytes(content)
        db.add(Attachment(request_id=req.id, filename=safe_name, original_name=upload.filename))
    db.commit()

    add_history(db, req, user, "Solicitação aberta")
    return RedirectResponse(f"/solicitacao/{req.id}", status_code=303)


@app.get("/minhas-solicitacoes", response_class=HTMLResponse)
def my_requests(request: Request, db: Session = Depends(get_db)):
    user, redirect = require_login(request, db)
    if redirect:
        return redirect
    require_role(user, ["lider"])
    rows = db.query(MaintenanceRequest).filter(MaintenanceRequest.requester_id == user.id).order_by(MaintenanceRequest.id.desc()).all()
    return templates.TemplateResponse("minhas_solicitacoes.html", {"request": request, "user": user, "rows": rows})


@app.get("/painel", response_class=HTMLResponse)
def dashboard(request: Request, status: str = "", priority: str = "", db: Session = Depends(get_db)):
    user, redirect = require_login(request, db)
    if redirect:
        return redirect
    require_role(user, ["manutencao", "adm"])

    query = db.query(MaintenanceRequest)
    if status:
        query = query.filter(MaintenanceRequest.status == status)
    if priority:
        query = query.filter(MaintenanceRequest.priority == priority)
    rows = query.order_by(MaintenanceRequest.id.desc()).all()

    counts = {
        "pendente": db.query(MaintenanceRequest).filter(MaintenanceRequest.status == "PENDENTE").count(),
        "atendimento": db.query(MaintenanceRequest).filter(MaintenanceRequest.status == "EM ATENDIMENTO").count(),
        "concluida": db.query(MaintenanceRequest).filter(MaintenanceRequest.status == "CONCLUÍDA").count(),
    }
    return templates.TemplateResponse(
        "painel.html",
        {"request": request, "user": user, "rows": rows, "counts": counts, "status": status, "priority": priority},
    )


@app.get("/solicitacao/{request_id}", response_class=HTMLResponse)
def request_detail(request: Request, request_id: int, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    req = db.get(MaintenanceRequest, request_id)
    if not req:
        raise HTTPException(404, "Solicitação não encontrada")

    if user.role == "lider" and req.requester_id != user.id:
        raise HTTPException(403, "Acesso não autorizado")

    return templates.TemplateResponse("detalhe.html", {"request": request, "user": user, "item": req})


@app.post("/solicitacao/{request_id}/assumir")
def take_request(request: Request, request_id: int, db: Session = Depends(get_db)):
    user, redirect = require_login(request, db)
    if redirect:
        return redirect
    require_role(user, ["manutencao", "adm"])
    req = db.get(MaintenanceRequest, request_id)
    if not req:
        raise HTTPException(404, "Solicitação não encontrada")

    req.assigned_to_id = user.id
    req.status = "EM ATENDIMENTO"
    req.started_at = req.started_at or datetime.now()
    db.commit()
    add_history(db, req, user, f"Atendimento assumido por {user.name}")
    return RedirectResponse(f"/solicitacao/{request_id}", status_code=303)


@app.post("/solicitacao/{request_id}/concluir")
def finish_request(
    request: Request,
    request_id: int,
    diagnosis: str = Form(""),
    cause: str = Form(""),
    service_done: str = Form(""),
    parts_used: str = Form(""),
    observations: str = Form(""),
    db: Session = Depends(get_db),
):
    user, redirect = require_login(request, db)
    if redirect:
        return redirect
    require_role(user, ["manutencao", "adm"])
    req = db.get(MaintenanceRequest, request_id)
    if not req:
        raise HTTPException(404, "Solicitação não encontrada")

    req.status = "CONCLUÍDA"
    req.finished_at = datetime.now()
    req.diagnosis = diagnosis.strip()
    req.cause = cause.strip()
    req.service_done = service_done.strip()
    req.parts_used = parts_used.strip()
    req.observations = observations.strip()
    req.assigned_to_id = req.assigned_to_id or user.id
    db.commit()
    add_history(db, req, user, "Solicitação concluída")
    return RedirectResponse(f"/solicitacao/{request_id}", status_code=303)


@app.post("/solicitacao/{request_id}/prioridade")
def change_priority(request: Request, request_id: int, priority: str = Form(...), db: Session = Depends(get_db)):
    user, redirect = require_login(request, db)
    if redirect:
        return redirect
    require_role(user, ["manutencao", "adm"])
    req = db.get(MaintenanceRequest, request_id)
    if not req:
        raise HTTPException(404, "Solicitação não encontrada")
    if priority not in {"Baixa", "Média", "Alta", "Crítica"}:
        raise HTTPException(400, "Prioridade inválida")
    old = req.priority
    req.priority = priority
    db.commit()
    add_history(db, req, user, f"Prioridade alterada de {old} para {priority}")
    return RedirectResponse(f"/solicitacao/{request_id}", status_code=303)
