"""Single-owner OAuth for a hosted memory server.

claude.ai connectors (web, phone, desktop app) can only reach a remote MCP
server through OAuth 2.1 with dynamic client registration; they have no
place to put a static header. This is the smallest authorization server
that satisfies them for ONE person: any client may register, but a client
only gets a token after someone types the owner's password into the
server's own /login page. The MCP SDK provides the protocol endpoints
(metadata, register, authorize, token, revoke); this module provides the
storage and the login step.

Two kinds of credential are accepted on every protected route:

- the static token (`--token` / MEMORY_GRAPH_TOKEN) — what Claude Code
  machines and scripts send as `Authorization: Bearer <token>`;
- access tokens this module issued through OAuth.

Issued tokens are persisted as SHA-256 hashes (oauth.json in the state
home), so a copy of that file grants nothing. Restarting the server keeps
connectors signed in.

The settings page (chat.py) can change the password and replace the token.
Those are stored in the same file — the password as a salted scrypt hash,
the token as SHA-256 — and from then on take precedence over
MEMORY_GRAPH_PASSWORD / MEMORY_GRAPH_TOKEN. Deleting oauth.json returns to
the configured values (and signs everything out).
"""

import hashlib
import hmac
import html
import json
import logging
import os
import secrets
import time
from pathlib import Path

from mcp.server.auth.provider import (AccessToken, AuthorizationCode, AuthorizationParams,
                                      RefreshToken, TokenError, construct_redirect_uri)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

log = logging.getLogger(__name__)

SCOPE = "memory"
CODE_TTL = 300                       # seconds an authorization code lives
ACCESS_TTL = 24 * 3600               # connectors refresh this silently
REFRESH_TTL = 180 * 24 * 3600        # how long a connector stays signed in unused
LOGIN_TTL = 900                      # a login page left open this long expires
MAX_FAILURES = 5                     # wrong passwords before the login locks…
LOCKOUT = 300                        # …for this many seconds


_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1}
MIN_PASSWORD = 8


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class OwnerAuth:
    """OAuthAuthorizationServerProvider for a single owner, plus the static
    token. Also usable as a TokenVerifier (verify_token)."""

    def __init__(self, path: Path, static_token: str, password: str, issuer: str):
        self.path = path
        self.static_token = static_token
        self.password = password        # empty: the token doubles as the password
        self.issuer = issuer.rstrip("/")
        self.clients: dict[str, dict] = {}
        self.access: dict[str, dict] = {}      # sha256(token) -> AccessToken fields
        self.refresh: dict[str, dict] = {}     # sha256(token) -> RefreshToken fields
        self.codes: dict[str, AuthorizationCode] = {}       # memory only
        self.pending: dict[str, tuple[float, str, AuthorizationParams]] = {}
        self.failures: list[float] = []
        self.password_override: dict | None = None    # {"salt", "hash"} (scrypt)
        self.token_override: str | None = None         # sha256 of the token
        self.on_sign_out: list = []                    # callbacks: chat sessions etc.
        self._load()

    # ------------------------------------------------------------ storage

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return
        self.clients = data.get("clients", {})
        now = time.time()
        self.access = {k: v for k, v in data.get("access", {}).items()
                       if (v.get("expires_at") or now + 1) > now}
        self.refresh = {k: v for k, v in data.get("refresh", {}).items()
                        if (v.get("expires_at") or now + 1) > now}
        self.password_override = data.get("password")
        self.token_override = data.get("token")

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"clients": self.clients, "access": self.access,
                                   "refresh": self.refresh, "password": self.password_override,
                                   "token": self.token_override}, indent=1))
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    # ------------------------------------------------------------ clients

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        data = self.clients.get(client_id)
        return OAuthClientInformationFull.model_validate(data) if data else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients[client_info.client_id] = client_info.model_dump(mode="json")
        self._save()
        log.info("oauth: registered client %s (%s)", client_info.client_id,
                 client_info.client_name or "unnamed")

    # -------------------------------------------------------- authorizing

    async def authorize(self, client: OAuthClientInformationFull,
                        params: AuthorizationParams) -> str:
        request_id = secrets.token_urlsafe(24)
        self._expire_pending()
        self.pending[request_id] = (time.time(), client.client_id, params)
        return f"{self.issuer}/login?request={request_id}"

    def _expire_pending(self) -> None:
        cutoff = time.time() - LOGIN_TTL
        for key in [k for k, (t, _, _) in self.pending.items() if t < cutoff]:
            del self.pending[key]

    def locked(self) -> bool:
        cutoff = time.time() - LOCKOUT
        self.failures = [t for t in self.failures if t > cutoff]
        return len(self.failures) >= MAX_FAILURES

    def _password_ok(self, password: str) -> bool:
        if self.password_override:
            salt = bytes.fromhex(self.password_override["salt"])
            digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT).hex()
            return hmac.compare_digest(digest, self.password_override["hash"])
        if self.password:
            return hmac.compare_digest(password.encode(), self.password.encode())
        # no password configured: the CURRENT token is the password, so
        # replacing a leaked token also retires it as a password
        return self._token_ok(password)

    def _token_ok(self, token: str) -> bool:
        if self.token_override:
            return hmac.compare_digest(_hash(token), self.token_override)
        return bool(self.static_token) and hmac.compare_digest(token.encode(),
                                                               self.static_token.encode())

    def _guard(self, ok: bool, what: str) -> bool:
        if self.locked():
            return False
        if ok:
            return True
        self.failures.append(time.time())
        log.warning("wrong %s on a sign-in or settings page", what)
        return False

    def check_password(self, password: str) -> bool:
        """The owner password, as typed on a sign-in page (connector or chat).
        Wrong guesses count towards the shared lockout."""
        return self._guard(self._password_ok(password), "password")

    def check_token(self, token: str) -> bool:
        """The server token, as typed on the settings page: changing settings
        needs it, so someone who only has the password (a colleague on a
        handover share) can chat but not lock the owner out."""
        return self._guard(self._token_ok(token), "token")

    # ------------------------------------------------------------ settings

    @property
    def manageable(self) -> bool:
        return bool(self.static_token or self.token_override)

    def sign_out_all(self) -> int:
        """Every connector and every browser signs in again. Returns how many
        connectors were signed out."""
        count = len(self.clients)
        self.clients, self.access, self.refresh = {}, {}, {}
        self.codes.clear()
        self.pending.clear()
        self._save()
        for callback in self.on_sign_out:
            callback()
        log.warning("settings: signed everything out (%d connector(s))", count)
        return count

    def set_password(self, new: str) -> None:
        """A new password, and everything signs in again with it."""
        salt = secrets.token_bytes(16)
        self.password_override = {
            "salt": salt.hex(),
            "hash": hashlib.scrypt(new.encode(), salt=salt, **_SCRYPT).hex()}
        self.sign_out_all()
        log.warning("settings: password changed")

    def new_token(self) -> str:
        """Replace the server token. Returned once; only its hash is kept.
        Every Claude Code machine needs the new one in its plugin settings."""
        token = secrets.token_hex(32)
        self.token_override = _hash(token)
        self._save()
        log.warning("settings: server token replaced")
        return token

    def login(self, request_id: str, password: str) -> str | None:
        """The owner typed a password on /login. Returns the redirect back to
        the client (carrying the authorization code), or None on failure."""
        self._expire_pending()
        if self.locked() or request_id not in self.pending:
            return None
        if not self.check_password(password):
            return None
        _, client_id, params = self.pending.pop(request_id)
        code = AuthorizationCode(
            code=secrets.token_urlsafe(32), client_id=client_id,
            scopes=params.scopes or [SCOPE], expires_at=time.time() + CODE_TTL,
            code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource, subject="owner")
        self.codes[code.code] = code
        log.info("oauth: owner approved client %s", client_id)
        return construct_redirect_uri(str(params.redirect_uri), code=code.code,
                                      state=params.state)

    def pending_client_name(self, request_id: str) -> str | None:
        entry = self.pending.get(request_id)
        if not entry:
            return None
        client = self.clients.get(entry[1], {})
        return client.get("client_name") or entry[1]

    # -------------------------------------------------------------- tokens

    async def load_authorization_code(self, client, authorization_code: str):
        code = self.codes.get(authorization_code)
        if code and code.client_id == client.client_id and code.expires_at > time.time():
            return code
        return None

    def _issue(self, client_id: str, scopes: list[str], resource: str | None) -> OAuthToken:
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = int(time.time())
        self.access[_hash(access)] = {"client_id": client_id, "scopes": scopes,
                                      "expires_at": now + ACCESS_TTL,
                                      "resource": resource, "refresh": _hash(refresh)}
        self.refresh[_hash(refresh)] = {"client_id": client_id, "scopes": scopes,
                                        "expires_at": now + REFRESH_TTL,
                                        "resource": resource}
        self._save()
        return OAuthToken(access_token=access, token_type="Bearer",
                          expires_in=ACCESS_TTL, refresh_token=refresh,
                          scope=" ".join(scopes))

    async def exchange_authorization_code(self, client, authorization_code) -> OAuthToken:
        if self.codes.pop(authorization_code.code, None) is None:
            raise TokenError("invalid_grant", "authorization code already used")
        return self._issue(client.client_id, authorization_code.scopes,
                           authorization_code.resource)

    async def load_refresh_token(self, client, refresh_token: str):
        data = self.refresh.get(_hash(refresh_token))
        if not data or data["client_id"] != client.client_id:
            return None
        return RefreshToken(token=refresh_token, subject="owner",
                            **{k: data[k] for k in ("client_id", "scopes", "expires_at",
                                                    "resource")})

    async def exchange_refresh_token(self, client, refresh_token, scopes) -> OAuthToken:
        # rotate: the old refresh token and the access tokens it minted die
        old = _hash(refresh_token.token)
        self.refresh.pop(old, None)
        self.access = {k: v for k, v in self.access.items() if v.get("refresh") != old}
        return self._issue(client.client_id, scopes or refresh_token.scopes,
                           refresh_token.resource)

    async def load_access_token(self, token: str) -> AccessToken | None:
        if self._token_ok(token):
            return AccessToken(token=token, client_id="static-token", scopes=[SCOPE],
                               subject="owner")
        data = self.access.get(_hash(token))
        if not data or (data.get("expires_at") or 0) < time.time():
            return None
        return AccessToken(token=token, subject="owner",
                           **{k: data[k] for k in ("client_id", "scopes", "expires_at",
                                                   "resource")})

    verify_token = load_access_token      # TokenVerifier protocol

    async def revoke_token(self, token) -> None:
        digest = _hash(token.token)
        if digest in self.refresh:
            self.refresh.pop(digest)
            self.access = {k: v for k, v in self.access.items() if v.get("refresh") != digest}
        else:
            self.access.pop(digest, None)
        self._save()



# ------------------------------------------------------------------ login page

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Memory graph — sign in</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;background:#f6f6f4;color:#222;margin:0;
display:flex;min-height:100vh;align-items:center;justify-content:center}}
@media (prefers-color-scheme:dark){{body{{background:#1b1b1a;color:#eee}}
input{{background:#2a2a28;color:#eee;border-color:#555}}}}
main{{max-width:22rem;width:100%;padding:1.5rem}}
input,button{{font:inherit;width:100%;box-sizing:border-box;padding:.7rem;
border-radius:.5rem;border:1px solid #bbb;margin-top:.6rem}}
button{{background:#2f5d50;color:#fff;border:0;cursor:pointer}}
.err{{color:#b3261e}}
</style></head><body><main>
<h1 style="font-size:1.3rem">Memory graph</h1>
<p><b>{client}</b> wants read and write access to your memory.</p>
{error}
<form method="post" action="login">
<input type="hidden" name="request" value="{request}">
<input type="password" name="password" placeholder="Server password"
 autocomplete="current-password" autofocus required>
<button type="submit">Allow</button>
</form></main></body></html>"""


def login_routes(auth: OwnerAuth):
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, RedirectResponse
    from starlette.routing import Route

    def page(request_id: str, client: str, error: str = "", status: int = 200):
        body = _PAGE.format(client=html.escape(client), request=html.escape(request_id),
                            error=f'<p class="err">{html.escape(error)}</p>' if error else "")
        return HTMLResponse(body, status_code=status, headers={
            "Cache-Control": "no-store", "X-Frame-Options": "DENY",
            # no form-action: browsers apply it to the redirect after the post,
            # which goes back to the app (claude.ai), not to this server
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                                       "frame-ancestors 'none'"})

    async def show(request: Request):
        request_id = request.query_params.get("request", "")
        client = auth.pending_client_name(request_id)
        if client is None:
            return HTMLResponse("This sign-in link has expired. Start again from the app.",
                                status_code=400)
        return page(request_id, client)

    async def submit(request: Request):
        form = await request.form()
        request_id = str(form.get("request", ""))
        client = auth.pending_client_name(request_id)
        if client is None:
            return HTMLResponse("This sign-in link has expired. Start again from the app.",
                                status_code=400)
        if auth.locked():
            return page(request_id, client, "Too many wrong passwords. Try again in a few "
                        "minutes.", 429)
        target = auth.login(request_id, str(form.get("password", "")))
        if target is None:
            import asyncio
            await asyncio.sleep(1)             # make guessing slow as well as limited
            return page(request_id, client, "Wrong password.", 401)
        return RedirectResponse(target, status_code=302)

    return [Route("/login", show, methods=["GET"]),
            Route("/login", submit, methods=["POST"])]
