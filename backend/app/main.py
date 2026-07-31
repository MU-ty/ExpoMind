import base64
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pwdlib import PasswordHash
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://expomind:expomind_dev_password@database:5432/expomind")
JWT_SECRET = os.getenv("JWT_SECRET", "replace-this-secret-before-production")
TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "1440"))
ALGORITHM = "HS256"
QWEN_API_KEY = os.getenv("DASHSCOPE_API_KEY", "").strip()
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
QWEN_VISION_MODEL = os.getenv("QWEN_VISION_MODEL", "qwen-vl-max")
QWEN_TEXT_MODEL = os.getenv("QWEN_TEXT_MODEL", "qwen-plus")
WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "").strip()
WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "").strip()

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def require_qwen():
    if not QWEN_API_KEY:
        raise HTTPException(status_code=503, detail="Real AI is not configured. Set DASHSCOPE_API_KEY; no mock result will be returned.")


def parse_json_content(content: str) -> dict:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="AI provider returned invalid structured data") from exc


async def qwen_chat(model: str, messages: list[dict]) -> dict:
    require_qwen()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{QWEN_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "temperature": 0.1, "response_format": {"type": "json_object"}},
            )
        response.raise_for_status()
        return parse_json_content(response.json()["choices"][0]["message"]["content"])
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"AI provider rejected the request ({exc.response.status_code})") from exc
    except (httpx.HTTPError, KeyError, IndexError) as exc:
        raise HTTPException(status_code=502, detail="AI provider is unavailable or returned an unexpected response") from exc


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    wechat_openid: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    contacts: Mapped[list["Contact"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    company: Mapped[str] = mapped_column(String(160))
    role: Mapped[str] = mapped_column(String(160), default="")
    interests: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    owner: Mapped[User] = relationship(back_populates="contacts")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="contact", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    transcript: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    next_action: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    contact: Mapped[Contact] = relationship(back_populates="conversations")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class WechatLoginIn(BaseModel):
    code: str = Field(min_length=1, max_length=256)
    display_name: str = Field(default="WeChat User", min_length=1, max_length=80)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    role: str
    is_active: bool
    created_at: datetime


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    company: str = Field(min_length=1, max_length=160)
    role: str = Field(default="", max_length=160)
    interests: list[str] = Field(default_factory=list)
    score: int = Field(default=50, ge=0, le=100)


class ContactPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    company: str | None = Field(default=None, min_length=1, max_length=160)
    role: str | None = Field(default=None, max_length=160)
    interests: list[str] | None = None
    score: int | None = Field(default=None, ge=0, le=100)


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    company: str
    role: str
    interests: str
    score: int
    created_at: datetime


class AdminUserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    is_active: bool | None = None


class AdminUserOut(UserOut):
    contact_count: int = 0


class ConversationIn(BaseModel):
    contact_id: int | None = None
    contact_name: str = "Li Mingyuan"
    company: str = "DeepCloud AI"
    transcript: str = ""
    summary: str = "Interested in edge AI and domestic GPU servers."
    next_action: str = "Send the Nebula G8 benchmark within 7 days."
    score: int = Field(default=85, ge=0, le=100)


class TranscriptAnalyzeIn(BaseModel):
    transcript: str = Field(min_length=5, max_length=50000)


async def get_db():
    async with SessionLocal() as session:
        yield session


Db = Annotated[AsyncSession, Depends(get_db)]


def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expires}, JWT_SECRET, algorithm=ALGORITHM)


async def current_user(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], db: Db) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account has been disabled")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def admin_user(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


AdminUser = Annotated[User, Depends(admin_user)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user'"))
        await connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE"))
        await connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS wechat_openid VARCHAR(128)"))
        await connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_wechat_openid ON users(wechat_openid) WHERE wechat_openid IS NOT NULL"))
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    if admin_email and admin_password:
        async with SessionLocal() as session:
            admin = await session.scalar(select(User).where(User.email == admin_email))
            if not admin:
                admin = User(name=os.getenv("ADMIN_NAME", "ExpoMind Admin"), email=admin_email, password_hash=password_hash.hash(admin_password), role="admin", is_active=True)
                session.add(admin)
            else:
                admin.role = "admin"
                admin.is_active = True
            await session.commit()
    yield
    await engine.dispose()


app = FastAPI(title="ExpoMind API", version="0.3.0", lifespan=lifespan)
origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:8080").split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=AuthOut, status_code=201)
async def register(data: RegisterIn, db: Db):
    email = data.email.lower()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(name=data.name.strip(), email=email, password_hash=password_hash.hash(data.password))
    db.add(user)
    await db.flush()
    await db.commit()
    await db.refresh(user)
    return AuthOut(access_token=create_token(user.id), user=user)


@app.post("/auth/login", response_model=AuthOut)
async def login(data: LoginIn, db: Db):
    user = await db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not password_hash.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return AuthOut(access_token=create_token(user.id), user=user)


@app.get("/auth/wechat/status")
async def wechat_status():
    return {"configured": bool(WECHAT_APP_ID and WECHAT_APP_SECRET)}


@app.post("/auth/wechat", response_model=AuthOut)
async def wechat_login(data: WechatLoginIn, db: Db):
    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        raise HTTPException(status_code=503, detail="WeChat login is not configured")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get("https://api.weixin.qq.com/sns/jscode2session", params={"appid": WECHAT_APP_ID, "secret": WECHAT_APP_SECRET, "js_code": data.code, "grant_type": "authorization_code"})
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="WeChat login service is unavailable") from exc
    if payload.get("errcode") or not payload.get("openid"):
        raise HTTPException(status_code=401, detail=payload.get("errmsg", "Invalid WeChat login code"))
    openid = payload["openid"]
    user = await db.scalar(select(User).where(User.wechat_openid == openid))
    if not user:
        opaque_email = f"wx_{openid[:40]}@wechat.expomind.com"
        random_password = base64.urlsafe_b64encode(os.urandom(32)).decode()
        user = User(name=data.display_name.strip(), email=opaque_email, password_hash=password_hash.hash(random_password), wechat_openid=openid)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account has been disabled")
    return AuthOut(access_token=create_token(user.id), user=user)


@app.get("/auth/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user


@app.get("/contacts", response_model=list[ContactOut])
async def list_contacts(user: CurrentUser, db: Db):
    result = await db.scalars(select(Contact).where(Contact.owner_id == user.id).order_by(Contact.score.desc()))
    return list(result)


@app.post("/contacts", response_model=ContactOut, status_code=201)
async def create_contact(data: ContactIn, user: CurrentUser, db: Db):
    contact = Contact(owner_id=user.id, name=data.name, company=data.company, role=data.role, interests=",".join(data.interests), score=data.score)
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@app.patch("/contacts/{contact_id}", response_model=ContactOut)
async def update_contact(contact_id: int, data: ContactPatch, user: CurrentUser, db: Db):
    contact = await db.scalar(select(Contact).where(Contact.id == contact_id, Contact.owner_id == user.id))
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    updates = data.model_dump(exclude_unset=True)
    if "interests" in updates:
        updates["interests"] = ",".join(updates["interests"])
    for field, value in updates.items():
        setattr(contact, field, value)
    await db.commit()
    await db.refresh(contact)
    return contact


@app.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(contact_id: int, user: CurrentUser, db: Db):
    contact = await db.scalar(select(Contact).where(Contact.id == contact_id, Contact.owner_id == user.id))
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(contact)
    await db.commit()


@app.post("/conversations", status_code=201)
async def save_conversation(data: ConversationIn, user: CurrentUser, db: Db):
    contact = None
    if data.contact_id:
        contact = await db.scalar(select(Contact).where(Contact.id == data.contact_id, Contact.owner_id == user.id))
    if not contact:
        raise HTTPException(status_code=400, detail="Select a real contact before saving a conversation")
    conversation = Conversation(contact_id=contact.id, transcript=data.transcript, summary=data.summary, next_action=data.next_action)
    db.add(conversation)
    await db.commit()
    return {"id": conversation.id, "contact_id": contact.id, "saved": True}


@app.get("/conversations")
async def list_conversations(user: CurrentUser, db: Db):
    rows = await db.execute(select(Conversation, Contact.name, Contact.company).join(Contact).where(Contact.owner_id == user.id).order_by(Conversation.created_at.desc()))
    return [{"id": item.id, "contact_id": item.contact_id, "contact_name": name, "company": company, "transcript": item.transcript, "summary": item.summary, "next_action": item.next_action, "created_at": item.created_at} for item, name, company in rows.all()]


@app.get("/dashboard")
async def dashboard(user: CurrentUser, db: Db):
    total = await db.scalar(select(func.count(Contact.id)).where(Contact.owner_id == user.id))
    high_intent = await db.scalar(select(func.count(Contact.id)).where(Contact.owner_id == user.id, Contact.score >= 75))
    conversations = await db.scalar(select(func.count(Conversation.id)).join(Contact).where(Contact.owner_id == user.id))
    return {"contacts": total or 0, "high_intent": high_intent or 0, "conversations": conversations or 0}


@app.get("/admin/users", response_model=list[AdminUserOut])
async def admin_list_users(_: AdminUser, db: Db):
    rows = await db.execute(select(User, func.count(Contact.id)).outerjoin(Contact).group_by(User.id).order_by(User.created_at.desc()))
    return [AdminUserOut(id=user.id, name=user.name, email=user.email, role=user.role, is_active=user.is_active, created_at=user.created_at, contact_count=count) for user, count in rows.all()]


@app.patch("/admin/users/{user_id}", response_model=UserOut)
async def admin_update_user(user_id: int, data: AdminUserUpdate, admin: AdminUser, db: Db):
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id and data.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")
    if data.role is not None:
        target.role = data.role
    if data.is_active is not None:
        target.is_active = data.is_active
    db.add(AuditLog(actor_id=admin.id, action="user.update", target_type="user", target_id=target.id, detail=json.dumps(data.model_dump(exclude_unset=True))))
    await db.commit()
    await db.refresh(target)
    return target


@app.get("/admin/audit-logs")
async def admin_audit_logs(_: AdminUser, db: Db):
    rows = await db.execute(select(AuditLog, User.email).join(User, User.id == AuditLog.actor_id).order_by(AuditLog.created_at.desc()).limit(200))
    return [{"id": log.id, "actor": email, "action": log.action, "target_type": log.target_type, "target_id": log.target_id, "detail": log.detail, "created_at": log.created_at} for log, email in rows.all()]


@app.get("/ai/status")
async def ai_status(_: CurrentUser):
    return {"configured": bool(QWEN_API_KEY), "vision_model": QWEN_VISION_MODEL if QWEN_API_KEY else None, "text_model": QWEN_TEXT_MODEL if QWEN_API_KEY else None}


@app.post("/ai/business-card")
async def scan_business_card(user: CurrentUser, image: UploadFile = File(...)):
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG or WebP image")
    raw = await image.read(6 * 1024 * 1024)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be 5 MB or smaller")
    encoded = base64.b64encode(raw).decode("ascii")
    prompt = "Read this business card. Return JSON only with keys name, company, role, phone, email, interests. Use empty strings or an empty interests array when not visible. Never invent text."
    data = await qwen_chat(QWEN_VISION_MODEL, [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:{image.content_type};base64,{encoded}"}}, {"type": "text", "text": prompt}]}])
    return {"source": "qwen", "result": data}


@app.post("/ai/analyze-transcript")
async def analyze_transcript(data: TranscriptAnalyzeIn, _: CurrentUser):
    prompt = "Analyze this real exhibition conversation. Return JSON only with keys summary (string), interests (array of strings), score (integer 0-100 based only on stated buying signals), next_action (string), and evidence (array of exact short excerpts). Do not infer unsupported facts. Transcript:\n" + data.transcript
    result = await qwen_chat(QWEN_TEXT_MODEL, [{"role": "system", "content": "You extract auditable CRM facts from conversations. Never fabricate."}, {"role": "user", "content": prompt}])
    return {"source": "qwen", "result": result}
