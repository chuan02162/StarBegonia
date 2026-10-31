# StarBegonia Everyday Rewards extension

A tiny Manifest V3 extension that reads the Everyday Rewards session token from
`localStorage` on `everyday.com.au` and hands it back to the StarBegonia web
app over Chrome's `externally_connectable` messaging. StarBegonia's own
authenticated API stores the token; the extension never talks to the backend
directly and never sees a StarBegonia password or login cookie.

Passwords and one-time codes are entered only on Everyday Rewards pages. The
extension reads only `authStatusData.access_token` and never displays or logs
cookies, passwords, or tokens.

## Install for development

1. Open `chrome://extensions` in Chrome.
2. Turn on **Developer mode**.
3. Choose **Load unpacked** and select this directory.
4. In StarBegonia, open Account → Woolworths and choose **连接 Everyday
   Rewards**. The app opens My Activity in a new tab; log in if asked, then the
   app reads the token through this extension and saves it automatically.

The extension ID is pinned by the `key` field in `manifest.json`, so the web
app can address it directly. `externally_connectable` matches the deployment
origin `https://1cchome1.duckdns.org` plus localhost development; for another
deployment, update both `manifest.json` and the `WWS_EXTENSION_ID` /
`MY_ACTIVITY_URL` constants in `frontend/src/pages/SourceCredentialPage.tsx`.

The Everyday Rewards access token is short-lived. When it expires, repeat the
one-click connect flow; no pairing code is involved.
