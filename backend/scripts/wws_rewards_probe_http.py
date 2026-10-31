"""Headless probe for the Everyday Rewards token lifecycle.

Unlike ``wws_rewards_probe.py`` this script does not open a browser and does not
require a login. It reads a freshly captured bearer + refresh token from the
environment and probes the same endpoints:

    WWS_PROBE_BEARER   -> Everyday Rewards access token (authStatusData.access_token)
    WWS_PROBE_REFRESH  -> Everyday Rewards refresh token (authStatusData.refresh_token)

Only HTTP statuses, token expiry seconds, and SHA-256 fingerprints are printed.
Token values are never printed or persisted.
"""

from __future__ import annotations

import hashlib
import base64
import json
import os
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SECURITY_TOKEN_URL = "https://api.everyday.com.au/wx/v2/security/token"
TOKEN_EXCHANGE_URL = "https://api.everyday.com.au/wx/v1/rewardspartner/secure/token-exchange"
GRAPHQL_URL = "https://apigee-prod.api-wr.com/wx/v1/bff/graphql"
CLIENT_ID = "8h41mMOiDULmlLT28xKSv5ITpp3XBRvH"
CALLBACK = "https://www.everyday.com.au/callback"

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


def make_state() -> str:
    payload = json.dumps(
        {
            "redirectUri": "https://www.everyday.com.au/index.html#/my-activity",
            "nonce": str(int(time.time() * 1000)),
        }
    )
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def _post(url: str, headers: dict[str, str], payload: dict[str, Any]) -> tuple[int | None, str]:
    req = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers=headers)
    try:
        with urlopen(req, timeout=30) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except URLError as exc:
        return None, f"network error: {exc}"


def summarize(status: int | None, body_text: str) -> dict[str, Any]:
    summary: dict[str, Any] = {"status": status}
    try:
        body = json.loads(body_text)
    except json.JSONDecodeError:
        summary["body_len"] = len(body_text)
        summary["body_head"] = body_text[:200]
        return summary

    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, dict):
        summary["bearer_fp"] = fp(data.get("bearer"))
        summary["refresh_fp"] = fp(data.get("refresh"))
        summary["bearer_expires_s"] = data.get("bearerExpiredInSeconds")
        summary["refresh_expires_s"] = data.get("refreshExpiredInSeconds")
        summary["twoFAVerified"] = data.get("twoFAVerified")
    errors = body.get("errors") if isinstance(body, dict) else None
    if errors:
        summary["errors"] = [
            {
                "message": str(e.get("message"))[:160],
                "code": e.get("code"),
            }
            for e in errors
            if isinstance(e, dict)
        ][:3]
    summary["body_head"] = body_text[:200]
    return summary


def graphql_probe(bearer: str, api_version: str) -> dict[str, Any]:
    status, body_text = _post(
        GRAPHQL_URL,
        {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://www.everyday.com.au",
            "Referer": "https://www.everyday.com.au/",
            "User-Agent": "StarBegonia-rewards-probe/1.0",
            "api-version": api_version,
            "client_id": CLIENT_ID,
            "Authorization": f"Bearer {bearer}",
        },
        {
            "query": ACTIVITY_QUERY,
            "variables": {"featureFlags": {"isGiftingStoreEnabled": False}},
        },
    )
    result = summarize(status, body_text)
    result["api-version"] = api_version
    return result


def refresh_probe(payload: dict[str, Any]) -> tuple[dict[str, Any], str | None, str | None]:
    status, body_text = _post(
        SECURITY_TOKEN_URL,
        {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://www.everyday.com.au",
            "Referer": "https://www.everyday.com.au/",
            "User-Agent": "StarBegonia-rewards-probe/1.0",
            "client_id": CLIENT_ID,
        },
        payload,
    )
    result = summarize(status, body_text)
    result["shape"] = list(payload.keys())
    bearer, refresh = extract_tokens(body_text)
    return result, bearer, refresh


def extract_tokens(body_text: str) -> tuple[str | None, str | None]:
    try:
        body = json.loads(body_text)
    except json.JSONDecodeError:
        return None, None
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None, None
    return data.get("bearer"), data.get("refresh")


def main() -> int:
    bearer = (os.environ.get("WWS_PROBE_BEARER") or "").strip()
    refresh = (os.environ.get("WWS_PROBE_REFRESH") or "").strip()
    state = (os.environ.get("WWS_PROBE_STATE") or "").strip()
    if not bearer or not refresh:
        print("缺少 WWS_PROBE_BEARER / WWS_PROBE_REFRESH 环境变量", file=sys.stderr)
        return 2

    results: dict[str, Any] = {
        "captured": {
            "bearer_fp": fp(bearer),
            "refresh_fp": fp(refresh),
        },
    }

    results["graphql_v1"] = graphql_probe(bearer, "1")
    results["graphql_v2"] = graphql_probe(bearer, "2")

    shapes: list[dict[str, Any]] = [
        {"refresh": refresh},
        {"refresh_token": refresh},
        {"refresh": refresh, "state": make_state(), "redirectUri": CALLBACK},
        {"refresh_token": refresh, "state": make_state(), "redirectUri": CALLBACK},
    ]
    if state:
        shapes.extend(
            [
                {"refresh": refresh, "state": state, "redirectUri": CALLBACK},
                {"refresh_token": refresh, "state": state, "redirectUri": CALLBACK},
                {"refresh": refresh, "state": state},
            ]
        )
    refresh_result: dict[str, Any] = {"attempts": []}
    working_shape: dict[str, Any] | None = None
    new_refresh: str | None = None
    for shape in shapes:
        attempt, _new_bearer, _new_refresh = refresh_probe(shape)
        refresh_result["attempts"].append(attempt)
        if attempt.get("status") == 200 and attempt.get("bearer_fp"):
            working_shape = shape
            new_refresh = _new_refresh
            break

    if working_shape is not None:
        first = refresh_result["attempts"][-1]
        refresh_result["rotated"] = fp(new_refresh) != fp(refresh)
        second_payload = dict(working_shape)
        if "refresh" in second_payload:
            second_payload["refresh"] = new_refresh or refresh
        elif "refresh_token" in second_payload:
            second_payload["refresh_token"] = new_refresh or refresh
        if second_payload.get("state"):
            second_payload["state"] = make_state()
        second, _, _ = refresh_probe(second_payload)
        refresh_result["second_attempt"] = second
        refresh_result["reusable"] = second.get("status") == 200 and bool(second.get("bearer_fp"))

    results["refresh"] = refresh_result

    status, body_text = _post(
        TOKEN_EXCHANGE_URL,
        {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://www.everyday.com.au",
            "Referer": "https://www.everyday.com.au/",
            "User-Agent": "StarBegonia-rewards-probe/1.0",
            "client_id": CLIENT_ID,
        },
        {"access_token": bearer},
    )
    results["token_exchange_with_bearer"] = summarize(status, body_text)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
