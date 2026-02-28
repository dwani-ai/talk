import os
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Generator, Optional

from passlib.context import CryptContext
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from auth_models import AuthSession, Base, User
from config import logger

DATABASE_URL = os.getenv("DWANI_DATABASE_URL", "sqlite:///./talk_auth.db").strip()
AUTH_SESSION_TTL_SECONDS = int(os.getenv("DWANI_AUTH_SESSION_TTL_SECONDS", os.getenv("DWANI_SESSION_TTL_SECONDS", "86400")))
AUTH_COOKIE_NAME = os.getenv("DWANI_AUTH_COOKIE_NAME", "dwani_auth_session").strip() or "dwani_auth_session"
AUTH_COOKIE_SECURE = os.getenv("DWANI_AUTH_COOKIE_SECURE", "0").strip() == "1"
AUTH_COOKIE_SAMESITE = (os.getenv("DWANI_AUTH_COOKIE_SAMESITE", "lax").strip().lower() or "lax")
AUTH_COOKIE_MAX_AGE = max(300, AUTH_SESSION_TTL_SECONDS)

_PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")

_engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

ENGINE = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=ENGINE, autocommit=False, autoflush=False, expire_on_commit=False)


def init_auth_db() -> None:
    Base.metadata.create_all(bind=ENGINE)


@contextmanager
def db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def hash_password(password: str) -> str:
    return _PWD_CONTEXT.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _PWD_CONTEXT.verify(password, password_hash)


def create_user(email: str, password: str) -> Optional[User]:
    with db_session() as db:
        user = User(email=normalize_email(email), password_hash=hash_password(password))
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            return None
        db.refresh(user)
        return user


def get_user_by_email(email: str) -> Optional[User]:
    with db_session() as db:
        stmt = select(User).where(User.email == normalize_email(email))
        return db.execute(stmt).scalar_one_or_none()


def authenticate_user(email: str, password: str) -> Optional[User]:
    user = get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_auth_session(user_id: int) -> AuthSession:
    session_id = secrets.token_urlsafe(48)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=AUTH_SESSION_TTL_SECONDS)
    with db_session() as db:
        auth_session = AuthSession(id=session_id, user_id=user_id, expires_at=expires)
        db.add(auth_session)
        db.flush()
        db.refresh(auth_session)
        return auth_session


def resolve_user_from_session(session_id: str) -> Optional[User]:
    token = (session_id or "").strip()
    if not token:
        return None
    with db_session() as db:
        stmt = select(AuthSession).where(AuthSession.id == token)
        auth_session = db.execute(stmt).scalar_one_or_none()
        if auth_session is None:
            return None
        if auth_session.revoked_at is not None or auth_session.is_expired:
            if auth_session.revoked_at is None:
                auth_session.revoked_at = datetime.now(timezone.utc)
            return None
        user = db.get(User, auth_session.user_id)
        return user


def revoke_session(session_id: str) -> None:
    token = (session_id or "").strip()
    if not token:
        return
    with db_session() as db:
        stmt = select(AuthSession).where(AuthSession.id == token)
        auth_session = db.execute(stmt).scalar_one_or_none()
        if auth_session is None or auth_session.revoked_at is not None:
            return
        auth_session.revoked_at = datetime.now(timezone.utc)


def cleanup_expired_sessions() -> int:
    now = datetime.now(timezone.utc)
    deleted = 0
    with db_session() as db:
        stmt = select(AuthSession).where(AuthSession.expires_at < now)
        sessions = db.execute(stmt).scalars().all()
        for session in sessions:
            db.delete(session)
            deleted += 1
    return deleted


def log_auth_db_config() -> None:
    logger.info("Auth DB initialized", extra={"database_url": DATABASE_URL.split('@')[-1]})
