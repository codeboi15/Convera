from __future__ import annotations

import logging

from arq import cron

from app.core.logging import configure_logging
from app.worker import jobs
from app.worker.queue import redis_settings

configure_logging()


async def startup(ctx: dict) -> None:
    """Log the effective configuration so a misconfigured deploy is obvious.

    Without this a worker running with the default ``stub`` email provider looks
    identical in the logs to one that is actually delivering mail.
    """
    from app.core.config import settings
    from app.services.email.base import get_outbound_provider, get_provider

    log = logging.getLogger(__name__)
    inbound = get_provider()
    outbound = get_outbound_provider()
    log.info(
        "worker ready | inbound=%s (polling=%s) outbound=%s | address=%s ai=%s",
        inbound.name,
        inbound.supports_polling,
        outbound.name,
        settings.email_inbound_address or "(unset)",
        "configured" if settings.anthropic_api_key else "MISSING",
    )
    if outbound.name == "stub":
        log.warning(
            "Outbound email is 'stub' — replies will be logged, not sent. Set "
            "EMAIL_OUTBOUND_PROVIDER (e.g. mailjet) on this service."
        )
    if not inbound.supports_polling:
        log.warning(
            "Inbound provider %r does not poll — incoming email will not be "
            "fetched by this worker.",
            inbound.name,
        )


class WorkerSettings:
    """arq worker configuration.

    Run with either:
        arq app.worker.main.WorkerSettings
        python -m app.worker.main
    """

    functions = [jobs.generate_summary, jobs.send_email, jobs.poll_inbox]
    cron_jobs = [
        # Mailbox polling: every 15s so inbound feels near-realtime.
        cron(jobs.poll_inbox, second={0, 15, 30, 45}, run_at_startup=True),
        # Snooze expiry.
        cron(jobs.reopen_snoozed, minute=set(range(0, 60, 5))),
    ]
    redis_settings = redis_settings()
    on_startup = startup
    max_jobs = 20
    job_timeout = 120


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)  # type: ignore[arg-type]
