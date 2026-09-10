from authlib.integrations.starlette_client import OAuth

from db_agent.core.config import get_settings

settings = get_settings()

oauth = OAuth()

_GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_ACCESS_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"

oauth.register(
    name="google",
    client_id=settings.google_oauth_client_id,
    client_secret=settings.google_oauth_client_secret,
    authorize_url=_GOOGLE_AUTHORIZE_URL,
    access_token_url=_GOOGLE_ACCESS_TOKEN_URL,
    jwks_uri=_GOOGLE_JWKS_URI,
    client_kwargs={
        "scope": f"openid email profile {settings.google_sheets_scope}",
        "access_type": "offline",  # required to receive a refresh_token at all
        "prompt": "consent",       # required to guarantee Google returns a refresh_token every time — see note below
    },
)