"""OpenAPI-derived authorization coverage for every protected resource-ID route."""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app

pytestmark = [pytest.mark.authz, pytest.mark.integration]


# Every case uses an ID belonging to user A while requests are sent as user B.
# The mapping is deliberately keyed by (method, OpenAPI path), so a new resource
# route fails the coverage assertion until it has explicit safe request data.
RESOURCE_CASES: dict[tuple[str, str], dict[str, Any]] = {
    ("DELETE", "/connections/{connection_id}"): {},
    ("POST", "/connections/{connection_id}/sync"): {},
    ("GET", "/connections/{connection_id}/schema"): {},
    ("PATCH", "/connections/{connection_id}/schema"): {"json": {"tables": [], "columns": []}},
    ("GET", "/connections/{connection_id}/glossary"): {},
    ("POST", "/connections/{connection_id}/glossary"): {
        "json": {"term": "blocked", "definition": "blocked"}
    },
    ("DELETE", "/connections/{connection_id}/glossary/{term_id}"): {},
    ("DELETE", "/conversations/{conversation_id}"): {},
    ("PATCH", "/conversations/{conversation_id}"): {"json": {"title": "blocked"}},
    ("POST", "/conversations/{conversation_id}/query"): {"json": {"question": "blocked"}},
    ("GET", "/runs/{run_id}"): {},
}


def _resource_operations() -> set[tuple[str, str]]:
    schema = app.openapi()
    return {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        if "{" in path and not path.startswith(("/auth/", "/test-resource/"))
        for method in operations
        if method in {"get", "post", "patch", "put", "delete"}
    }


def test_every_openapi_resource_route_has_a_matrix_case() -> None:
    assert _resource_operations() == set(RESOURCE_CASES)


@pytest.mark.parametrize("operation", sorted(RESOURCE_CASES))
@pytest.mark.asyncio
async def test_other_user_gets_not_found_for_every_resource_route(
    two_users: dict[str, Any], operation: tuple[str, str]
) -> None:
    method, path = operation
    request = RESOURCE_CASES[operation]
    response = await two_users["client_b"].request(
        method,
        path.format(**two_users["resource_ids"]),
        **request,
    )
    assert response.status_code == 404


@pytest.mark.parametrize("operation", sorted(RESOURCE_CASES))
@pytest.mark.asyncio
async def test_unauthenticated_request_is_rejected_for_every_resource_route(
    two_users: dict[str, Any], operation: tuple[str, str]
) -> None:
    method, path = operation
    request = RESOURCE_CASES[operation]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(
            method,
            path.format(**two_users["resource_ids"]),
            **request,
        )
    assert response.status_code == 401
