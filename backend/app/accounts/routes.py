import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.accounts import service
from app.settings_security.crypto import new_session_token
from app.accounts.models import User
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)
    display_name: str | None = Field(default=None, max_length=80)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)


def _public(user: User) -> dict:
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name,
            "auth_provider": user.auth_provider, "is_admin": user.is_admin}


@router.post("/register", status_code=201)
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)):
    user = service.register(db, body.email, body.password, body.display_name)
    service.start_session_for(db, user, response)
    return _public(user)


@router.post("/login")
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    return _public(service.login(db, body.email, body.password, response))


@router.post("/logout")
def logout(response: Response, db: Session = Depends(get_db), cos_session: str | None = Cookie(default=None, alias=service.COOKIE_NAME)):
    service.logout(db, cos_session, response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(service.current_user)):
    return _public(user)


@router.get("/providers")
def providers():
    """Which sign-in options can be used on this installation."""
    from app.config import settings
    return {
        "local": {"enabled": True},
        "google": {"enabled": bool(settings.google_client_id and settings.google_client_secret)},
        "supabase": {"enabled": False, "reason": "Not configured yet. See docs/PROJECT_DOCUMENTATION.md."},
    }


GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"


@router.get("/google/start")
def google_start(db: Session = Depends(get_db)):
    """Sends the browser to Google. Refused with a clear message until Google is configured."""
    from urllib.parse import urlencode
    from fastapi.responses import RedirectResponse
    from app.config import settings
    if not (settings.google_client_id and settings.google_client_secret):
        raise HTTPException(status_code=503, detail="Google sign-in is not configured. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to backend/.env.")
    state = new_session_token()
    query = urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })
    response = RedirectResponse(f"{GOOGLE_AUTH}?{query}", status_code=302)
    response.set_cookie("cos_oauth_state", state, httponly=True, samesite="lax", path="/api/auth/google", max_age=600)
    return response


@router.get("/google/callback")
def google_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)):
    """Exchanges the code with Google, reads the verified email, then signs the person in."""
    import httpx
    from fastapi.responses import RedirectResponse
    from app.config import settings
    expected = request.cookies.get("cos_oauth_state")
    if not expected or expected != state:
        raise HTTPException(status_code=400, detail="Sign-in expired or was tampered with. Try again.")
    with httpx.Client(timeout=15) as client:
        token = client.post(GOOGLE_TOKEN, data={
            "code": code, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri, "grant_type": "authorization_code",
        })
        if token.status_code != 200:
            raise HTTPException(status_code=401, detail="Google did not accept the sign-in.")
        info = client.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {token.json().get('access_token')}"})
    if info.status_code != 200:
        raise HTTPException(status_code=401, detail="Could not read the Google account.")
    profile = info.json()
    email = (profile.get("email") or "").lower()
    if not profile.get("email_verified") or not email:
        raise HTTPException(status_code=403, detail="Google account email is not verified.")

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(id=uuid.uuid4(), email=email, display_name=profile.get("name") or email.split("@")[0],
                    password_hash=None, auth_provider="google")
        db.add(user)
        db.commit()
        db.refresh(user)
    response = RedirectResponse(f"{settings.frontend_url}/", status_code=302)
    service.start_session_for(db, user, response)
    response.delete_cookie("cos_oauth_state", path="/api/auth/google")
    return response
