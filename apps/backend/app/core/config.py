from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", case_sensitive=False
    )

    # App
    app_env: str = "development"
    debug: bool = True

    # Data — psycopg v3 serves both async (app) and sync (Alembic) from one URL.
    database_url: str = (
        "postgresql+psycopg://intercom:intercom@localhost:5432/intercom"
    )
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    # Frontend / CORS
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # Email — "imap" (mailbox polling), "postmark" (webhook), or "stub" (no-op).
    email_provider: str = "stub"
    # Outbound can use a different transport from inbound. Some hosts block
    # outbound SMTP entirely, in which case mail must leave over HTTPS while
    # inbound still arrives by IMAP. Blank means "same as email_provider".
    email_outbound_provider: str = ""
    # Mailbox that receives every workspace's mail; the plus-tag routes it.
    # e.g. support@example.com -> support+acme@example.com
    email_inbound_address: str = ""
    email_from_name: str = "Support"

    # IMAP/SMTP adapter
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""

    # Brevo adapter (HTTPS) — used where the host blocks outbound SMTP.
    brevo_api_key: str = ""
    brevo_from_email: str = ""

    # Resend adapter (HTTPS) — requires a verified sending domain.
    resend_api_key: str = ""
    resend_from_email: str = ""

    # Postmark adapter
    postmark_server_token: str = ""
    postmark_from_email: str = ""
    postmark_inbound_secret: str = ""

    # Custom domains — TLS issuance is the only platform-specific part, so it
    # sits behind a provider: "manual" (default), "caddy", or "vercel".
    domain_provider: str = "manual"
    # What customers point their CNAME at.
    domain_cname_target: str = ""
    vercel_token: str = ""
    vercel_project_id: str = ""
    vercel_team_id: str = ""

    # AI (Anthropic Claude)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    @field_validator("database_url")
    @classmethod
    def _normalize_db_url(cls, v: str) -> str:
        # Accept plain postgres URLs and pin the psycopg v3 driver used by the app.
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://") :]
        return v

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
