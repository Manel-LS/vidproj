"""Authentication and account management (requirement 20)."""
from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, ConflictError, ValidationError
from app.core.security import (
    MAX_PASSWORD_BYTES,
    MIN_PASSWORD_LENGTH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.models import User

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def normalise_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _EMAIL_RE.match(email) or len(email) > 320:
        raise ValidationError("Please enter a valid email address.")
    return email


def validate_password(password: str) -> str:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValidationError(
            f"Your password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValidationError("That password is too long. Please use 72 bytes or fewer.")
    return password


def get_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(func.lower(User.email) == email.lower()))


def register(session: Session, *, email: str, password: str, full_name: str = "") -> User:
    email = normalise_email(email)
    validate_password(password)

    if get_by_email(session, email) is not None:
        raise ConflictError("An account with that email already exists. Try signing in instead.")

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=(full_name or "").strip()[:120],
    )
    session.add(user)
    session.flush()
    return user


def authenticate(session: Session, *, email: str, password: str) -> User:
    user = get_by_email(session, (email or "").strip().lower())
    # Always run a hash comparison so a missing account and a wrong password take
    # the same amount of time.
    password_hash = user.password_hash if user else "$2b$12$" + "." * 53
    valid = verify_password(password or "", password_hash)

    if user is None or not valid:
        raise AuthenticationError("That email or password is incorrect.")
    if not user.is_active:
        raise AuthenticationError("This account has been disabled.")
    return user


def issue_token(user: User) -> str:
    return create_access_token(subject=user.id)
