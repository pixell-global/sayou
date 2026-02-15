"""Auth dependency for the REST API.

Simple Bearer token → (org_id, user_id) mapping.
In production, this would verify JWTs. For now, the token is the user_id
and org_id is passed via X-Org-Id header.
"""

from __future__ import annotations

from fastapi import Header, HTTPException


async def get_identity(
    authorization: str = Header(default=""),
    x_org_id: str = Header(default=""),
) -> tuple[str, str]:
    """Extract (org_id, user_id) from request headers.

    Authorization: Bearer <user_id>
    X-Org-Id: <org_id>
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    user_id = authorization[7:].strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Empty bearer token")

    org_id = x_org_id.strip()
    if not org_id:
        raise HTTPException(status_code=401, detail="Missing X-Org-Id header")

    return org_id, user_id
