from __future__ import annotations

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

    functions = [jobs.generate_summary, jobs.send_email]
    cron_jobs: list = []  # reopen_snoozed cron is registered in the inbox step
    redis_settings = redis_settings()


if __name__ == "__main__":
    from arq import run_worker

    run_worker(WorkerSettings)  # type: ignore[arg-type]
