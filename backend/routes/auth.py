"""
Authentication: registration, login (JWT bearer tokens), current user, password change.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.deps import LOGIN_ATTEMPTS_PER_MINUTE, get_current_user, login_rate_limiter
from backend.models import User
from backend.schemas import ChangePasswordRequest, LoginRequest, RegisterRequest, TokenResponse, UserOut
from backend.security import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)
router = APIRouter()


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.username),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    user_count = db.scalar(select(func.count(User.id)))
    if not settings.ALLOW_REGISTRATION and user_count:
        raise HTTPException(status_code=403, detail="Registration is disabled. Ask an administrator for an account.")
    email = payload.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.username) == payload.username.lower())):
        raise HTTPException(status_code=409, detail="That username is already taken")
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status_code=409, detail="An account with that email already exists")
    user = User(
        username=payload.username,
        email=email,
        hashed_password=hash_password(payload.password),
        is_admin=not user_count,  # the first account administers the instance
    )
    db.add(user)
    db.commit()
    logger.info("Registered user %s (admin=%s)", user.username, user.is_admin)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    identifier = payload.username.strip().lower()
    login_rate_limiter.check(identifier, LOGIN_ATTEMPTS_PER_MINUTE, "Too many login attempts")
    user = db.scalar(
        select(User).where(or_(func.lower(User.username) == identifier, func.lower(User.email) == identifier))
    )
    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        logger.info("Failed login for %s", identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
