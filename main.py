from pathlib import Path
import zipfile, textwrap, os

root = Path("/mnt/data/manutencao-fabrica")
(root / "templates").mkdir(parents=True, exist_ok=True)
(root / "static").mkdir(parents=True, exist_ok=True)
(root / "uploads").mkdir(parents=True, exist_ok=True)

files = {
"main.py": r'''import os
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
    user = current_user(request, db)
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
    user = current_user(request, db)
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
    user = current_user(request, db)
    require_role(user, ["lider"])
    rows = db.query(MaintenanceRequest).filter(MaintenanceRequest.requester_id == user.id).order_by(MaintenanceRequest.id.desc()).all()
    return templates.TemplateResponse("minhas_solicitacoes.html", {"request": request, "user": user, "rows": rows})


@app.get("/painel", response_class=HTMLResponse)
def dashboard(request: Request, status: str = "", priority: str = "", db: Session = Depends(get_db)):
    user = current_user(request, db)
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
    user = current_user(request, db)
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
    user = current_user(request, db)
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
    user = current_user(request, db)
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
''',

"requirements.txt": r'''fastapi==0.116.1
uvicorn[standard]==0.35.0
jinja2==3.1.6
python-multipart==0.0.20
itsdangerous==2.2.0
sqlalchemy==2.0.43
psycopg[binary]==3.2.9
passlib==1.7.4
''',

"templates/base.html": r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}Manutenção{% endblock %}</title>
<link rel="stylesheet" href="/static/style.css">
</head>
<body>
<header class="topbar">
  <div><strong>MANUTENÇÃO</strong><span class="sub"> | Fábrica de Ração</span></div>
  {% if user %}
  <div class="userbar">{{ user.name }} · <a href="/logout">Sair</a></div>
  {% endif %}
</header>
<main class="container">{% block content %}{% endblock %}</main>
</body>
</html>''',

"templates/login.html": r'''{% extends "base.html" %}{% block title %}Login{% endblock %}
{% block content %}
<div class="login-card">
<h1>Acesso ao sistema</h1>
<p class="muted">Solicitações e acompanhamento de manutenção</p>
{% if error %}<div class="alert">{{ error }}</div>{% endif %}
<form method="post" action="/login">
<label>Usuário<input name="username" required autofocus></label>
<label>Senha<input type="password" name="password" required></label>
<button class="btn primary">Entrar</button>
</form>
</div>
{% endblock %}''',

"templates/nova_solicitacao.html": r'''{% extends "base.html" %}{% block title %}Nova solicitação{% endblock %}
{% block content %}
<div class="page-head"><div><h1>Solicitar manutenção</h1><p class="muted">Informe o problema. A avaliação técnica será feita pela manutenção.</p></div></div>
<form class="card form" method="post" enctype="multipart/form-data">
<label>Setor
<input name="sector" placeholder="Digite o setor" required></label>
<label>Equipamento / Local
<input name="equipment" placeholder="Digite o equipamento ou local" required></label>
<label>Descreva o problema
<textarea name="description" rows="7" placeholder="Descreva o que está acontecendo..." required></textarea></label>
<label>Foto ou vídeo
<input type="file" name="files" multiple accept="image/*,video/*"></label>
<div>
<label>Prioridade</label>
<div class="priorities">
<label><input type="radio" name="priority" value="Baixa"> Baixa</label>
<label><input type="radio" name="priority" value="Média" checked> Média</label>
<label><input type="radio" name="priority" value="Alta"> Alta</label>
<label><input type="radio" name="priority" value="Crítica"> Crítica</label>
</div>
</div>
<button class="btn primary">Enviar solicitação</button>
</form>
{% endblock %}''',

"templates/minhas_solicitacoes.html": r'''{% extends "base.html" %}{% block title %}Minhas solicitações{% endblock %}
{% block content %}
<div class="page-head"><h1>Minhas solicitações</h1><a class="btn primary" href="/nova-solicitacao">+ Nova solicitação</a></div>
<div class="table-card"><table><thead><tr><th>Nº</th><th>Setor</th><th>Equipamento</th><th>Prioridade</th><th>Status</th><th>Data</th></tr></thead>
<tbody>{% for x in rows %}<tr onclick="location.href='/solicitacao/{{x.id}}'"><td>#{{ "%06d"|format(x.id) }}</td><td>{{x.sector}}</td><td>{{x.equipment}}</td><td><span class="priority p-{{x.priority|lower|replace('í','i')|replace('é','e')}}">● {{x.priority}}</span></td><td><span class="status">{{x.status}}</span></td><td>{{x.created_at.strftime("%d/%m/%Y %H:%M")}}</td></tr>{% else %}<tr><td colspan="6" class="empty">Nenhuma solicitação encontrada.</td></tr>{% endfor %}</tbody></table></div>
{% endblock %}''',

"templates/painel.html": r'''{% extends "base.html" %}{% block title %}Painel{% endblock %}
{% block content %}
<div class="page-head"><div><h1>Painel de manutenção</h1><p class="muted">Acompanhamento das solicitações</p></div></div>
<div class="cards">
<div class="metric"><span>Pendentes</span><strong>{{counts.pendente}}</strong></div>
<div class="metric"><span>Em atendimento</span><strong>{{counts.atendimento}}</strong></div>
<div class="metric"><span>Concluídas</span><strong>{{counts.concluida}}</strong></div>
</div>
<form class="filters" method="get">
<select name="status"><option value="">Todos os status</option><option {% if status=="PENDENTE" %}selected{% endif %}>PENDENTE</option><option {% if status=="EM ATENDIMENTO" %}selected{% endif %}>EM ATENDIMENTO</option><option {% if status=="CONCLUÍDA" %}selected{% endif %}>CONCLUÍDA</option></select>
<select name="priority"><option value="">Todas as prioridades</option><option>Baixa</option><option>Média</option><option>Alta</option><option>Crítica</option></select>
<button class="btn">Filtrar</button>
</form>
<div class="table-card"><table><thead><tr><th>Nº</th><th>Solicitante</th><th>Setor</th><th>Equipamento</th><th>Prioridade</th><th>Status</th><th>Data</th></tr></thead>
<tbody>{% for x in rows %}<tr onclick="location.href='/solicitacao/{{x.id}}'"><td>#{{ "%06d"|format(x.id) }}</td><td>{{x.requester.name}}</td><td>{{x.sector}}</td><td>{{x.equipment}}</td><td>{{x.priority}}</td><td>{{x.status}}</td><td>{{x.created_at.strftime("%d/%m/%Y %H:%M")}}</td></tr>{% else %}<tr><td colspan="7" class="empty">Nenhuma solicitação encontrada.</td></tr>{% endfor %}</tbody></table></div>
{% endblock %}''',

"templates/detalhe.html": r'''{% extends "base.html" %}{% block title %}Solicitação #{{"%06d"|format(item.id)}}{% endblock %}
{% block content %}
<div class="page-head"><div><h1>Solicitação #{{"%06d"|format(item.id)}}</h1><p class="muted">{{item.created_at.strftime("%d/%m/%Y %H:%M")}} · {{item.requester.name}}</p></div><span class="status big">{{item.status}}</span></div>
<div class="grid">
<section class="card">
<h2>Solicitação</h2>
<div class="info"><b>Setor</b><span>{{item.sector}}</span><b>Equipamento / Local</b><span>{{item.equipment}}</span><b>Prioridade</b><span>{{item.priority}}</span><b>Problema</b><p>{{item.description}}</p></div>
{% if item.attachments %}<h3>Anexos</h3><div class="attachments">{% for a in item.attachments %}<a href="/uploads/{{a.filename}}" target="_blank">{{a.original_name}}</a>{% endfor %}</div>{% endif %}
</section>
{% if user.role in ["manutencao","adm"] %}
<section class="card">
<h2>Atendimento</h2>
{% if item.status != "CONCLUÍDA" %}
<form method="post" action="/solicitacao/{{item.id}}/assumir"><button class="btn primary">Assumir / iniciar atendimento</button></form>
<hr>
<form method="post" action="/solicitacao/{{item.id}}/concluir">
<label>Diagnóstico<textarea name="diagnosis" rows="3"></textarea></label>
<label>Causa<textarea name="cause" rows="3"></textarea></label>
<label>Serviço realizado<textarea name="service_done" rows="4" required></textarea></label>
<label>Peças utilizadas<textarea name="parts_used" rows="3"></textarea></label>
<label>Observações<textarea name="observations" rows="3"></textarea></label>
<button class="btn success">Concluir solicitação</button>
</form>
<hr>
<form method="post" action="/solicitacao/{{item.id}}/prioridade">
<label>Alterar prioridade<select name="priority">{% for p in ["Baixa","Média","Alta","Crítica"] %}<option {% if item.priority==p %}selected{% endif %}>{{p}}</option>{% endfor %}</select></label>
<button class="btn">Salvar prioridade</button>
</form>
{% else %}
<div class="success-box">Serviço concluído em {{item.finished_at.strftime("%d/%m/%Y %H:%M")}}.</div>
{% endif %}
</section>
{% endif %}
</div>
{% endblock %}''',

"static/style.css": r'''*{box-sizing:border-box}body{margin:0;font-family:Inter,Arial,sans-serif;background:#f4f6f8;color:#17202a}.topbar{height:64px;background:#17202a;color:#fff;display:flex;align-items:center;justify-content:space-between;padding:0 28px}.topbar .sub{opacity:.7;font-weight:400}.topbar a{color:#fff;text-decoration:none}.container{max-width:1180px;margin:0 auto;padding:30px 18px}.page-head{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:22px}.page-head h1{margin:0 0 5px}.muted{color:#697586}.card,.table-card,.login-card{background:#fff;border:1px solid #e3e7eb;border-radius:14px;box-shadow:0 3px 12px rgba(0,0,0,.04)}.card{padding:24px}.login-card{max-width:420px;margin:70px auto;padding:30px}.form{max-width:760px}.form label,.card form label{display:block;font-weight:600;margin-bottom:17px}.form input,.form textarea,.card input,.card textarea,.card select,.filters select{display:block;width:100%;margin-top:7px;border:1px solid #cbd2d9;border-radius:9px;padding:12px;font:inherit;background:#fff}.btn{border:0;border-radius:9px;padding:11px 17px;background:#e8edf2;color:#17202a;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}.btn.primary{background:#1769e0;color:#fff}.btn.success{background:#16834b;color:#fff}.alert{background:#fde8e8;color:#a61b1b;padding:11px;border-radius:8px;margin:12px 0 18px}.priorities{display:flex;gap:16px;flex-wrap:wrap;margin:8px 0 20px}.priorities label{font-weight:500!important}.priorities input{width:auto;display:inline}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:15px;margin-bottom:20px}.metric{background:#fff;border:1px solid #e3e7eb;border-radius:14px;padding:20px}.metric span{color:#697586}.metric strong{display:block;font-size:32px;margin-top:8px}.filters{display:flex;gap:10px;margin-bottom:18px}.filters select{width:auto;min-width:190px;margin:0}.table-card{overflow:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:14px 13px;border-bottom:1px solid #edf0f2;white-space:nowrap}th{font-size:13px;color:#697586;background:#fafbfc}tbody tr{cursor:pointer}tbody tr:hover{background:#f8fafc}.empty{text-align:center;padding:35px;color:#697586}.status{display:inline-block;padding:6px 10px;border-radius:999px;background:#edf1f5;font-size:12px;font-weight:800}.status.big{font-size:14px}.priority{font-weight:700}.p-baixa{color:#16834b}.p-media{color:#a46a00}.p-alta{color:#c75a00}.p-critica{color:#b42318}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.info{display:grid;grid-template-columns:150px 1fr;gap:12px}.info p{grid-column:1/-1;background:#f7f8fa;padding:14px;border-radius:9px;white-space:pre-wrap}.attachments{display:flex;flex-wrap:wrap;gap:8px}.attachments a{padding:8px 10px;background:#edf3ff;border-radius:8px;text-decoration:none;color:#1769e0}.success-box{padding:14px;background:#e8f7ee;color:#146c3a;border-radius:9px}hr{border:0;border-top:1px solid #e5e7eb;margin:25px 0}@media(max-width:800px){.cards,.grid{grid-template-columns:1fr}.topbar{padding:0 15px}.container{padding:20px 12px}.page-head{align-items:flex-start;flex-direction:column}.filters{flex-direction:column}.filters select{width:100%}.info{grid-template-columns:1fr}th,td{padding:11px 9px}.sub{display:none}}'''
}

for rel, content in files.items():
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

(root / "README.md").write_text("""# Sistema de Manutenção — Fábrica de Ração

V1 de um sistema web para solicitações e acompanhamento de manutenção.

## Perfis
- Líder de Produção: abre e acompanha solicitações.
- Manutenção: recebe, assume, executa e conclui.
- Administrativo: acompanha o painel.

## Rodar localmente
```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload
