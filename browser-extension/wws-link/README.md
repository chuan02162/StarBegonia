# StarBegonia Woolworths extension

This small Manifest V3 extension opens Woolworths and transfers the logged-in
session cookies to a one-time StarBegonia pairing link. Passwords and OTPs are
entered only on Woolworths pages. Cookie values are never displayed or logged.

## Install for development

1. Open `chrome://extensions` in Chrome.
2. Turn on **Developer mode**.
3. Choose **Load unpacked** and select this directory.
4. In StarBegonia, open Account → Woolworths and generate a pairing link.
5. Open the extension, open Woolworths and log in, paste the pairing link, then
   choose **提取并绑定会话**.

The pairing link expires after 10 minutes and can be used once. The extension
asks for Woolworths and StarBegonia host access only when the bind button is
clicked. It reads cookies scoped to the `pastshops` request URL and submits
them to the configured StarBegonia origin over HTTPS. HTTP is accepted only
for localhost development; configure `APP_PUBLIC_URL` with HTTPS before using
the extension against a deployed account.

The extension is pinned to the project deployment origin
`https://1cchome1.duckdns.org` plus localhost development. For another
deployment, update `APP_ORIGIN` in `popup.js` and add that exact origin's host
pattern to `manifest.json` before loading the extension.
