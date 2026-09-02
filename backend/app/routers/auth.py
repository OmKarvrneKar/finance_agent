import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import Config
from app.database.db import get_db, User
from app.models.schemas import UserCreate, UserResponse, TokenResponse
from app.auth import (
    hash_password, verify_password, create_access_token, get_current_user,
    revoke_token, decode_access_token, JWT_SECRET_KEY, JWT_ALGORITHM,
    oauth2_scheme, JWT_EXPIRE_MINUTES,
)
from app.dependencies import auth_rate_limit, register_rate_limit
from app.database.db import RevokedToken

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(register_rate_limit)])
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    # Check for duplicate email
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists."
        )

    user = User(
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        full_name=user_in.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    logger.info(f"New user registered: {user.id}")
    return user


@router.post("/auth/login", response_model=TokenResponse,
             dependencies=[Depends(auth_rate_limit)])
def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": user.id})

    # Set HttpOnly cookie
    response.set_cookie(
        key=Config.COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=Config.COOKIE_SECURE,
        samesite=Config.COOKIE_SAMESITE,
        max_age=JWT_EXPIRE_MINUTES * 60,
        path="/",
    )

    logger.info(f"User logged in: {user.id}")
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/auth/logout", status_code=status.HTTP_200_OK)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    # Read token from Authorization header first (takes precedence), then cookie
    auth_header = request.headers.get("Authorization", "")
    bearer_token = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else None
    cookie_token = request.cookies.get(Config.COOKIE_NAME)
    jwt_token = bearer_token or cookie_token

    # Clear the cookie regardless
    response.delete_cookie(
        key=Config.COOKIE_NAME,
        path="/",
        httponly=True,
        secure=Config.COOKIE_SECURE,
        samesite=Config.COOKIE_SAMESITE,
    )

    if not jwt_token:
        return {"detail": "Successfully logged out"}

    try:
        payload = jwt.decode(jwt_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return {"detail": "Successfully logged out"}

    jti = payload.get("jti")
    sub = payload.get("sub")
    if jti and sub:
        try:
            user_id = int(sub)
        except (ValueError, TypeError):
            return {"detail": "Successfully logged out"}
        revoke_token(jti, user_id, db)

    return {"detail": "Successfully logged out"}
