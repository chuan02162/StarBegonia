const WOOLWORTHS_HOME = "https://www.woolworths.com.au/";
const PASTSHOPS_URL = "https://www.woolworths.com.au/api/v3/ui/pastshops";
const WOOLWORTHS_PERMISSION = "https://www.woolworths.com.au/*";
const APP_ORIGIN = "https://1cchome1.duckdns.org";

const pairingInput = document.getElementById("pairing");
const statusEl = document.getElementById("status");
const openButton = document.getElementById("open");
const bindButton = document.getElementById("bind");

function showStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#a12622" : "#53635b";
}

function parsePairingLink(raw) {
  const link = new URL(raw.trim());
  const local = /^(localhost|127\.0\.0\.1)$/.test(link.hostname);
  if (
    (!local && link.origin !== APP_ORIGIN) ||
    (!local && link.protocol !== "https:")
  ) {
    throw new Error("绑定链接不是此扩展允许的 StarBegonia 地址");
  }
  if (link.protocol !== "https:" && !(link.protocol === "http:" && local)) {
    throw new Error("绑定链接必须使用 HTTPS（本机开发可用 localhost）");
  }
  const match = link.hash.match(/^#wws_pair=([A-Za-z0-9_-]+)$/);
  if (!match) throw new Error("绑定链接无效，请在 StarBegonia 重新生成");
  return { origin: link.origin, code: match[1] };
}

openButton.addEventListener("click", async () => {
  await chrome.tabs.create({ url: WOOLWORTHS_HOME });
  showStatus("已打开 Woolworths。登录完成后返回这里继续。");
});

bindButton.addEventListener("click", async () => {
  bindButton.disabled = true;
  try {
    const { origin, code } = parsePairingLink(pairingInput.value);
    const appUrl = new URL(origin);
    const appPermission = `${appUrl.protocol}//${appUrl.host}/*`;
    const granted = await chrome.permissions.request({
      origins: [WOOLWORTHS_PERMISSION, appPermission],
    });
    if (!granted) throw new Error("需要允许 Woolworths 和 StarBegonia 站点权限才能绑定");

    const cookies = await chrome.cookies.getAll({ url: PASTSHOPS_URL });
    if (!cookies.length) throw new Error("没有找到 Woolworths 登录会话，请先登录后重试");

    const payload = {
      code,
      user_agent: navigator.userAgent,
      captured_at: new Date().toISOString(),
      cookies: cookies.map((cookie) => ({
        name: cookie.name,
        value: cookie.value,
        domain: cookie.domain,
        path: cookie.path,
        expires: cookie.expirationDate ?? null,
        http_only: cookie.httpOnly,
        secure: cookie.secure,
        same_site: cookie.sameSite,
      })),
    };

    const response = await fetch(`${origin}/api/v1/sources/wws/claim`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      credentials: "omit",
      cache: "no-store",
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.error || `StarBegonia 请求失败（${response.status}）`);
    }

    pairingInput.value = "";
    showStatus("凭证已加密保存；订单拉取尚未验证。");
  } catch (error) {
    showStatus(
      error instanceof Error ? error.message : "绑定失败，请重新生成绑定链接",
      true,
    );
  } finally {
    bindButton.disabled = false;
  }
});
