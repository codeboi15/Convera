from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import Role


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: Optional[str] = Field(default=None, max_length=255)
    workspace_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str
    workspace_id: Optional[uuid.UUID] = None


class SwitchWorkspaceRequest(BaseModel):
    workspace_id: uuid.UUID


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    name: Optional[str] = None


class WorkspaceMembershipOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: Role


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut
    active_workspace_id: Optional[uuid.UUID] = None
    workspaces: List[WorkspaceMembershipOut] = []


class MeResponse(BaseModel):
    user: UserOut
    active_workspace_id: Optional[uuid.UUID] = None
    active_role: Optional[Role] = None
    workspaces: List[WorkspaceMembershipOut] = []
