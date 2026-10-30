"""Manual-login Playwright smoke test for Woolworths Past Shops.

Credentials are never printed. A successful browser storage state is encrypted
with the project's credential cipher and written under backend/secrets/.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from playwright.async_api import async_playwright

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(REPO_ROOT / ".env")

from app import create_app  # noqa: E402
from app.security.crypto import decrypt_payload, encrypt_payload  # noqa: E402

LOGIN_URL = "https://auth.woolworths.com.au/u/login"
PASTSHOPS_URL = "https://www.woolworths.com.au/api/v3/ui/pastshops"
PASTSHOPS_PAGE = "https://www.woolworths.com.au/shop/mylists/pastshops"
DETAIL_PATH = re.compile(r"/api/v3/ui/pastshops/[^/]+/products(?:\?|$)")
STATE_FILE = BACKEND_ROOT / "secrets" / "wws_playwright_demo.enc"


def chrome_path() -> str | None:
    # Prefer Playwright's bundled Chromium. A custom path is opt-in for users
    # who want to test their installed Chrome build.
    configured = os.environ.get("WWS_CHROME_PATH")
    return str(configured) if configured and Path(configured).is_file() else None


def encrypt_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    app = create_app()
    configured_fernet = (app.config.get("CREDENTIAL_FERNET_KEY") or "").strip()
    weak_secrets = {"", "dev-secret-change-me", "change-me-in-production", "change-me-jwt"}
    if not configured_fernet and app.config.get("SECRET_KEY") in weak_secrets:
        raise RuntimeError("Configure a strong SECRET_KEY or CREDENTIAL_FERNET_KEY in .env first.")
    with app.app_context():
        encrypted = encrypt_payload(
            {
                "provider": "wws",
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "storage_state": state,
            }
        )
    fd = os.open(STATE_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(encrypted)


def decrypt_state() -> dict[str, Any]:
    app = create_app()
    with app.app_context():
        payload = decrypt_payload(STATE_FILE.read_text(encoding="utf-8"))
    return payload["storage_state"]


def product_count(value: Any) -> int:
    counts: list[int] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if key.lower() in {"products", "items", "results", "basketproducts"} and isinstance(child, list):
                    counts.append(len(child))
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return max(counts, default=len(value) if isinstance(value, list) else 0)


async def main() -> int:
    async with async_playwright() as playwright:
        launch_options: dict[str, Any] = {"headless": False}
        executable = chrome_path()
        if executable:
            launch_options["executable_path"] = executable
        browser = await playwright.chromium.launch(**launch_options)
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60_000)
        print("在打开的 Chrome 窗口中手动完成 Woolworths 登录；不要把密码或验证码发给我。")

        deadline = asyncio.get_running_loop().time() + 8 * 60
        logged_in = False
        while asyncio.get_running_loop().time() < deadline:
            current_url = page.url
            try:
                body = (await page.locator("body").inner_text(timeout=1500)).lower()
            except Exception:
                body = ""
            if "access denied" in body:
                print("登录页返回 Access Denied；停止测试，不尝试绕过站点拦截。")
                await browser.close()
                return 3
            if current_url.startswith("https://www.woolworths.com.au/") and "/auth/callback" not in current_url:
                logged_in = True
                break
            await asyncio.sleep(2)

        if not logged_in:
            print("8 分钟内没有完成登录，未保存凭证。")
            await browser.close()
            return 4

        list_response = await context.request.get(
            PASTSHOPS_URL,
            headers={
                "accept": "application/json, text/plain, */*",
                "origin": "https://www.woolworths.com.au",
                "referer": PASTSHOPS_PAGE,
            },
            timeout=30_000,
        )
        if list_response.status != 200:
            print(f"pastshops 请求失败：HTTP {list_response.status}；未保存凭证。")
            await browser.close()
            return 5
        listing = await list_response.json()
        history = listing.get("History") or []
        in_store = [shop for shop in history if str(shop.get("Channel", "")).lower() == "instore"]
        if not in_store:
            print(f"pastshops 成功，但没有找到线下记录（记录数 {len(history)}）。")
            await browser.close()
            return 6

        shop = in_store[0]
        basket_id = str(shop.get("BasketId") or "")
        if not basket_id:
            print("pastshops 返回记录缺少 BasketId。")
            await browser.close()
            return 7

        detail_response = None
        try:
            async with page.expect_response(
                lambda response: DETAIL_PATH.search(response.url) is not None
                and response.request.method.upper() == "POST",
                timeout=45_000,
            ) as response_info:
                await page.goto(
                    f"{PASTSHOPS_PAGE}/{basket_id}?pageNumber=1",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
            detail_response = await response_info.value
        except Exception:
            print("Past Shops 页面未触发已知的商品详情 POST 请求。")
            await browser.close()
            return 8

        detail_request = detail_response.request
        try:
            detail_body = detail_request.post_data_json
        except Exception:
            detail_body = json.loads(detail_request.post_data or "{}")
        if detail_response.status != 200:
            print(f"商品详情请求失败：HTTP {detail_response.status}。")
            await browser.close()
            return 9
        detail_json = await detail_response.json()
        details_count = product_count(detail_json)

        state = await context.storage_state()
        state["cookies"] = [
            cookie for cookie in state.get("cookies", [])
            if "woolworths.com.au" in cookie.get("domain", "")
        ]
        state["origins"] = [
            origin for origin in state.get("origins", [])
            if "woolworths.com.au" in origin.get("origin", "")
        ]
        encrypt_state(state)

        # Verify the encrypted credential can be decrypted and reused in a new
        # browser context, then replay the exact detail request body.
        saved_state = decrypt_state()
        replay_context = await browser.new_context(storage_state=saved_state)
        replay_list = await replay_context.request.get(
            PASTSHOPS_URL,
            headers={
                "accept": "application/json, text/plain, */*",
                "origin": "https://www.woolworths.com.au",
                "referer": PASTSHOPS_PAGE,
            },
            timeout=30_000,
        )
        replay_detail = None
        if replay_list.status == 200:
            original_headers = await detail_request.all_headers()
            replay_headers = {
                key: value
                for key, value in original_headers.items()
                if key.lower() not in {
                    "cookie", "host", "content-length", "connection",
                    "accept-encoding", "authorization",
                }
            }
            replay_detail = await replay_context.request.post(
                detail_request.url,
                data=detail_body,
                headers=replay_headers,
                timeout=30_000,
            )

        print(
            "Smoke test result: "
            f"pastshops_http={list_response.status}, "
            f"shops={len(history)}, in_store={len(in_store)}, "
            f"detail_http={detail_response.status}, detail_products={details_count}, "
            f"credential_saved=true, replay_list_http={replay_list.status}, "
            f"replay_detail_http={replay_detail.status if replay_detail else 'skipped'}, "
            f"credential_file={STATE_FILE}"
        )
        await replay_context.close()
        await browser.close()
        return 0 if replay_list.status == 200 and replay_detail and replay_detail.status == 200 else 10


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
