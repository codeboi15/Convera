from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Role


class InviteCreate(BaseModel):
    email: EmailStr
    role: Role = Role.agent


class InviteOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: Role
    accepted: bool
    expires_at: datetime
    created_at: datetime
    # Returned only right after creation so the UI can show/copy the link.
    invite_url: Optional[str] = None


class AcceptInviteRequest(BaseModel):
    token: str
    # Required only when the invited email does not yet have an account.
    name: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    name: Optional[str] = None
    role: Role
    joined_at: datetime


class UpdateMemberRole(BaseModel):
    role: Role
