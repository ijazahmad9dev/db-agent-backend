from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from db_agent.core.config import get_settings
from db_agent.db.session import get_db
from db_agent.db.models import User
from db_agent.auth.oauth import oauth
from db_agent.auth.jwt import create_access_token
from db_agent.auth.dependencies import get_current_user
from db_agent.security.credentials import encrypt_config

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")
settings = get_settings()


@router.get("/google/login")
async def google_login(request: Request):
    return await oauth.google.authorize_redirect(
        request,
        settings.google_oauth_redirect_uri,
        access_type="offline",
        prompt="consent",
    )


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token["userinfo"]
    refresh_token = token.get("refresh_token")

    logger.info(f"Token response keys: {list(token.keys())}")
    logger.info(f"refresh_token present: {refresh_token is not None}")

    user = db.query(User).filter(User.google_sub == userinfo["sub"]).first()
    if user is None:
        user = User(
            google_sub=userinfo["sub"],
            email=userinfo["email"],
            name=userinfo.get("name"),
            picture_url=userinfo.get("picture"),
        )
        db.add(user)

    if refresh_token:
        user.google_refresh_token_encrypted = encrypt_config({"refresh_token": refresh_token})
        user.google_sheets_scope_granted = True
        logger.info("Stored refresh_token and set google_sheets_scope_granted=True")
    else:
        logger.warning("No refresh_token in response — google_sheets_scope_granted NOT updated")

    db.commit()
    db.refresh(user)
    logger.info(f"After commit — google_sheets_scope_granted: {user.google_sheets_scope_granted}")

    session_token = create_access_token(user.id)
    response = RedirectResponse(url=settings.frontend_url)
    response.set_cookie(
        key="session_token", value=session_token, httponly=True, samesite="lax",
        secure=False, max_age=settings.jwt_expire_minutes * 60,
    )
    return response


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id, "email": current_user.email, "name": current_user.name,
        "picture_url": current_user.picture_url, "sheets_connected": current_user.google_sheets_scope_granted,
    }


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("session_token")
    return {"status": "logged_out"}