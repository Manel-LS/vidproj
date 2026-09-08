from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import CurrentUser, SessionDep, auth_rate_limit
from app.core.config import settings
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user) -> TokenResponse:
    return TokenResponse(
        access_token=auth_service.issue_token(user),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    dependencies=[Depends(auth_rate_limit)],
)
def register(payload: RegisterRequest, session: SessionDep, request: Request) -> TokenResponse:
    user = auth_service.register(
        session,
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
    )
    session.commit()
    return _token_response(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in",
    dependencies=[Depends(auth_rate_limit)],
)
def login(payload: LoginRequest, session: SessionDep, request: Request) -> TokenResponse:
    user = auth_service.authenticate(session, email=str(payload.email), password=payload.password)
    return _token_response(user)


@router.get("/me", response_model=UserResponse, summary="The signed-in user")
def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
