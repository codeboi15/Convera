from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, require_admin
from app.core.db import get_session
from app.models.workspace import Workspace
from app.services.domains import providers, verification

router = APIRouter()


class DomainConnect(BaseModel):
    domain: str = Field(min_length=3, max_length=255)


class DomainStatus(BaseModel):
    domain: Optional[str] = None
    verified: bool = False
    verified_at: Optional[datetime] = None
    ssl_status: str = "none"
    provider: str = "manual"
    # Everything the admin needs to configure DNS.
    dns_txt_name: Optional[str] = None
    dns_txt_value: Optional[str] = None
    dns_cname_name: Optional[str] = None
    dns_cname_target: Optional[str] = None
    public_url: Optional[str] = None
    detail: Optional[str] = None
    auto_verified: bool = False


def _status(ws: Workspace, detail: Optional[str] = None) -> DomainStatus:
    provider = providers.get_domain_provider()
    domain = ws.custom_domain
    if not domain:
        return DomainStatus(provider=provider.name, detail=detail)
    reserved = verification.is_reserved_domain(domain)
    return DomainStatus(
        domain=domain,
        verified=ws.custom_domain_verified,
        verified_at=ws.custom_domain_verified_at,
        ssl_status=ws.custom_domain_ssl_status,
        provider=provider.name,
        dns_txt_name=None if reserved else verification.txt_record_name(domain),
        dns_txt_value=(
            None
            if reserved
            else verification.txt_record_value(ws.custom_domain_token or "")
        ),
        dns_cname_name=None if reserved else domain,
        dns_cname_target=None if reserved else provider.cname_target,
        public_url=(
            f"{'http' if reserved else 'https'}://{domain}"
            if ws.custom_domain_verified
            else None
        ),
        detail=detail,
        auto_verified=reserved,
    )


async def _workspace(session: AsyncSession, current: CurrentUser) -> Workspace:
    ws = await session.get(Workspace, current.workspace_id)
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )
    return ws


@router.get("", response_model=DomainStatus)
async def get_domain(
    current: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomainStatus:
    return _status(await _workspace(session, current))


@router.post("", response_model=DomainStatus, status_code=status.HTTP_201_CREATED)
async def connect_domain(
    payload: DomainConnect,
    current: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomainStatus:
    """Attach a custom domain and issue a verification token.

    The domain is stored unverified — nothing is served on it until ownership
    is proven, so a workspace cannot claim a hostname it does not control.
    """
    domain = verification.normalize_domain(payload.domain)
    reason = verification.rejection_reason(domain)
    if reason:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)

    taken = await session.scalar(
        select(Workspace).where(
            Workspace.custom_domain == domain, Workspace.id != current.workspace_id
        )
    )
    if taken is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That domain is already connected to another workspace.",
        )

    ws = await _workspace(session, current)
    ws.custom_domain = domain
    ws.custom_domain_token = verification.new_token()
    ws.custom_domain_verified = False
    ws.custom_domain_verified_at = None
    ws.custom_domain_ssl_status = "none"
    await session.commit()
    await session.refresh(ws)

    # Reserved names (.test/.localhost) can never be publicly registered, so
    # there is nothing to prove — verify immediately to keep local demos usable.
    if verification.is_reserved_domain(domain):
        return await _verify(session, ws)

    return _status(ws, detail="Add the DNS records below, then verify.")


async def _verify(session: AsyncSession, ws: Workspace) -> DomainStatus:
    ok, detail = await verification.verify_dns_token(
        ws.custom_domain or "", ws.custom_domain_token or ""
    )
    if not ok:
        ws.custom_domain_verified = False
        await session.commit()
        await session.refresh(ws)
        return _status(ws, detail=detail)

    ws.custom_domain_verified = True
    ws.custom_domain_verified_at = datetime.now(timezone.utc)

    result = await providers.get_domain_provider().provision(ws.custom_domain or "")
    ws.custom_domain_ssl_status = result.status
    await session.commit()
    await session.refresh(ws)
    return _status(ws, detail=f"{detail} {result.detail}".strip())


@router.post("/verify", response_model=DomainStatus)
async def verify_domain(
    current: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomainStatus:
    """Check the DNS TXT record and, on success, request a certificate."""
    ws = await _workspace(session, current)
    if not ws.custom_domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No domain connected."
        )
    return await _verify(session, ws)


@router.post("/refresh-ssl", response_model=DomainStatus)
async def refresh_ssl(
    current: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomainStatus:
    """Re-check certificate status with the configured provider."""
    ws = await _workspace(session, current)
    if not ws.custom_domain or not ws.custom_domain_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verify the domain first.",
        )
    result = await providers.get_domain_provider().status(ws.custom_domain)
    ws.custom_domain_ssl_status = result.status
    await session.commit()
    await session.refresh(ws)
    return _status(ws, detail=result.detail)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def disconnect_domain(
    current: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    ws = await _workspace(session, current)
    if ws.custom_domain:
        await providers.get_domain_provider().remove(ws.custom_domain)
    ws.custom_domain = None
    ws.custom_domain_token = None
    ws.custom_domain_verified = False
    ws.custom_domain_verified_at = None
    ws.custom_domain_ssl_status = "none"
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Public: TLS authorization hook ──────────────────────────────────────

public_router = APIRouter()


@public_router.get("/authorize")
async def authorize_domain(
    domain: str = Query(min_length=3, max_length=255),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Answer whether a hostname may receive a certificate.

    This is the vendor-neutral hook: Caddy's on-demand TLS calls it before
    obtaining a Let's Encrypt certificate, so custom domains work on any host
    without a platform-specific API. 200 = allowed, 404 = refused.
    """
    normalized = verification.normalize_domain(domain)
    ws = await session.scalar(
        select(Workspace).where(
            Workspace.custom_domain == normalized,
            Workspace.custom_domain_verified.is_(True),
        )
    )
    if ws is None:
        return Response(status_code=status.HTTP_404_NOT_FOUND)
    return Response(status_code=status.HTTP_200_OK)
