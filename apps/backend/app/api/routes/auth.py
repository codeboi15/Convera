from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user
from app.core.db import get_session
from app.core.security import decode_token
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    SignupRequest,
    SwitchWorkspaceRequest,
    UserOut,
)
from app.services import auth as auth_service

router = APIRouter()


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    existing = await auth_service.get_user_by_email(session, payload.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = await auth_service.create_user(
        session, email=payload.email, password=payload.password, name=payload.name
    )
    workspace = await auth_service.create_workspace_with_owner(
        session, name=payload.workspace_name, owner=user
    )
    await session.commit()

    memberships = await auth_service.list_memberships(session, user.id)
    access, refresh = auth_service.issue_tokens(
        user, workspace.id, memberships[0].role if memberships else None
    )
    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(user),
        active_workspace_id=workspace.id,
        workspaces=memberships,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    user = await auth_service.authenticate(session, payload.email, payload.password)
    if user is None:
        # Same message for unknown email and bad password (no user enumeration).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    memberships = await auth_service.list_memberships(session, user.id)
    active = memberships[0] if memberships else None
    access, refresh = auth_service.issue_tokens(
        user, active.id if active else None, active.role if active else None
    )
    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(user),
        active_workspace_id=active.id if active else None,
        workspaces=memberships,
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_tokens(
    payload: RefreshRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    claims = decode_token(payload.refresh_token)
    if claims is None or claims.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    memberships = await auth_service.list_memberships(session, user.id)
    target = None
    if payload.workspace_id is not None:
        target = next(
            (m for m in memberships if m.id == payload.workspace_id), None
        )
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this workspace",
            )
    elif memberships:
        target = memberships[0]

    access, new_refresh = auth_service.issue_tokens(
        user, target.id if target else None, target.role if target else None
    )
    return AuthResponse(
        access_token=access,
        refresh_token=new_refresh,
        user=UserOut.model_validate(user),
        active_workspace_id=target.id if target else None,
        workspaces=memberships,
    )


@router.post("/switch-workspace", response_model=AuthResponse)
async def switch_workspace(
    payload: SwitchWorkspaceRequest,
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    membership = await auth_service.get_membership(
        session, current.user.id, payload.workspace_id
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this workspace",
        )

    memberships = await auth_service.list_memberships(session, current.user.id)
    access, refresh = auth_service.issue_tokens(
        current.user, membership.workspace_id, membership.role
    )
    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(current.user),
        active_workspace_id=membership.workspace_id,
        workspaces=memberships,
    )


@router.get("/me", response_model=MeResponse)
async def me(
    current: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    memberships = await auth_service.list_memberships(session, current.user.id)
    return MeResponse(
        user=UserOut.model_validate(current.user),
        active_workspace_id=current.workspace_id,
        active_role=current.role,
        workspaces=memberships,
    )
