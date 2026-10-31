"""Manual-login probe for the Everyday Rewards token lifecycle.

Opens a visible Chromium window, lets the user log in to Everyday Rewards
manually, captures the `/wx/v2/security/token` response (bearer + refresh),
then empirically probes:

  * whether the GraphQL BFF accepts ``api-version`` 1 vs 2,
  * whether the ``refresh`` token can mint a new bearer via ``security/token``,
  * whether the refresh token rotates and can be reused.

Only HTTP statuses, token expiry seconds, and SHA-256 fingerprints are printed.
Token values are never printed, logged, or written to disk.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
import time
from typing import Any

from playwright.async_api import async_playwright

LOGIN_URL = "https://www.everyday.com.au/"
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
      }
      nextPageToken
    }
  }
}
"""


def fp(value: Any) -> str | None:
    """Short fingerprint for identifying a token without exposing it."""
    if value is None or value == "":
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:8]


def make_state() -> str:
    nonce = str(int(time.time() * 1000))
    payload = json.dumps(
        {
            "redirectUri": "https://www.everyday.com.au/index.html#/my-activity",
            "nonce": nonce,
        }
    )
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def summarize_response(status: int, body_text: str) -> dict[str, Any]:
    """Return a compact summary that never includes token material."""
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


async def probe_graphql(context, bearer: str, api_version: str) -> dict[str, Any]:
    payload = json.dumps(
        {"query": ACTIVITY_QUERY, "variables": {"featureFlags": {"isGiftingStoreEnabled": False}}}
    )
    response = await context.request.post(
        GRAPHQL_URL,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://www.everyday.com.au",
            "Referer": "https://www.everyday.com.au/",
            "User-Agent": "StarBegonia-rewards-probe/1.0",
            "api-version": api_version,
            "client_id": CLIENT_ID,
            "Authorization": f"Bearer {bearer}",
        },
        data=payload,
    )
    body_text = await response.text()
    summary = summarize_response(response.status, body_text)
    summary["api-version"] = api_version
    return summary


async def probe_refresh_shape(
    context, payload: dict[str, Any]
) -> dict[str, Any]:
    response = await context.request.post(
        SECURITY_TOKEN_URL,
        headers={
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": "https://www.everyday.com.au",
            "Referer": "https://www.everyday.com.au/",
            "User-Agent": "StarBegonia-rewards-probe/1.0",
            "client_id": CLIENT_ID,
        },
        data=json.dumps(payload),
    )
    body_text = await response.text()
    summary = summarize_response(response.status, body_text)
    summary["shape"] = list(payload.keys())
    return summary


async def main() -> int:
    captured: dict[str, Any] = {}
    observed_graphql_headers: dict[str, Any] = {}

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        async def on_response(response):
            if response.url == SECURITY_TOKEN_URL:
                try:
                    body = json.loads(await response.text())
                except Exception:
                    return
                data = (body or {}).get("data") or {}
                if data.get("bearer"):
                    captured.update(
                        {
                            "bearer": data.get("bearer"),
                            "refresh": data.get("refresh"),
                            "bearer_expires_s": data.get("bearerExpiredInSeconds"),
                            "refresh_expires_s": data.get("refreshExpiredInSeconds"),
                            "state": data.get("state"),
                        }
                    )

        page.on("response", on_response)

        async def on_request(request):
            if request.url == GRAPHQL_URL and request.method == "POST":
                headers = await request.all_headers()
                authorization = headers.get("authorization", "")
                observed_graphql_headers.setdefault("api-version", headers.get("api-version"))
                observed_graphql_headers.setdefault(
                    "authorization_prefix",
                    authorization.split(" ")[0] if authorization else "",
                )
                observed_graphql_headers.setdefault(
                    "authorization_len",
                    len(authorization),
                )
                observed_graphql_headers.setdefault("client_id", headers.get("client_id"))

        page.on("request", on_request)

        print("在打开的 Chrome 窗口中手动登录 Everyday Rewards（含可能的验证码/2FA）；")
        print("不要把密码或验证码发给任何人。登录并打开「我的活动」后会自动继续。")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)

        deadline = asyncio.get_running_loop().time() + 12 * 60
        while asyncio.get_running_loop().time() < deadline and not captured.get("bearer"):
            await asyncio.sleep(2)

        if not captured.get("bearer"):
            print("12 分钟内没有捕获到 Everyday Rewards 会话，未执行探针。")
            await browser.close()
            return 4

        print(
            "已捕获会话: "
            f"bearer_fp={fp(captured['bearer'])}, "
            f"refresh_fp={fp(captured['refresh'])}, "
            f"bearer_expires_s={captured.get('bearer_expires_s')}, "
            f"refresh_expires_s={captured.get('refresh_expires_s')}"
        )

        results: dict[str, Any] = {
            "captured": {
                "bearer_fp": fp(captured["bearer"]),
                "refresh_fp": fp(captured["refresh"]),
                "bearer_expires_s": captured.get("bearer_expires_s"),
                "refresh_expires_s": captured.get("refresh_expires_s"),
            },
            "observed_graphql": observed_graphql_headers,
        }

        results["graphql_v1"] = await probe_graphql(context, captured["bearer"], "1")
        results["graphql_v2"] = await probe_graphql(context, captured["bearer"], "2")

        refresh = captured["refresh"]
        shapes: list[dict[str, Any]] = [
            {"refresh": refresh, "state": make_state(), "redirectUri": CALLBACK},
            {"refresh_token": refresh, "state": make_state(), "redirectUri": CALLBACK},
            {"refresh": refresh},
            {"refresh_token": refresh},
        ]
        refresh_result: dict[str, Any] = {"attempts": []}
        working_shape: dict[str, Any] | None = None
        for shape in shapes:
            summary = await probe_refresh_shape(context, shape)
            refresh_result["attempts"].append(summary)
            if summary.get("bearer_fp"):
                working_shape = shape
                break

        if working_shape:
            first = refresh_result["attempts"][-1]
            refresh_result["rotated"] = first.get("refresh_fp") != fp(refresh)
            # Try to rotate once more with whatever the endpoint returned.
            second_payload = dict(working_shape)
            if "refresh" in second_payload:
                second_payload["refresh"] = first.get("refresh") or refresh
            elif "refresh_token" in second_payload:
                second_payload["refresh_token"] = first.get("refresh") or refresh
            if second_payload.get("state"):
                second_payload["state"] = make_state()
            second = await probe_refresh_shape(context, second_payload)
            refresh_result["second_attempt"] = second
            refresh_result["reusable"] = bool(second.get("bearer_fp"))

        results["refresh"] = refresh_result

        exchange = await context.request.post(
            TOKEN_EXCHANGE_URL,
            headers={
                "Accept": "*/*",
                "Content-Type": "application/json",
                "Origin": "https://www.everyday.com.au",
                "Referer": "https://www.everyday.com.au/",
                "User-Agent": "StarBegonia-rewards-probe/1.0",
                "client_id": CLIENT_ID,
            },
            data=json.dumps({"access_token": captured["bearer"]}),
        )
        results["token_exchange_with_bearer"] = summarize_response(
            exchange.status, await exchange.text()
        )

        print(json.dumps(results, ensure_ascii=False, indent=2))
        await browser.close()
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
