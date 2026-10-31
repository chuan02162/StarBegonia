"""Probe whether Everyday Rewards Auth0 can silently issue a fresh code.

Replays the authorization request with ``prompt=none`` (instead of the
interactive ``prompt=login``) while carrying the user's Auth0 SSO cookie. If
the SSO session is still valid, Auth0 should 302 to the callback URL with a new
authorization ``code``, which we then exchange via ``/wx/v2/security/token``
for a fresh bearer -- no password or MFA required.

Expected environment:

    WWS_PROBE_AUTH0_COOKIE  -> Cookie header value for auth.everyday.com.au

Only statuses, fingerprints, and expiry seconds are printed. Token values are
never printed or persisted.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

AUTHORIZE_URL = "https://auth.everyday.com.au/authorize"
LOGIN_URL = "https://api.everyday.com.au/wx/v2/security/login/url"
SECURITY_TOKEN_URL = "https://api.everyday.com.au/wx/v2/security/token"
GRAPHQL_URL = "https://apigee-prod.api-wr.com/wx/v1/bff/graphql"
AUTH0_CLIENT_ID = "wWG2vmdG9vsNvGKPQcYz56LwCuRfKVF8"
CLIENT_ID = "8h41mMOiDULmlLT28xKSv5ITpp3XBRvH"
AUDIENCE = "https://www.woolworthsrewards.com.au/auth/"
CALLBACK = "https://www.everyday.com.au/callback"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)

ACTIVITY_QUERY = """
query ProbeActivityHome($featureFlags: ActivityHomeFeatureFlags) {
  activityHome(featureFlags: $featureFlags) {
    __typename
    ... on ActivityHomePage {
      results {
        sections {
          sectionItems {
            __typename
            ... on RewardsActivityItem {
              id
              receipt { receiptId }
            }
          }
        }
        nextPageToken
      }
    }
  }
}
"""


def fp(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_no_redirect = build_opener(_NoRedirect, HTTPSHandler())


def _read_error_body(exc: HTTPError) -> str:
    try:
        return exc.read(300).decode("utf-8", errors="replace")
    except Exception:
        return ""


def silent_authorize(cookie_header: str) -> dict[str, Any]:
    url, state = get_login_url()
    if url is None:
        return {"error": "login/url failed", "state": state}
    # Ask Auth0 to issue the code silently; falls back to a login prompt when
    # the SSO session is no longer valid.
    url = url.replace("prompt=login", "prompt=none")
    if "prompt=" not in url:
        url += ("&" if "?" in url else "?") + "prompt=none"
    req = Request(
        url,
        headers={
            "Cookie": cookie_header,
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": BROWSER_UA,
        },
    )
    result: dict[str, Any] = {"state": state}
    try:
        with _no_redirect.open(req, timeout=30) as response:
            result["status"] = response.status
            result["location"] = response.headers.get("Location")
    except HTTPError as exc:
        result["status"] = exc.code
        result["location"] = exc.headers.get("Location")
        result["body_head"] = _read_error_body(exc)[:200]
    except URLError as exc:
        result["status"] = None
        result["error"] = str(exc)
    return result


def get_login_url() -> tuple[str | None, str | None]:
    state = make_state()
    query = urlencode(
        {
            "state": state,
            "redirectUri": CALLBACK,
            "newSignup": "true",
        }
    )
    req = Request(
        f"{LOGIN_URL}?{query}",
        headers={
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://www.everyday.com.au",
            "Referer": "https://www.everyday.com.au/",
            "User-Agent": "StarBegonia-rewards-probe/1.0",
            "client_id": CLIENT_ID,
        },
    )
    try:
        with _no_redirect.open(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return None, f"login/url HTTP {exc.code}: {_read_error_body(exc)[:120]}"
    except URLError as exc:
        return None, f"login/url network error: {exc}"
    data = (body or {}).get("data") or {}
    url = data.get("url")
    if not url:
        return None, f"login/url missing url: {json.dumps(body)[:120]}"
    parsed = urlsplit(url)
    auth0_state = (parse_qs(parsed.query).get("state") or [None])[0]
    return url, auth0_state


def make_state() -> str:
    import base64
    import time

    payload = json.dumps(
        {
            "redirectUri": "https://www.everyday.com.au/index.html#/my-activity",
            "nonce": str(int(time.time() * 1000)),
        }
    )
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def exchange_code(code: str, state: str) -> dict[str, Any]:
    payload = {"code": code, "state": state, "redirectUri": CALLBACK}
    req = Request(
        SECURITY_TOKEN_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://www.everyday.com.au",
            "Referer": "https://www.everyday.com.au/",
            "User-Agent": "StarBegonia-rewards-probe/1.0",
            "client_id": CLIENT_ID,
        },
    )
    try:
        with _no_redirect.open(req, timeout=30) as response:
            status, body_text = response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        status, body_text = exc.code, _read_error_body(exc)
    except URLError as exc:
        return {"status": None, "error": str(exc)}

    result: dict[str, Any] = {"status": status}
    try:
        data = json.loads(body_text).get("data") or {}
    except json.JSONDecodeError:
        data = {}
    result["bearer_fp"] = fp(data.get("bearer"))
    result["refresh_fp"] = fp(data.get("refresh"))
    result["bearer_expires_s"] = data.get("bearerExpiredInSeconds")
    result["refresh_expires_s"] = data.get("refreshExpiredInSeconds")
    result["new_bearer"] = data.get("bearer")
    if result["status"] != 200 or not data.get("bearer"):
        result["body_head"] = body_text[:200]
    return result


def graphql_ok(bearer: str) -> dict[str, Any]:
    payload = json.dumps(
        {
            "query": ACTIVITY_QUERY,
            "variables": {"featureFlags": {"isGiftingStoreEnabled": False}},
        }
    )
    req = Request(
        GRAPHQL_URL,
        data=payload.encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://www.everyday.com.au",
            "Referer": "https://www.everyday.com.au/",
            "User-Agent": "StarBegonia-rewards-probe/1.0",
            "api-version": "2",
            "client_id": CLIENT_ID,
            "Authorization": f"Bearer {bearer}",
        },
    )
    try:
        with _no_redirect.open(req, timeout=30) as response:
            status, body_text = response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        status, body_text = exc.code, _read_error_body(exc)
    except URLError as exc:
        return {"status": None, "error": str(exc)}
    return {"status": status, "has_data": '"data"' in body_text[:200]}


def main() -> int:
    cookie_header = (os.environ.get("WWS_PROBE_AUTH0_COOKIE") or "").strip()
    cookie_file = (os.environ.get("WWS_PROBE_AUTH0_COOKIE_FILE") or "").strip()
    if cookie_file and not cookie_header:
        with open(cookie_file, "r", encoding="utf-8") as handle:
            cookie_header = handle.read().strip()
    if not cookie_header:
        print("缺少 WWS_PROBE_AUTH0_COOKIE / WWS_PROBE_AUTH0_COOKIE_FILE", file=sys.stderr)
        return 2

    auth = silent_authorize(cookie_header)
    report: dict[str, Any] = {"authorize": {k: v for k, v in auth.items() if k != "state"}}

    location = auth.get("location") or ""
    parsed = urlsplit(location)
    query = parse_qs(parsed.query)
    code = (query.get("code") or [None])[0]
    if parsed.path.rstrip("/").endswith("/callback") and code:
        report["authorize"]["got_code"] = True
        exchange = exchange_code(code, auth["state"])
        report["security_token"] = {k: v for k, v in exchange.items() if k != "new_bearer"}
        fresh_bearer = exchange.get("new_bearer")
        if fresh_bearer:
            report["graphql_with_fresh_bearer"] = graphql_ok(fresh_bearer)
    else:
        report["authorize"]["got_code"] = False

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
