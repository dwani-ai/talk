from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from auth_store import (
    AUTH_COOKIE_MAX_AGE,
    AUTH_COOKIE_NAME,
    AUTH_COOKIE_SAMESITE,
    AUTH_COOKIE_SECURE,
    authenticate_user,
    create_auth_session,
    create_user,
    revoke_session,
)
from deps import get_optional_user
from models import LoginRequest, SignupRequest, UserResponse

router = APIRouter(prefix="/v1/auth", tags=["Auth"])


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=AUTH_COOKIE_MAX_AGE,
        samesite=AUTH_COOKIE_SAMESITE,
        secure=AUTH_COOKIE_SECURE,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        secure=AUTH_COOKIE_SECURE,
        samesite=AUTH_COOKIE_SAMESITE,
    )


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, response: Response) -> UserResponse:
    user = create_user(email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(status_code=409, detail="Email is already registered")
    auth_session = create_auth_session(user.id)
    _set_auth_cookie(response, auth_session.id)
    return UserResponse(id=user.id, email=user.email)


@router.post("/login", response_model=UserResponse)
async def login(payload: LoginRequest, response: Response) -> UserResponse:
    user = authenticate_user(email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    auth_session = create_auth_session(user.id)
    _set_auth_cookie(response, auth_session.id)
    return UserResponse(id=user.id, email=user.email)


@router.post("/logout")
async def logout(request: Request, response: Response) -> Dict[str, str]:
    session_id = request.cookies.get(AUTH_COOKIE_NAME, "")
    if session_id:
        revoke_session(session_id)
    _clear_auth_cookie(response)
    return {"status": "ok"}


@router.get("/me", response_model=Optional[UserResponse])
async def me(current_user=Depends(get_optional_user)) -> Optional[UserResponse]:
    if current_user is None:
        return None
    return UserResponse(id=current_user.id, email=current_user.email)
