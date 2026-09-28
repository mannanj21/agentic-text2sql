from typing import Any

import pytest
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.main import app
from app.auth import current_user
from app.database.models import User

# --- Placeholder Router for Authz Harness ---
mock_router = APIRouter(prefix="/test-resource", tags=["Test"])

# Mock database for resources mapping resource_id -> owner_id
MOCK_RESOURCES = {
    "resource-a": "will-be-replaced-with-user-a-id",
    "resource-b": "will-be-replaced-with-user-b-id",
}


@mock_router.get("/{resource_id}")
async def get_test_resource(
    resource_id: str,
    user: User = Depends(current_user),  # noqa: B008
) -> dict[str, Any]:
    owner_id = MOCK_RESOURCES.get(resource_id)
    if not owner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Ownership Check Convention: Return 404 if the resource belongs to someone else
    if owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    return {"resource_id": resource_id, "data": "secret"}


@pytest.fixture(autouse=True)
def setup_mock_router():
    app.include_router(mock_router)
    yield
    app.routes = [r for r in app.routes if getattr(r, "path", "") != "/test-resource/{resource_id}"]


@pytest.mark.asyncio
async def test_two_users_authz_harness(two_users: dict[str, Any]) -> None:
    """Test that user_a can access their own resource, but gets 404 for user_b's resource."""
    user_a_id = two_users["user_a_id"]
    user_b_id = two_users["user_b_id"]
    client_a = two_users["client_a"]
    client_b = two_users["client_b"]

    MOCK_RESOURCES["resource-a"] = user_a_id
    MOCK_RESOURCES["resource-b"] = user_b_id

    # User A accesses Resource A (Success)
    resp = await client_a.get("/test-resource/resource-a")
    assert resp.status_code == 200
    assert resp.json()["data"] == "secret"

    # User A accesses Resource B (404 Not Found to prevent existence leak)
    resp = await client_a.get("/test-resource/resource-b")
    assert resp.status_code == 404

    # User B accesses Resource B (Success)
    resp = await client_b.get("/test-resource/resource-b")
    assert resp.status_code == 200

    # User B accesses Resource A (404 Not Found)
    resp = await client_b.get("/test-resource/resource-a")
    assert resp.status_code == 404
