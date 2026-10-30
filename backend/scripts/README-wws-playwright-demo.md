# Woolworths Playwright smoke demo

This is an isolated, manual-login demo. It does not automate password entry or
attempt to bypass Woolworths access controls.

From the repository root:

```sh
backend/.venv/bin/pip install -r backend/scripts/requirements-wws-demo.txt
backend/.venv/bin/python backend/scripts/wws_playwright_demo.py
```

The script opens a visible Playwright Chromium window. After manual login, it
requests `pastshops`, opens one in-store receipt, captures the page's product
detail request, encrypts the browser storage state with the project's existing
credential cipher, and attempts to replay the requests in a fresh browser
context. It prints counts and HTTP statuses only.

The encrypted demo credential is written to
`backend/secrets/wws_playwright_demo.enc`, which is git-ignored. The script
stops if login returns Access Denied and does not write a credential in that
case. Remove the encrypted demo file when it is no longer needed.
