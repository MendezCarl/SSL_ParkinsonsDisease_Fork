"""Authentication/authorization primitives shared by main.py and every router.

Extracted from main.py so route modules can depend on `get_current_user`
without a circular import (main.py includes those routers).
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.utils import get_authorization_scheme_param

from patient_manager import SessionLocal
from repo.sql_models import User

try:
    import jwt
    from jwt import InvalidTokenError
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test environments
    try:
        from jose import jwt
        from jose import JWTError as InvalidTokenError
    except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test environments
        jwt = None

        class InvalidTokenError(Exception):
            pass

try:
    from passlib.context import CryptContext
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test environments
    CryptContext = None

logger = logging.getLogger(__name__)

ALGO = "HS256"
ACCESS_MIN = 30
_FALLBACK_TOKEN_PREFIX = "dev-token:"

_env_secret = os.environ.get("JWT_SECRET_KEY")
if _env_secret:
    SECRET_KEY = _env_secret
else:
    if os.environ.get("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable must be set when ENVIRONMENT=production."
        )
    SECRET_KEY = secrets.token_urlsafe(32)
    logger.warning(
        "JWT_SECRET_KEY is not set; using a randomly generated development-only secret. "
        "Existing tokens will not survive a process restart. Set JWT_SECRET_KEY for stable tokens."
    )

if CryptContext is None:
    class _UnavailablePasswordContext:
        """Fails closed instead of silently accepting/storing plaintext passwords."""

        def hash(self, value: str) -> str:
            raise RuntimeError(
                "passlib is not installed; refusing to hash a password insecurely. "
                "Install passlib to enable authentication."
            )

        def verify(self, plain: str, hashed: str) -> bool:
            raise RuntimeError("passlib is not installed; cannot verify passwords.")

        def needs_update(self, hashed: str) -> bool:
            return False

    pwd = _UnavailablePasswordContext()
else:
    pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

_ANOMALY_WORKER_TOKEN = os.environ.get("ANOMALY_WORKER_TOKEN")


def _password_matches(plain: str, stored: str) -> bool:
    try:
        return pwd.verify(plain, stored)
    except Exception:
        logger.exception("Password verification failed; treating as no match")
        return False


def _should_rehash_password(stored: str) -> bool:
    if CryptContext is None:
        return False
    try:
        return pwd.needs_update(stored)
    except Exception:
        return True


def ensure_demo_user() -> None:
    """Provision the demo clinician account used for local/demo logins.

    Intentionally kept: this app is only deployed on the hospital's private
    network, and a known demo login is wanted for that environment.
    """
    demo_username = "doctor@hospital.com"
    demo_password = "Demo123!"
    try:
        with SessionLocal() as session:
            existing = session.query(User).filter(
                (User.username == demo_username) | (User.email == demo_username)
            ).first()
            if existing:
                if not _password_matches(demo_password, existing.hashed_password) or _should_rehash_password(existing.hashed_password):
                    existing.hashed_password = pwd.hash(demo_password)
                    session.commit()
                return

            session.add(
                User(
                    username=demo_username,
                    full_name="Demo Doctor",
                    email=demo_username,
                    hashed_password=pwd.hash(demo_password),
                    location="Demo Clinic",
                    title="Neurologist",
                    speciality="Movement Disorders",
                )
            )
            session.commit()
    except Exception:
        # Keep the app importable for docs/OpenAPI even when the optional
        # password-hashing backend is unavailable.
        logger.exception("Failed to provision demo user")


def authenticate(username: str, password: str) -> User | None:
    try:
        with SessionLocal() as session:
            user = session.query(User).filter(
                (User.username == username) | (User.email == username)
            ).first()
            if user and _password_matches(password, user.hashed_password):
                if _should_rehash_password(user.hashed_password):
                    user.hashed_password = pwd.hash(password)
                    session.commit()
                return user
    except Exception:
        logger.exception("Authentication lookup failed")
        return None
    return None


def create_access_token(sub: str) -> str:
    if jwt is None:
        return f"{_FALLBACK_TOKEN_PREFIX}{sub}"
    to_encode = {
        "sub": sub,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_MIN),
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGO)


def _username_from_token(token: str) -> str:
    if jwt is None:
        if not token.startswith(_FALLBACK_TOKEN_PREFIX):
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return token.removeprefix(_FALLBACK_TOKEN_PREFIX)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGO])
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    username = payload.get("sub")
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    return username


def get_user_by_token(token: str) -> User:
    username = _username_from_token(token)
    with SessionLocal() as session:
        user = session.query(User).filter_by(username=username).first()
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        session.expunge(user)
        return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    return get_user_by_token(token)


async def get_current_user_from_header_or_query(
    request: Request,
    token: str | None = Query(default=None),
) -> User:
    """Same auth check as get_current_user, but also accepts ?token=.

    Native <video>/<audio> elements and WebSocket clients can't attach a
    custom Authorization header, so media/streaming endpoints that must stay
    authenticated take the token as a query parameter instead.
    """
    header_token = None
    auth_header = request.headers.get("Authorization")
    if auth_header:
        scheme, param = get_authorization_scheme_param(auth_header)
        if scheme.lower() == "bearer" and param:
            header_token = param

    effective_token = header_token or token
    if not effective_token:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    return get_user_by_token(effective_token)


async def get_worker_auth(request: Request) -> None:
    """Shared-secret auth for the anomaly-detection worker's endpoints.

    Separate from get_current_user on purpose: the worker is a machine on the
    hospital's private network, not a logged-in clinician, so it shouldn't
    share the doctor JWT path.
    """
    if not _ANOMALY_WORKER_TOKEN:
        raise HTTPException(status_code=503, detail="Anomaly worker auth is not configured")

    auth_header = request.headers.get("Authorization") or ""
    scheme, param = get_authorization_scheme_param(auth_header)
    if scheme.lower() != "bearer" or not param or not secrets.compare_digest(param, _ANOMALY_WORKER_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid worker credentials")
