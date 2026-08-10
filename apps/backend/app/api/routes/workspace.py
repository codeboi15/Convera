from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_workspace_context, require_admin
from app.core.db import get_session
from app.models.workspace import Workspace
from app.services.email.routing import inbound_address_for

router = APIRouter()


class WorkspaceOut(BaseModel):
    id: str
    name: str
    slug: str
    inbound_key: str
    # The address customers (or their forwarding rule) should send mail to.
    inbound_address: str
    support_email: Optional[EmailStr] = None
    custom_domain: Optional[str] = None
    custom_domain_verified: bool = False


class EmailSettingsUpdate(BaseModel):
    """The workspace's real support address, used as Reply-To on replies."""

    support_email: Optional[EmailStr] = Field(default=None)


def _to_out(ws: Workspace) -> WorkspaceOut:
    return WorkspaceOut(
        id=str(ws.id),
        name=ws.name,
        slug=ws.slug,
        inbound_key=ws.inbound_key,
        inbound_address=inbound_address_for(ws.inbound_key),
        support_email=ws.support_email,
        custom_domain=ws.custom_domain,
        custom_domain_verified=ws.custom_domain_verified,
    )


@router.get("", response_model=WorkspaceOut)
async def get_workspace(
    current: CurrentUser = Depends(get_workspace_context),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceOut:
    ws = await session.get(Workspace, current.workspace_id)
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    return _to_out(ws)


@router.patch("/email", response_model=WorkspaceOut)
async def update_email_settings(
    payload: EmailSettingsUpdate,
    current: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceOut:
    ws = await session.get(Workspace, current.workspace_id)
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    ws.support_email = payload.support_email
    await session.commit()
    await session.refresh(ws)
    return _to_out(ws)
