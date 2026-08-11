from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ProvisionResult:
    """Outcome of asking the platform to serve TLS for a domain."""

    status: str  # none | pending | active | error
    detail: str
    cname_target: Optional[str] = None


class DomainProvider(ABC):
    """Issues and serves TLS certificates for customer domains.

    Certificate issuance is the only genuinely platform-specific part of custom
    domains — verification and host routing are ours. Keeping it behind this
    interface means the feature is not tied to any one host.
    """

    name = "base"
    #: What the customer points their DNS at.
    cname_target: str = ""

    @abstractmethod
    async def provision(self, domain: str) -> ProvisionResult:
        """Register the domain so a certificate is issued for it."""

    async def status(self, domain: str) -> ProvisionResult:
        return ProvisionResult(status="pending", detail="Awaiting certificate.")

    async def remove(self, domain: str) -> None:
        return None


class ManualDomainProvider(DomainProvider):
    """Default: record the domain; certificates are handled by the operator.

    Used when no provider is configured. Verification and routing still work —
    only automatic certificate issuance is absent.
    """

    name = "manual"

    @property
    def cname_target(self) -> str:  # type: ignore[override]
        return settings.domain_cname_target or "your-app.example.com"

    async def provision(self, domain: str) -> ProvisionResult:
        logger.info("domain %s recorded; certificate handled externally", domain)
        return ProvisionResult(
            status="pending",
            detail=(
                "Domain verified. A certificate must be issued by your "
                "hosting platform for this hostname."
            ),
            cname_target=self.cname_target,
        )


class CaddyDomainProvider(DomainProvider):
    """Self-hosted TLS via Caddy's on-demand certificate issuance.

    Caddy asks our ``/api/public/domains/authorize`` endpoint whether a
    hostname is allowed, then obtains a Let's Encrypt certificate for it on the
    first request. Nothing to call here — approving the domain in our database
    *is* the provisioning step, which is what makes this vendor-independent.
    """

    name = "caddy"

    @property
    def cname_target(self) -> str:  # type: ignore[override]
        return settings.domain_cname_target or ""

    async def provision(self, domain: str) -> ProvisionResult:
        return ProvisionResult(
            status="active",
            detail=(
                "Authorized. Caddy will obtain a certificate on the first "
                "HTTPS request to this domain."
            ),
            cname_target=self.cname_target,
        )


class VercelDomainProvider(DomainProvider):
    """Adds the domain to a Vercel project; Vercel issues and renews the cert."""

    name = "vercel"
    API = "https://api.vercel.com"

    @property
    def cname_target(self) -> str:  # type: ignore[override]
        return settings.domain_cname_target or "cname.vercel-dns.com"

    def _params(self) -> dict:
        return {"teamId": settings.vercel_team_id} if settings.vercel_team_id else {}

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {settings.vercel_token}"}

    async def provision(self, domain: str) -> ProvisionResult:
        if not settings.vercel_token or not settings.vercel_project_id:
            return ProvisionResult(
                status="pending",
                detail="Vercel credentials not configured; certificate not requested.",
                cname_target=self.cname_target,
            )
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                res = await client.post(
                    f"{self.API}/v10/projects/{settings.vercel_project_id}/domains",
                    headers=self._headers(),
                    params=self._params(),
                    json={"name": domain},
                )
        except httpx.HTTPError as exc:
            logger.exception("Vercel domain provisioning failed for %s", domain)
            return ProvisionResult(status="error", detail=f"Provider error: {exc}")

        # 409 means the domain is already attached — that is success for us.
        if res.status_code in (200, 201, 409):
            return ProvisionResult(
                status="pending",
                detail="Domain registered. Certificate is being issued.",
                cname_target=self.cname_target,
            )
        logger.error("Vercel rejected domain %s: %s", domain, res.text[:300])
        return ProvisionResult(
            status="error", detail=f"Provider rejected the domain ({res.status_code})."
        )

    async def status(self, domain: str) -> ProvisionResult:
        if not settings.vercel_token or not settings.vercel_project_id:
            return ProvisionResult(status="pending", detail="Provider not configured.")
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                res = await client.get(
                    f"{self.API}/v9/projects/{settings.vercel_project_id}"
                    f"/domains/{domain}/config",
                    headers=self._headers(),
                    params=self._params(),
                )
            if res.status_code == 200 and not res.json().get("misconfigured", True):
                return ProvisionResult(status="active", detail="Certificate active.")
        except httpx.HTTPError:
            logger.debug("Vercel status check failed for %s", domain, exc_info=True)
        return ProvisionResult(
            status="pending", detail="DNS not pointing here yet, or certificate pending."
        )

    async def remove(self, domain: str) -> None:
        if not settings.vercel_token or not settings.vercel_project_id:
            return
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                await client.delete(
                    f"{self.API}/v9/projects/{settings.vercel_project_id}"
                    f"/domains/{domain}",
                    headers=self._headers(),
                    params=self._params(),
                )
        except httpx.HTTPError:
            logger.debug("Vercel domain removal failed for %s", domain, exc_info=True)


_provider: Optional[DomainProvider] = None


def get_domain_provider() -> DomainProvider:
    global _provider
    if _provider is not None:
        return _provider
    choice = (settings.domain_provider or "manual").lower()
    if choice == "vercel":
        _provider = VercelDomainProvider()
    elif choice == "caddy":
        _provider = CaddyDomainProvider()
    else:
        _provider = ManualDomainProvider()
    logger.info("domain provider: %s", _provider.name)
    return _provider


def reset_domain_provider() -> None:
    global _provider
    _provider = None
