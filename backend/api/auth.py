"""
Authentication API Router
Endpoints:
  POST /api/auth/register  – Create a new user account
  POST /api/auth/login     – Exchange credentials for a JWT
  GET  /api/auth/me        – Return the authenticated user's profile
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.models.user import User, Role
from backend.schemas.auth import Token, UserRegister, UserResponse, LoginRequest, RefreshTokenRequest
from backend.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from backend.core.deps import get_current_user
from backend.core.rate_limit import rate_limit_login

router = APIRouter()


# ──────────────────────────────────────────────
# POST /api/auth/register
# ──────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    """
    Create a new user account.
    Assigns the default 'viewer' role (id=3).
    """
    existing_email = db.query(User).filter(User.email == payload.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    existing_user = db.query(User).filter(User.username == payload.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this username already exists.",
        )

    viewer_role = db.query(Role).filter(Role.name == "viewer").first()
    role_id = viewer_role.id if viewer_role else 3

    new_user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        role_id=role_id,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return _build_user_response(new_user)


# ──────────────────────────────────────────────
# POST /api/auth/login
# ──────────────────────────────────────────────

@router.post(
    "/login",
    response_model=Token,
    summary="Authenticate and receive a JWT access token",
)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    _rate_limit: None = Depends(rate_limit_login),
):
    """
    Accept email **or** username + password.
    Returns a signed JWT access token and refresh token on success.
    Enforces rate limit of 5 attempts/minute per IP.
    """
    # Try email first, then username
    user = db.query(User).filter(User.email == payload.username).first()
    if user is None:
        user = db.query(User).filter(User.username == payload.username).first()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please check your email/username and password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Contact an administrator.",
        )

    role_name = user.role.name if user.role else "viewer"
    access_token = create_access_token(subject=user.email, role=role_name)
    refresh_token = create_refresh_token(subject=user.email)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
    }


# ──────────────────────────────────────────────
# POST /api/auth/refresh
# ──────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=Token,
    summary="Exchange a refresh token for a new access token",
)
def refresh_token_endpoint(
    payload: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    """
    Validates a long-lived refresh token and returns a fresh short-lived access token.
    """
    subject = decode_refresh_token(payload.refresh_token)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter((User.email == subject) | (User.username == subject)).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    role_name = user.role.name if user.role else "viewer"
    access_token = create_access_token(subject=user.email, role=role_name)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": payload.refresh_token,
    }


# ──────────────────────────────────────────────
# POST /api/auth/login (OAuth2 form — used by /api/docs Swagger UI)
# ──────────────────────────────────────────────

@router.post(
    "/login/oauth2",
    response_model=Token,
    include_in_schema=False,   # Hidden from public docs; only for Swagger UI
)
def login_oauth2(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """OAuth2 password-grant form used by the interactive /api/docs UI."""
    user = db.query(User).filter(User.email == form_data.username).first()
    if user is None:
        user = db.query(User).filter(User.username == form_data.username).first()

    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role_name = user.role.name if user.role else "viewer"
    access_token = create_access_token(subject=user.email, role=role_name)
    refresh_token = create_refresh_token(subject=user.email)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "refresh_token": refresh_token,
    }


# ──────────────────────────────────────────────
# GET /api/auth/me
# ──────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
def get_me(current_user: User = Depends(get_current_user)):
    """Protected route — requires a valid Bearer token."""
    return _build_user_response(current_user)


# ──────────────────────────────────────────────
# Internal helper
# ──────────────────────────────────────────────

def _build_user_response(user: User) -> dict:
    """Resolve the role name from the ORM relationship."""
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role.name if user.role else "viewer",
        "is_active": user.is_active,
    }
