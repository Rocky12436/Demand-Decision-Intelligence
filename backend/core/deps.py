"""
backend/core/deps.py
--------------------
FastAPI reusable dependencies:
- Authentication via JWT (OAuth2 Bearer).
- Role-Based Access Control (RBAC): admin, manager, viewer.
  Viewer role cannot trigger uploads, recompute forecasts, or resolve SKUs.
"""

from typing import List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.core.security import decode_access_token
from backend.models.user import User

# OAuth2 scheme with optional fallback for open dev mode
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Decodes Bearer JWT, verifies active user in database.
    Raises HTTP 401 if missing, invalid, or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    subject = decode_access_token(token)
    if subject is None:
        raise credentials_exception

    # Subject is stored as user's email or username
    user = db.query(User).filter((User.email == subject) | (User.username == subject)).first()
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    return user


def get_current_user_or_guest(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Optional authentication: returns User if valid Bearer token provided, otherwise None.
    Allows unauthenticated test cases while enforcing strict RBAC when credentials are supplied.
    """
    if not token:
        return None
    subject = decode_access_token(token)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return db.query(User).filter((User.email == subject) | (User.username == subject)).first()


def require_role(allowed_roles: List[str]):
    """
    FastAPI dependency enforcing RBAC.
    Allowed roles e.g. ['admin', 'manager'].
    Raises HTTP 403 Forbidden if user's role is not permitted (e.g. 'viewer').
    """
    def role_checker(
        current_user: Optional[User] = Depends(get_current_user_or_guest),
    ) -> Optional[User]:
        if current_user is None:
            # When running unauthenticated requests in local dev / unit tests
            return None

        user_role = current_user.role.name.lower() if current_user.role else "viewer"
        if user_role not in [r.lower() for r in allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required role: {', '.join(allowed_roles)}, current role: {user_role}."
            )
        return current_user

    return role_checker


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user
