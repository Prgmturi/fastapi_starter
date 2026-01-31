from fastapi import APIRouter

from fastapi_starter.core.auth.dependencies import AdminUser, CurrentUser

auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.get("/auth/me")
async def get_me(user: CurrentUser) -> dict:
    """Test endpoint - returns current user info."""
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "roles": [r.value for r in user.roles],
        "full_name": user.full_name,
    }

@auth_router.get("/auth/admin")
async def admin_only(user: AdminUser) -> dict:
    """Test endpoint - requires admin role."""
    return {
        "message": "Welcome admin!",
        "user": user.username,
    }
