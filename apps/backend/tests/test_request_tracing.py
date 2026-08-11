"""Request tracing: one id per unit of work, carried across process boundaries."""

import asyncio
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import (
    MAX_REQUEST_ID_LENGTH,
    REQUEST_ID_HEADER,
    RequestIdFilter,
    get_request_id,
    new_request_id,
    request_context,
)
from app.core.middleware import RequestIdMiddleware


class _CapturingHandler(logging.Handler):
    """Captures records *with the filter applied at emit time*.

    `caplog` alone is not enough here: the id is stamped on by a handler
    filter while the request context is still open, so inspecting records
    afterwards would read an already-restored context.
    """

    def __init__(self) -> None:
        super().__init__()
        self.records = []
        self.addFilter(RequestIdFilter())

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def captured_logs():
    handler = _CapturingHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    previous = root.level
    root.setLevel(logging.INFO)
    try:
        yield handler.records
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/echo")
    def echo() -> dict:
        # What a handler deep in the stack would see.
        return {"request_id": get_request_id()}

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# --------------------------------------------------------------------------
# HTTP boundary
# --------------------------------------------------------------------------


def test_generates_an_id_and_returns_it_to_the_caller(client):
    response = client.get("/echo")

    header = response.headers[REQUEST_ID_HEADER]
    assert header
    # The id the handler saw is the id the caller was told about — otherwise
    # a user reporting "request abc123 failed" points at nothing.
    assert response.json()["request_id"] == header


def test_honours_an_id_supplied_by_the_caller(client):
    """Lets a trace start at the client or an upstream proxy."""
    response = client.get("/echo", headers={REQUEST_ID_HEADER: "from-upstream"})

    assert response.headers[REQUEST_ID_HEADER] == "from-upstream"
    assert response.json()["request_id"] == "from-upstream"


def test_truncates_a_hostile_id(client):
    response = client.get("/echo", headers={REQUEST_ID_HEADER: "x" * 500})

    assert len(response.json()["request_id"]) == MAX_REQUEST_ID_LENGTH


def test_blank_supplied_id_falls_back_to_a_generated_one(client):
    response = client.get("/echo", headers={REQUEST_ID_HEADER: "   "})

    assert response.json()["request_id"].strip()


def test_id_is_present_on_a_failing_request(client, captured_logs):
    """A 500 is exactly when the trace matters most."""
    response = client.get("/boom", headers={REQUEST_ID_HEADER: "failing-req"})

    assert response.status_code == 500
    assert any(r.request_id == "failing-req" for r in captured_logs)


def test_access_log_carries_the_id(client, captured_logs):
    client.get("/echo", headers={REQUEST_ID_HEADER: "access-trace"})

    access = [r for r in captured_logs if r.name == "app.access"]
    assert access, "the request should have produced an access log line"
    assert all(r.request_id == "access-trace" for r in access)


def test_ids_do_not_leak_between_requests(client):
    first = client.get("/echo").json()["request_id"]
    second = client.get("/echo").json()["request_id"]

    assert first != second


# --------------------------------------------------------------------------
# Context isolation — the property the whole design rests on
# --------------------------------------------------------------------------


def test_concurrent_work_keeps_separate_ids():
    """Interleaved tasks must not see each other's id.

    This is what makes a `ContextVar` the right tool rather than a global: the
    API handles many requests concurrently in one process, and an id that
    bled across them would make every log line a lie.
    """

    async def worker(name: str, delay: float) -> tuple:
        with request_context(name):
            await asyncio.sleep(delay)  # yield, letting the others interleave
            seen_after_suspension = get_request_id()
        return name, seen_after_suspension

    async def run():
        return await asyncio.gather(
            worker("alpha", 0.03),
            worker("bravo", 0.01),
            worker("charlie", 0.02),
        )

    for name, seen in asyncio.new_event_loop().run_until_complete(run()):
        assert seen == name


def test_context_restores_the_previous_id_on_exit():
    with request_context("outer"):
        with request_context("inner"):
            assert get_request_id() == "inner"
        assert get_request_id() == "outer"


def test_context_restores_even_when_the_body_raises():
    with request_context("outer"):
        with pytest.raises(ValueError):
            with request_context("inner"):
                raise ValueError
        assert get_request_id() == "outer"


def test_generated_ids_are_unique():
    assert len({new_request_id() for _ in range(1000)}) == 1000


# --------------------------------------------------------------------------
# The filter — this is what correlates third-party log lines
# --------------------------------------------------------------------------


def test_filter_stamps_the_current_id_onto_any_record():
    record = logging.LogRecord("sqlalchemy.engine", logging.INFO, "", 0, "SELECT 1", None, None)

    with request_context("db-trace"):
        RequestIdFilter().filter(record)

    assert record.request_id == "db-trace"


def test_filter_never_drops_a_record():
    """A tracing filter that swallowed logs would be worse than no tracing."""
    record = logging.LogRecord("x", logging.INFO, "", 0, "msg", None, None)
    assert RequestIdFilter().filter(record) is True


def test_records_outside_any_request_are_still_loggable():
    record = logging.LogRecord("startup", logging.INFO, "", 0, "booting", None, None)
    RequestIdFilter().filter(record)
    assert record.request_id == "-"


# --------------------------------------------------------------------------
# Crossing the process boundary — API enqueues, worker picks up
# --------------------------------------------------------------------------


def test_enqueue_passes_the_current_id_to_the_job(monkeypatch):
    """Without this the trace dies at the queue and the worker is an island."""
    import uuid

    from app.services.email import dispatch

    enqueued = {}

    class FakeQueue:
        async def enqueue_job(self, name, *args, **kwargs):
            enqueued["name"] = name
            enqueued["args"] = args
            enqueued["kwargs"] = kwargs

        async def close(self):
            pass

    async def fake_get_queue():
        return FakeQueue()

    monkeypatch.setattr("app.worker.queue.get_queue", fake_get_queue)

    message_id = uuid.uuid4()

    async def run():
        with request_context("agent-click"):
            return await dispatch.enqueue_reply(message_id)

    assert asyncio.new_event_loop().run_until_complete(run()) is True
    assert enqueued["name"] == "send_email"
    assert enqueued["args"] == (str(message_id),)
    assert enqueued["kwargs"]["request_id"] == "agent-click"


def test_worker_job_adopts_the_id_it_was_given(monkeypatch):
    import uuid

    from app.worker import jobs

    seen = {}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def fake_send_reply(session, message_id):
        # Anything the job logs from here must carry the caller's id.
        seen["request_id"] = get_request_id()
        return True

    monkeypatch.setattr("app.core.db.async_session", lambda: FakeSession())
    monkeypatch.setattr("app.services.email.outbound.send_reply", fake_send_reply)

    async def run():
        # Outside any context, as a fresh worker process would be.
        await jobs.send_email({}, str(uuid.uuid4()), request_id="agent-click")

    asyncio.new_event_loop().run_until_complete(run())
    assert seen["request_id"] == "agent-click"


def test_worker_job_without_an_id_still_gets_one(monkeypatch):
    """A job enqueued by an older client must never log an empty trace."""
    import uuid

    from app.worker import jobs

    seen = {}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    async def fake_send_reply(session, message_id):
        seen["request_id"] = get_request_id()
        return True

    monkeypatch.setattr("app.core.db.async_session", lambda: FakeSession())
    monkeypatch.setattr("app.services.email.outbound.send_reply", fake_send_reply)

    async def run():
        await jobs.send_email({}, str(uuid.uuid4()))

    asyncio.new_event_loop().run_until_complete(run())
    assert seen["request_id"] not in ("", "-", None)
