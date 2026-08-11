"""Rate limiting: wiring, enforcement, and failure behaviour.

Runs against ``fakeredis`` (real Redis semantics, no server) and a throwaway
app, so none of it touches the database or the network.

    pip install -r requirements-dev.txt && pytest
"""

import asyncio

import fakeredis.aioredis
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import ratelimit
from app.core.ratelimit import RateLimit
from app.main import app as real_app


@pytest.fixture
def redis():
    """Point the limiter at an in-memory Redis for the duration of a test."""
    ratelimit.reset_client()
    ratelimit._redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield ratelimit._redis
    ratelimit.reset_client()


@pytest.fixture
def client():
    probe = FastAPI()
    limiter = RateLimit("test:limited", limit=10, window_seconds=60)
    other = RateLimit("test:other", limit=10, window_seconds=60)

    @probe.get("/limited", dependencies=[Depends(limiter)])
    def limited() -> dict:
        return {"ok": True}

    @probe.get("/other", dependencies=[Depends(other)])
    def other_route() -> dict:
        return {"ok": True}

    with TestClient(probe) as c:
        yield c


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------

EXPECTED_LIMITS = {
    ("POST", "/api/auth/login"): ("auth:login", 10, 60),
    ("POST", "/api/auth/signup"): ("auth:signup", 5, 3600),
    ("POST", "/api/auth/refresh"): ("auth:refresh", 60, 60),
    ("POST", "/api/team/invites/accept"): ("team:invite_accept", 10, 3600),
    ("POST", "/api/widget/session"): ("widget:session", 20, 60),
    ("GET", "/api/widget/suggestions"): ("widget:suggest", 60, 60),
    ("GET", "/api/public/kb/{identifier}/search"): ("public_kb:search", 60, 60),
    ("POST", "/api/webhooks/postmark/inbound"): ("webhook:inbound", 300, 60),
}


def _wired_limits() -> dict:
    limits = {}
    for route in real_app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        for sub in dependant.dependencies:
            if isinstance(sub.call, RateLimit):
                key = (sorted(route.methods)[0], route.path)
                limits[key] = (sub.call.scope, sub.call.limit, sub.call.window)
    return limits


def test_every_public_endpoint_is_limited():
    assert _wired_limits() == EXPECTED_LIMITS


def test_limiter_injects_request_and_response_not_query_params():
    """Regression: ``RateLimit`` must keep real (non-string) annotations.

    FastAPI resolves string annotations against the callable's ``__globals__``,
    which a class *instance* does not have. Adding
    ``from __future__ import annotations`` to ``app.core.ratelimit`` therefore
    turns the injected ``Request``/``Response`` into required query parameters
    and every limited endpoint answers 422 — including login.
    """
    schema = real_app.openapi()["paths"]["/api/auth/login"]["post"]
    assert "parameters" not in schema, (
        "login gained query parameters — the limiter's Request/Response are "
        "being parsed as inputs"
    )


# --------------------------------------------------------------------------
# Enforcement
# --------------------------------------------------------------------------


def test_allows_up_to_the_limit_then_rejects(redis, client):
    codes = [client.get("/limited").status_code for _ in range(13)]
    assert codes[:10] == [200] * 10
    assert codes[10:] == [429] * 3


def test_rejection_tells_the_caller_when_to_retry(redis, client):
    for _ in range(11):
        response = client.get("/limited")

    assert response.status_code == 429
    assert "Too many requests" in response.json()["detail"]
    assert response.headers["Retry-After"].isdigit()
    assert response.headers["X-RateLimit-Limit"] == "10"
    assert response.headers["X-RateLimit-Remaining"] == "0"


def test_allowed_responses_report_remaining_budget(redis, client):
    assert client.get("/limited").headers["X-RateLimit-Remaining"] == "9"
    assert client.get("/limited").headers["X-RateLimit-Remaining"] == "8"


def test_budgets_are_independent_per_scope(redis, client):
    for _ in range(11):
        client.get("/limited")

    assert client.get("/other").status_code == 200


def test_budgets_are_independent_per_client_ip(redis, client):
    attacker = {"X-Forwarded-For": "1.2.3.4"}
    bystander = {"X-Forwarded-For": "9.9.9.9"}

    codes = [client.get("/limited", headers=attacker).status_code for _ in range(12)]
    assert codes[10:] == [429, 429]

    assert client.get("/limited", headers=bystander).status_code == 200


def test_window_expires_instead_of_sliding_forward(redis):
    """The TTL is set once; later hits must not push the reset further out."""

    async def probe():
        limiter = RateLimit("test:ttl", limit=3, window_seconds=60)
        await limiter.check("tester")
        key = (await redis.keys("ratelimit:test:ttl:*"))[0]
        first = await redis.ttl(key)
        await asyncio.sleep(1.1)
        await limiter.check("tester")
        return first, await redis.ttl(key)

    first, second = asyncio.new_event_loop().run_until_complete(probe())
    assert 0 < first <= 60
    assert second < first


# --------------------------------------------------------------------------
# Failure behaviour — a limiter must never be the reason the API is down
# --------------------------------------------------------------------------


def test_fails_open_when_redis_is_not_configured(client):
    ratelimit.reset_client()
    codes = [client.get("/limited").status_code for _ in range(15)]
    assert codes == [200] * 15


def test_fails_open_when_redis_errors_mid_request(client):
    class Broken:
        def pipeline(self):
            raise ConnectionError("redis down")

    ratelimit._redis = Broken()
    ratelimit._redis_unavailable_logged = False
    try:
        assert client.get("/limited").status_code == 200
    finally:
        ratelimit.reset_client()
