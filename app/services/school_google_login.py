"""School-only Google OpenID Connect login with verified student number matching."""
import json
import secrets
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DOMAIN = "stu.ukn.edu.tw"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleLoginError(Exception):
    pass


def configured(config):
    return all(config.get(key) for key in (
        "GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_LOGIN_REDIRECT_URI"
    ))


def new_state():
    return secrets.token_urlsafe(32)


def authorization_url(config, state):
    return AUTH_URL + "?" + urlencode({
        "client_id": config["GOOGLE_OAUTH_CLIENT_ID"],
        "redirect_uri": config["GOOGLE_LOGIN_REDIRECT_URI"],
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    })


class HttpGoogleLoginClient:
    def __init__(self, config):
        self.config = config

    def verify_code(self, code):
        body = urlencode({
            "code": code,
            "client_id": self.config["GOOGLE_OAUTH_CLIENT_ID"],
            "client_secret": self.config["GOOGLE_OAUTH_CLIENT_SECRET"],
            "redirect_uri": self.config["GOOGLE_LOGIN_REDIRECT_URI"],
            "grant_type": "authorization_code",
        }).encode()
        try:
            with urlopen(Request(TOKEN_URL, data=body, method="POST", headers={
                "Content-Type": "application/x-www-form-urlencoded"
            }), timeout=10) as response:
                payload = json.load(response)
            token = payload["id_token"]
            from google.auth.transport.requests import Request as GoogleRequest
            from google.oauth2 import id_token
            claims = id_token.verify_oauth2_token(token, GoogleRequest(), self.config["GOOGLE_OAUTH_CLIENT_ID"])
        except Exception as error:
            raise GoogleLoginError("Google identity verification failed") from error
        if not isinstance(claims, dict):
            raise GoogleLoginError("Invalid Google identity")
        return claims


def client_for(app):
    return app.config.get("GOOGLE_LOGIN_CLIENT") or HttpGoogleLoginClient(app.config)


def school_identity(claims):
    if not isinstance(claims, dict) or claims.get("email_verified") is not True:
        return None
    email = claims.get("email")
    sub = claims.get("sub")
    if not isinstance(email, str) or not isinstance(sub, str) or not sub:
        return None
    email = email.lower()
    if email.count("@") != 1 or email.split("@", 1)[1] != DOMAIN or claims.get("hd") not in (DOMAIN, "ukn.edu.tw"):
        return None
    return email, sub
