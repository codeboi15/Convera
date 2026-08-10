from __future__ import annotations

from arq import cron

from app.core.logging import configure_logging
from app.worker import jobs
from app.worker.queue import redis_settings

configure_logging()


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
    max_jobs = 20
    job_timeout = 120


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)  # type: ignore[arg-type]
