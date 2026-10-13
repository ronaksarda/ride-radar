"""Small HTTP helpers shared by the API modules."""
import hashlib
import hmac

from fastapi import Depends, HTTPException, Request

from app import config, ratelimit


def client_id(request: Request):
    return request.client.host if request.client else "unknown"


def limit(bucket):
    def dependency(request: Request):
        if not ratelimit.allow(bucket, client_id(request)):
            raise HTTPException(429, "Too many requests. Wait a little and try again.")
    return Depends(dependency)


def require_admin(request: Request):
    if not ratelimit.allow("admin", client_id(request)):
        raise HTTPException(429, "Too many requests. Wait a little and try again.")
    if not config.ADMIN_TOKEN:
        return
    given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given.encode(), config.ADMIN_TOKEN.encode()):
        raise HTTPException(401, "Admin token required.")


def key_hash(key):
    return hashlib.sha256(key.encode()).hexdigest()


def require_owner(row, request: Request, column="owner_key_hash"):
    given = request.headers.get("x-owner-key", "")
    if not given or not hmac.compare_digest(key_hash(given), row[column]):
        raise HTTPException(403, "Only the rider who created this can change it.")


def base_url(request: Request):
    return config.PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
