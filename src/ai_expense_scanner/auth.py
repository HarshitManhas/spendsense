from datetime import timedelta
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel, Field

from .config import settings
from .database import database, now

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def csrf_guard(request: Request):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        token = request.headers.get("x-csrf-token", "")
        cookie = request.cookies.get("spendsense_csrf", "")
        if origin != settings().frontend_origin or not token or not secrets.compare_digest(token, cookie):
            raise HTTPException(403, "Request origin or CSRF token is invalid; reload the application")


def current_user(request: Request):
    token = request.cookies.get("spendsense_session")
    if not token:
        raise HTTPException(401, "Sign in to continue")
    session = database().sessions.find_one({"_id": hashlib.sha256(token.encode()).hexdigest(), "expiresAt": {"$gt": now()}})
    if not session:
        raise HTTPException(401, "Session expired; sign in again")
    return session["user"]


def set_session(response, user, request):
    previous = request.cookies.get("spendsense_session")
    if previous:
        database().sessions.delete_one({"_id": hashlib.sha256(previous.encode()).hexdigest()})
    token = secrets.token_urlsafe(32)
    database().sessions.insert_one({"_id": hashlib.sha256(token.encode()).hexdigest(),
        "user": user, "expiresAt": now() + timedelta(hours=12)})
    database().users.update_one({"_id": user["id"]}, {"$set": {**user, "lastLogin": now()}, "$setOnInsert": {"createdAt": now()}}, upsert=True)
    response.set_cookie("spendsense_session", token, httponly=True, samesite="lax",
                        secure=settings().app_env != "development", max_age=43200)
    return user


@router.get("/config")
def config(request: Request, response: Response):
    # Reuse the challenge across tabs so opening another tab does not break forms.
    csrf = request.cookies.get("spendsense_csrf") or secrets.token_urlsafe(32)
    response.set_cookie("spendsense_csrf", csrf, httponly=True, samesite="strict",
                        secure=settings().app_env != "development", max_age=43200)
    response.headers["Cache-Control"] = "no-store"
    return {"googleClientId": settings().google_client_id, "devLogin": settings().allow_dev_login,
            "csrfToken": csrf}


class Credential(BaseModel):
    credential: str = Field(max_length=10000)


@router.post("/google", dependencies=[Depends(csrf_guard)])
def google_login(body: Credential, request: Request, response: Response):
    if not settings().google_client_id:
        raise HTTPException(503, "Google sign-in is not configured yet")
    try:
        claims = id_token.verify_oauth2_token(body.credential, GoogleRequest(), settings().google_client_id)
        if not claims.get("sub") or not claims.get("email_verified"):
            raise ValueError("Unverified identity")
        if not secrets.compare_digest(str(claims.get("nonce", "")), request.cookies.get("spendsense_csrf", "missing")):
            raise ValueError("Invalid login nonce")
    except Exception as exc:
        # Never return the token or identity provider response to logs/clients.
        raise HTTPException(401, "Google identity could not be verified") from exc
    return set_session(response, {"id": "google:" + claims["sub"], "name": claims.get("name", "User"), "email": claims.get("email", "")}, request)


class DevIdentity(BaseModel):
    account: str = Field(pattern="^(alex|sam)$")


@router.post("/development", dependencies=[Depends(csrf_guard)])
def dev_login(body: DevIdentity, request: Request, response: Response):
    if not settings().allow_dev_login or settings().app_env != "development":
        raise HTTPException(404)
    return set_session(response, {"id": f"dev:{body.account}", "name": body.account.title(), "email": f"{body.account}@example.test"}, request)


@router.get("/me")
def me(user=Depends(current_user)):
    return user


@router.post("/logout", dependencies=[Depends(csrf_guard)])
def logout(request: Request, response: Response):
    token = request.cookies.get("spendsense_session", "")
    database().sessions.delete_one({"_id": hashlib.sha256(token.encode()).hexdigest()})
    response.delete_cookie("spendsense_session")
    return {"ok": True}
