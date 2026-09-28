from fastapi.routing import APIRoute

from app.api.main import app
from app.auth import current_user

PUBLIC_ALLOWLIST = {
    "/health",
    "/auth/register",
    "/auth/login",
    "/auth/logout",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}


def test_all_private_routes_require_current_user():
    """
    Ensure every route (except the public allowlist) requires `current_user`
    either as a route dependency or as an injected parameter.
    """
    unsecured_routes = []

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue

        if route.path in PUBLIC_ALLOWLIST:
            continue

        # Check if current_user is in the dependencies tree
        # APIRoute has a `dependant` object which represents the parsed dependencies
        has_current_user = False

        # We need to traverse the dependant tree to find the current_user dependency
        def check_dependant(dependant):
            if dependant.call is current_user:
                return True
            return any(check_dependant(sub_dep) for sub_dep in dependant.dependencies)

        if check_dependant(route.dependant):
            has_current_user = True

        if not has_current_user:
            unsecured_routes.append(f"{route.methods} {route.path}")

    assert not unsecured_routes, (
        f"The following routes are missing current_user: {unsecured_routes}"
    )
