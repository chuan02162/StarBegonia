"""OpenFeed FAPI 2.0 helpers: discovery, private_key_jwt, DPoP, tokens."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import current_app
from redis import Redis

ISSUER_DEFAULT = "https://auth.openfeed.au"
API_AUDIENCE = "https://api.openfeed.au"
RESOURCE = "https://api.openfeed.au"
DATA_SCOPES = "openid offline_access openfeed-au:data:banking:read"


class OpenFeedAuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _redis() -> Redis:
    return Redis.from_url(current_app.config["REDIS_URL"])


def issuer() -> str:
    return (current_app.config.get("OPENFEED_ISSUER") or ISSUER_DEFAULT).rstrip("/")


def client_id() -> str:
    cid = (current_app.config.get("OPENFEED_CLIENT_ID") or "").strip()
    if not cid:
        raise OpenFeedAuthError("OPENFEED_CLIENT_ID is not configured", 503)
    return cid


def app_id() -> str:
    aid = (current_app.config.get("OPENFEED_APP_ID") or "").strip()
    if not aid:
        raise OpenFeedAuthError("OPENFEED_APP_ID is not configured", 503)
    return aid


def public_url() -> str:
    url = (current_app.config.get("APP_PUBLIC_URL") or "").rstrip("/")
    if not url:
        raise OpenFeedAuthError(
            "APP_PUBLIC_URL is not configured "
            "(e.g. http://1cchome1.duckdns.org:5173)",
            503,
        )
    return url


def callback_uri() -> str:
    return f"{public_url()}/api/v1/sources/openfeed/callback"


def consent_return_uri() -> str:
    return f"{public_url()}/api/v1/sources/openfeed/consent-return"


def _load_private_key(pem: str):
    text = (pem or "").strip()
    if not text:
        raise OpenFeedAuthError("OpenFeed private key missing", 503)
    # Allow \n escaped in .env
    text = text.replace("\\n", "\n")
    return serialization.load_pem_private_key(text.encode("utf-8"), password=None)


def app_private_key():
    return _load_private_key(current_app.config.get("OPENFEED_APP_PRIVATE_KEY") or "")


def dpop_private_key():
    return _load_private_key(current_app.config.get("OPENFEED_DPOP_PRIVATE_KEY") or "")


def _int_to_b64u(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return jwt.utils.base64url_encode(value.to_bytes(length, "big")).decode()


def public_jwk_from_private(private_key, *, kid: str | None = None) -> dict[str, str]:
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise OpenFeedAuthError("OpenFeed keys must be RSA", 500)
    numbers = private_key.public_key().public_numbers()
    n = _int_to_b64u(numbers.n)
    e = _int_to_b64u(numbers.e)
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "PS256",
        "kid": kid or n[:16],
        "n": n,
        "e": e,
    }


def app_jwks() -> dict[str, Any]:
    """Public JWKS for dashboard jwksUri / inline registration."""
    key = app_private_key()
    kid = (current_app.config.get("OPENFEED_APP_KID") or "").strip() or None
    return {"keys": [public_jwk_from_private(key, kid=kid)]}


def discovery() -> dict[str, Any]:
    url = f"{issuer()}/.well-known/openid-configuration"
    req = Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise OpenFeedAuthError(f"OpenFeed discovery HTTP {exc.code}: {detail}", exc.code) from exc
    except URLError as exc:
        raise OpenFeedAuthError(f"OpenFeed discovery unreachable: {exc.reason}", 502) from exc


def client_assertion() -> str:
    """private_key_jwt — aud must be the issuer URL from discovery."""
    now = int(time.time())
    payload = {
        "iss": client_id(),
        "sub": client_id(),
        "aud": issuer(),
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + 60,
    }
    headers = {"alg": "PS256", "typ": "JWT"}
    kid = (current_app.config.get("OPENFEED_APP_KID") or "").strip()
    if kid:
        headers["kid"] = kid
    return jwt.encode(payload, app_private_key(), algorithm="PS256", headers=headers)


def _b64u_sha256(raw: str) -> str:
    digest = hashlib.sha256(raw.encode("ascii")).digest()
    return jwt.utils.base64url_encode(digest).decode()


def dpop_proof(
    *,
    method: str,
    url: str,
    access_token: str | None = None,
    nonce: str | None = None,
) -> str:
    """RFC 9449 DPoP proof. htu = URL without query/fragment; keep raw '=' in path."""
    htu = url.split("?", 1)[0].split("#", 1)[0]
    now = int(time.time())
    payload: dict[str, Any] = {
        "htu": htu,
        "htm": method.upper(),
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    if access_token:
        payload["ath"] = _b64u_sha256(access_token)
    if nonce:
        payload["nonce"] = nonce

    dpop_key = dpop_private_key()
    kid = (current_app.config.get("OPENFEED_DPOP_KID") or "").strip() or None
    jwk = public_jwk_from_private(dpop_key, kid=kid)
    # DPoP header must embed public JWK (not private); typ dpop+jwt
    headers = {"alg": "PS256", "typ": "dpop+jwt", "jwk": jwk}
    return jwt.encode(payload, dpop_key, algorithm="PS256", headers=headers)


def _form_post(
    url: str,
    fields: dict[str, str],
    *,
    dpop: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    body = urlencode(fields).encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    if dpop:
        headers["DPoP"] = dpop
    if extra_headers:
        headers.update(extra_headers)
    req = Request(url, data=body, method="POST", headers=headers)
    try:
        with urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            hdrs = {k: v for k, v in resp.headers.items()}
            return json.loads(raw) if raw else {}, hdrs
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        hdrs = {k: v for k, v in exc.headers.items()} if exc.headers else {}
        try:
            payload = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            payload = {"error": detail[:400]}
        payload["_http_status"] = exc.code
        return payload, hdrs


def _token_request(fields: dict[str, str]) -> dict[str, Any]:
    disc = discovery()
    token_url = disc["token_endpoint"]
    fields = {
        **fields,
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": client_assertion(),
        "resource": RESOURCE,
    }
    nonce: str | None = None
    for _ in range(2):
        proof = dpop_proof(method="POST", url=token_url, nonce=nonce)
        payload, hdrs = _form_post(token_url, fields, dpop=proof)
        if payload.get("error") == "use_dpop_nonce" or (
            payload.get("_http_status") == 400 and "use_dpop_nonce" in str(payload)
        ):
            nonce = hdrs.get("DPoP-Nonce") or hdrs.get("dpop-nonce")
            if nonce:
                continue
        if payload.get("_http_status") and payload.get("_http_status") >= 400:
            raise OpenFeedAuthError(
                f"OpenFeed token error: {payload.get('error') or payload}",
                int(payload.get("_http_status") or 502),
            )
        if "access_token" not in payload:
            raise OpenFeedAuthError(f"OpenFeed token response missing access_token: {payload}", 502)
        return payload
    raise OpenFeedAuthError("OpenFeed DPoP nonce retry exhausted", 502)


def start_authorization(*, person_id: int) -> str:
    """PAR + return browser redirect URL to OpenFeed authorization_endpoint."""
    disc = discovery()
    par_url = disc["pushed_authorization_request_endpoint"]
    code_verifier = secrets.token_urlsafe(64)
    challenge = _b64u_sha256(code_verifier)
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)

    fields = {
        "response_type": "code",
        "client_id": client_id(),
        "redirect_uri": callback_uri(),
        "scope": DATA_SCOPES,
        "resource": RESOURCE,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "nonce": nonce,
        "state": state,
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": client_assertion(),
    }
    payload, _ = _form_post(par_url, fields)
    if payload.get("_http_status") and int(payload["_http_status"]) >= 400:
        raise OpenFeedAuthError(
            f"OpenFeed PAR failed: {payload.get('error') or payload}",
            int(payload.get("_http_status") or 502),
        )
    request_uri = payload.get("request_uri")
    if not request_uri:
        raise OpenFeedAuthError(f"OpenFeed PAR missing request_uri: {payload}", 502)

    r = _redis()
    r.setex(
        f"openfeed:oauth:{state}",
        600,
        json.dumps(
            {
                "person_id": person_id,
                "code_verifier": code_verifier,
                "nonce": nonce,
            }
        ),
    )

    auth_url = (
        f"{disc['authorization_endpoint']}"
        f"?{urlencode({'client_id': client_id(), 'request_uri': request_uri})}"
    )
    return auth_url


def exchange_code(*, code: str, state: str) -> tuple[int, dict[str, Any]]:
    r = _redis()
    raw = r.get(f"openfeed:oauth:{state}")
    if not raw:
        raise OpenFeedAuthError("OAuth state expired or unknown — try connecting again", 400)
    r.delete(f"openfeed:oauth:{state}")
    meta = json.loads(raw)
    person_id = int(meta["person_id"])
    token = _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": meta["code_verifier"],
            "redirect_uri": callback_uri(),
            "client_id": client_id(),
        }
    )
    return person_id, token


def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    return _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id(),
        }
    )


def grant_id_from_token_response(token: dict[str, Any]) -> str | None:
    details = token.get("authorization_details") or []
    if isinstance(details, list) and details:
        gid = details[0].get("grant_id")
        return str(gid) if gid else None
    return None


def disclosure_consent_url(*, person_id: int) -> str:
    # Embed person_id in redirectUri so the consent-return handler can find the cred
    # without a StarBegonia JWT (browser redirect has none).
    return_uri = f"{consent_return_uri()}?pid={int(person_id)}"
    return (
        "https://app.openfeed.au/grants/disclosure?"
        + urlencode({"appId": app_id(), "redirectUri": return_uri})
    )


def api_get(path: str, *, access_token: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    """Authenticated Sharing API GET with DPoP."""
    base = f"{API_AUDIENCE}/v1{path}"
    url = base
    if params:
        # Build query without encoding '=' inside path segments (path has none here).
        url = f"{base}?{urlencode(params)}"
    nonce: str | None = None
    for _ in range(2):
        proof = dpop_proof(
            method="GET", url=url, access_token=access_token, nonce=nonce
        )
        req = Request(
            url,
            method="GET",
            headers={
                "Authorization": f"DPoP {access_token}",
                "DPoP": proof,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            hdrs = {k: v for k, v in exc.headers.items()} if exc.headers else {}
            if exc.code == 400 and "use_dpop_nonce" in detail:
                nonce = hdrs.get("DPoP-Nonce") or hdrs.get("dpop-nonce")
                if nonce:
                    continue
            raise OpenFeedAuthError(
                f"OpenFeed API HTTP {exc.code}: {detail[:400]}", exc.code
            ) from exc
        except URLError as exc:
            raise OpenFeedAuthError(f"OpenFeed API unreachable: {exc.reason}", 502) from exc
    raise OpenFeedAuthError("OpenFeed API DPoP nonce retry exhausted", 502)


def configured() -> bool:
    return bool(
        (current_app.config.get("OPENFEED_CLIENT_ID") or "").strip()
        and (current_app.config.get("OPENFEED_APP_ID") or "").strip()
        and (current_app.config.get("OPENFEED_APP_PRIVATE_KEY") or "").strip()
        and (current_app.config.get("OPENFEED_DPOP_PRIVATE_KEY") or "").strip()
        and (current_app.config.get("APP_PUBLIC_URL") or "").strip()
    )
