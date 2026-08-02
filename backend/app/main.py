import base64
import json
import os
import math
import uuid
import asyncio
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
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
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434").rstrip("/")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:0.5b")
WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "").strip()
WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "").strip()

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


whisper_model = None


def get_whisper_model():
    global whisper_model
    if whisper_model is None:
        from faster_whisper import WhisperModel
        whisper_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return whisper_model


def transcribe_audio_file(path: str) -> str:
    model = get_whisper_model()
    segments, _ = model.transcribe(path, language="zh", vad_filter=True, beam_size=3)
    return "".join(segment.text for segment in segments).strip()


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


async def local_llm_chat(messages: list[dict]) -> dict:
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": LOCAL_LLM_MODEL,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1},
                },
            )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", "Local AI request failed")
            except (ValueError, AttributeError):
                detail = "Local AI request failed"
            raise HTTPException(status_code=502, detail=detail)
        return parse_json_content(response.json()["message"]["content"])
    except HTTPException:
        raise
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Local AI model is unavailable or returned an unexpected response") from exc


def normalize_conversation_analysis(result: dict) -> dict:
    summary = str(result.get("summary", "")).strip()[:100]
    interests = result.get("interests", [])
    evidence = result.get("evidence", [])
    try:
        score = max(0, min(100, int(result.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    return {
        "summary": summary,
        "interests": [str(item).strip() for item in interests if str(item).strip()][:8] if isinstance(interests, list) else [],
        "score": score,
        "next_action": str(result.get("next_action", "")).strip(),
        "evidence": [str(item).strip() for item in evidence if str(item).strip()][:5] if isinstance(evidence, list) else [],
    }


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
    event_name: Mapped[str] = mapped_column(String(120), default="2026 Shenzhen Electronics Expo")
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
    phone: Mapped[str] = mapped_column(String(80), default="")
    contact_email: Mapped[str] = mapped_column(String(255), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    gender: Mapped[str] = mapped_column(String(20), default="unspecified")
    photo_url: Mapped[str] = mapped_column(Text, default="")
    face_embedding: Mapped[str] = mapped_column(Text, default="")
    face_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    event_name: str = "2026 Shenzhen Electronics Expo"
    created_at: datetime


class ProfilePatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    event_name: str | None = Field(default=None, min_length=2, max_length=120)


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
    phone: str = Field(default="", max_length=80)
    contact_email: str = Field(default="", max_length=255)
    summary: str = Field(default="", max_length=5000)
    gender: str = Field(default="unspecified", pattern="^(male|female|unspecified)$")


class ContactPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    company: str | None = Field(default=None, min_length=1, max_length=160)
    role: str | None = Field(default=None, max_length=160)
    interests: list[str] | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    phone: str | None = Field(default=None, max_length=80)
    contact_email: str | None = Field(default=None, max_length=255)
    summary: str | None = Field(default=None, max_length=5000)
    gender: str | None = Field(default=None, pattern="^(male|female|unspecified)$")


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    company: str
    role: str
    interests: str
    score: int
    phone: str
    contact_email: str
    summary: str
    gender: str
    photo_url: str
    face_consent_at: datetime | None
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


class FaceProfileIn(BaseModel):
    embedding: list[float] = Field(min_length=64, max_length=2048)
    consent_confirmed: bool


class FaceMatchIn(BaseModel):
    embedding: list[float] = Field(min_length=64, max_length=2048)


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
    os.makedirs("/data/uploads", exist_ok=True)
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
app.mount("/media", StaticFiles(directory="/data/uploads", check_dir=False), name="media")
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


@app.patch("/auth/me", response_model=UserOut)
async def update_profile(data: ProfilePatch, user: CurrentUser, db: Db):
    if data.name is None and data.event_name is None:
        raise HTTPException(status_code=422, detail="No profile changes supplied")
    if data.name is not None:
        name = " ".join(data.name.split())
        if len(name) < 2:
            raise HTTPException(status_code=422, detail="Display name is too short")
        user.name = name
    if data.event_name is not None:
        event_name = " ".join(data.event_name.split())
        if len(event_name) < 2:
            raise HTTPException(status_code=422, detail="Exhibition name is too short")
        user.event_name = event_name
    await db.commit()
    await db.refresh(user)
    return user


@app.get("/contacts", response_model=list[ContactOut])
async def list_contacts(user: CurrentUser, db: Db):
    result = await db.scalars(select(Contact).where(Contact.owner_id == user.id).order_by(Contact.score.desc()))
    return list(result)


@app.post("/contacts", response_model=ContactOut, status_code=201)
async def create_contact(data: ContactIn, user: CurrentUser, db: Db):
    contact = Contact(owner_id=user.id, name=data.name, company=data.company, role=data.role, interests=",".join(data.interests), score=data.score, phone=data.phone, contact_email=data.contact_email, summary=data.summary, gender=data.gender)
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


@app.post("/contacts/{contact_id}/photo")
async def upload_contact_photo(contact_id: int, user: CurrentUser, db: Db, image: UploadFile = File(...)):
    contact = await db.scalar(select(Contact).where(Contact.id == contact_id, Contact.owner_id == user.id))
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG or WebP image")
    raw = await image.read(6 * 1024 * 1024)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image must be 5 MB or smaller")
    extension = {"image/jpeg":"jpg", "image/png":"png", "image/webp":"webp"}[image.content_type]
    filename = f"{user.id}/{contact.id}/{uuid.uuid4().hex}.{extension}"
    local_path = os.path.join("/data/uploads", filename)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    with open(local_path, "wb") as output:
        output.write(raw)
    contact.photo_url = f"/api/media/{filename}"
    await db.commit()
    return {"photo_url": contact.photo_url, "storage": "local"}


@app.post("/contacts/{contact_id}/face-profile")
async def save_face_profile(contact_id: int, data: FaceProfileIn, user: CurrentUser, db: Db):
    if not data.consent_confirmed:
        raise HTTPException(status_code=400, detail="Explicit face-profile consent is required")
    contact = await db.scalar(select(Contact).where(Contact.id == contact_id, Contact.owner_id == user.id))
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    norm = math.sqrt(sum(value * value for value in data.embedding))
    if norm <= 0:
        raise HTTPException(status_code=400, detail="Invalid face embedding")
    contact.face_embedding = json.dumps([value / norm for value in data.embedding])
    contact.face_consent_at = datetime.now(timezone.utc)
    await db.commit()
    return {"saved": True, "contact_id": contact.id, "consent_at": contact.face_consent_at}


@app.post("/faces/match")
async def match_face(data: FaceMatchIn, user: CurrentUser, db: Db):
    norm = math.sqrt(sum(value * value for value in data.embedding))
    if norm <= 0:
        raise HTTPException(status_code=400, detail="Invalid face embedding")
    candidate = [value / norm for value in data.embedding]
    rows = await db.scalars(select(Contact).where(Contact.owner_id == user.id, Contact.face_embedding != ""))
    best_contact, best_similarity = None, -1.0
    for contact in rows:
        stored = json.loads(contact.face_embedding)
        if len(stored) != len(candidate):
            continue
        similarity = sum(a * b for a, b in zip(candidate, stored))
        if similarity > best_similarity:
            best_contact, best_similarity = contact, similarity
    if not best_contact or best_similarity < 0.72:
        return {"matched": False, "similarity": max(best_similarity, 0)}
    return {"matched": True, "similarity": best_similarity, "contact": ContactOut.model_validate(best_contact)}


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
    return {
        "configured": True,
        "vision_model": QWEN_VISION_MODEL if QWEN_API_KEY else None,
        "speech_model": f"faster-whisper:{WHISPER_MODEL}",
        "analysis_model": f"ollama:{LOCAL_LLM_MODEL}",
    }


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
    prompt = "分析下面真实展会客户对话。仅返回JSON，字段为：summary（中文总结，严格不超过100个汉字或字符）、interests（明确提及的兴趣数组）、score（仅依据购买信号的0-100整数）、next_action（建议下一步）、evidence（原对话中的简短原句数组）。不得补充对话中没有的事实。\n真实转写：\n" + data.transcript
    result = await local_llm_chat([{"role": "system", "content": "你是严谨的展会CRM分析助手。仅从真实转写提取信息，不得编造，并输出合法JSON。"}, {"role": "user", "content": prompt}])
    return {"source": "local-qwen2.5", "model": LOCAL_LLM_MODEL, "result": normalize_conversation_analysis(result)}


@app.post("/ai/transcribe")
async def transcribe_audio(_: CurrentUser, audio: UploadFile = File(...)):
    allowed = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/wav": ".wav", "audio/mpeg": ".mp3", "audio/mp4": ".m4a"}
    content_type = (audio.content_type or "").split(";", 1)[0]
    if content_type not in allowed:
        raise HTTPException(status_code=415, detail="Record WebM, OGG, WAV, MP3 or M4A audio")
    raw = await audio.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio segment must be 10 MB or smaller")
    path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=allowed[content_type], delete=False) as temporary:
            temporary.write(raw)
            path = temporary.name
        transcript = await asyncio.to_thread(transcribe_audio_file, path)
        return {"source": "faster-whisper", "transcript": transcript}
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Local Whisper transcription failed") from exc
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
