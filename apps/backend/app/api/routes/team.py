from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_workspace_context, require_admin
from app.core.config import settings
from app.core.db import get_session
from app.core.ratelimit import RateLimit
from app.models.enums import Role
from app.models.workspace import Invite, WorkspaceMember
from app.schemas.auth import AuthResponse, UserOut
from app.schemas.team import (
    AcceptInviteRequest,
    InviteCreate,
    InviteOut,
    MemberOut,
    UpdateMemberRole,
)
from app.services import auth as auth_service
from app.services import team as team_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Invite tokens are single-use secrets; cap guessing attempts from one address.
accept_limit = RateLimit("team:invite_accept", limit=10, window_seconds=3600)


def _invite_url(token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/invite/{token}"


@router.get("/members", response_model=List[MemberOut])
async def list_members(
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> List[MemberOut]:
    return await team_service.list_members(session, current.workspace_id)


@router.post(
    "/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED
)
async def create_invite(
    payload: InviteCreate,
    current: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> InviteOut:
    existing_user = await auth_service.get_user_by_email(session, payload.email)
    if existing_user is not None:
        membership = await auth_service.get_membership(
            session, existing_user.id, current.workspace_id
        )
        if membership is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This person is already a member of the workspace",
            )

    invite = await team_service.create_invite(
        session,
        workspace_id=current.workspace_id,
        email=payload.email,
        role=payload.role,
        invited_by_id=current.user.id,
    )
    await session.commit()

    # Delivery is queued once the email channel lands; the URL is returned so an
    # admin can always share the link manually.
    logger.info("invite created for %s in workspace %s", invite.email, invite.workspace_id)

    return InviteOut(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        accepted=False,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
        invite_url=_invite_url(invite.token),
    )


@router.get("/invites", response_model=List[InviteOut])
async def list_invites(
    current: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> List[InviteOut]:
    invites = (
        await session.scalars(
            select(Invite)
            .where(Invite.workspace_id == current.workspace_id)
            .order_by(Invite.created_at.desc())
        )
    ).all()
    return [
        InviteOut(
            id=i.id,
            email=i.email,
            role=i.role,
            accepted=i.accepted_at is not None,
            expires_at=i.expires_at,
            created_at=i.created_at,
        )
        for i in invites
    ]


@router.delete(
    "/invites/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def revoke_invite(
    invite_id: uuid.UUID,
    current: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    invite = await session.scalar(
        select(Invite).where(
            Invite.id == invite_id, Invite.workspace_id == current.workspace_id
        )
    )
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found"
        )
    await session.delete(invite)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/invites/accept",
    response_model=AuthResponse,
    dependencies=[Depends(accept_limit)],
)
async def accept_invite(
    payload: AcceptInviteRequest, session: AsyncSession = Depends(get_session)
) -> AuthResponse:
    invite = await team_service.get_valid_invite(session, payload.token)
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invite is invalid, expired, or already used",
        )

    user = await auth_service.get_user_by_email(session, invite.email)
    if user is None:
        if not payload.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A password is required to create your account",
            )
        user = await auth_service.create_user(
            session,
            email=invite.email,
            password=payload.password,
            name=payload.name,
        )

    membership = await auth_service.get_membership(
        session, user.id, invite.workspace_id
    )
    if membership is None:
        membership = WorkspaceMember(
            workspace_id=invite.workspace_id, user_id=user.id, role=invite.role
        )
        session.add(membership)

    invite.accepted_at = datetime.now(timezone.utc)
    await session.commit()

    memberships = await auth_service.list_memberships(session, user.id)
    access, refresh = auth_service.issue_tokens(
        user, invite.workspace_id, membership.role
    )
    return AuthResponse(
        access_token=access,
        refresh_token=refresh,
        user=UserOut.model_validate(user),
        active_workspace_id=invite.workspace_id,
        workspaces=memberships,
    )


@router.patch("/members/{user_id}", response_model=MemberOut)
async def update_member_role(
    user_id: uuid.UUID,
    payload: UpdateMemberRole,
    current: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MemberOut:
    membership = await auth_service.get_membership(
        session, user_id, current.workspace_id
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )

    # Never allow the workspace to lose its last admin.
    if membership.role == Role.admin and payload.role != Role.admin:
        if await team_service.count_admins(session, current.workspace_id) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The workspace must keep at least one admin",
            )

    membership.role = payload.role
    await session.commit()

    members = await team_service.list_members(session, current.workspace_id)
    return next(m for m in members if m.user_id == user_id)


@router.delete(
    "/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_member(
    user_id: uuid.UUID,
    current: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    membership = await auth_service.get_membership(
        session, user_id, current.workspace_id
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Member not found"
        )
    if (
        membership.role == Role.admin
        and await team_service.count_admins(session, current.workspace_id) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The workspace must keep at least one admin",
        )

    await session.delete(membership)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
