# OpenFeed 银行源（替换 BankSync）

## 1. 在服务器 `.env` 增加（私钥见本机 `backend/secrets/openfeed.env.snippet`，勿提交 git）

```
APP_PUBLIC_URL=http://1cchome1.duckdns.org:5173
OPENFEED_ISSUER=https://auth.openfeed.au
OPENFEED_CLIENT_ID=app-1d75015d-ee9a-4a70-bcb2-c1171efacf9e
OPENFEED_APP_ID=1d75015d-ee9a-4a70-bcb2-c1171efacf9e
OPENFEED_APP_KID=oUwJB8npRTHFW2Tb
OPENFEED_DPOP_KID=um3Ub-PMV_jVYLLo
OPENFEED_APP_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n…\n-----END PRIVATE KEY-----"
OPENFEED_DPOP_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n…\n-----END PRIVATE KEY-----"
```

私钥请从开发机复制 `backend/secrets/openfeed.env.snippet`（该目录已 gitignore）。

然后 `docker compose up -d --build`。

## 2. 注册 App

打开 https://app.openfeed.au/registered-apps/new

| 字段 | 值 |
|---|---|
| Name / Description | StarBegonia / 家庭记账 |
| Auth method | `private_key_jwt` |
| Requested scopes | `openfeed-au:data:banking:read`（必选） |
| **jwksUri** | `http://1cchome1.duckdns.org:5173/api/v1/sources/.well-known/jwks.json` |
| Post-logout redirect | `http://1cchome1.duckdns.org:5173/`（末尾 `/`） |

> OpenFeed 文档要求 **HTTPS** 的 jwksUri。若 HTTP 被拒，改用 **Inline JWKS**，粘贴：

```json
{"keys":[{"kty":"RSA","use":"sig","alg":"PS256","kid":"oUwJB8npRTHFW2Tb","n":"oUwJB8npRTHFW2Tb9E-EWVigrydi51lZ2yxEFPPabJ_50qqIiFfDx37FMlCNc17jMeR0Ta4LyYpmEGeXKNKYOak_FBD6H3vWcDpzeHXDcs-FIf78EewhuR-z0TxeZFJGEJ--qkE6kBrXGswCJUyyWKbjY8GnSuimkZ3HT-F1Tb3ta8ik9SrJRyaGBE8f1pj49IXhrdTtPe7efRIMvmqekedQ3pjBvpPZsO9HDLPP7tL9X7jSh9Z5X3K4L7WKOE2ealCjiHpYkn6n2N5YPKLFNpw31Hvj7jnARjwZl0pyKywlGbHpDCX6OXCaOCtFCPluZP4nRbDq5rwmh0BKHtgS6Q","e":"AQAB"}]}
```

上 HTTPS 后可把 jwksUri 改成同一路径的 `https://…`。

提交后把两个 ID 发回 / 填进 `.env`：
- `oauth2ClientId` → `OPENFEED_CLIENT_ID`
- `id`（UUID）→ `OPENFEED_APP_ID`

## 3. 使用

1. 打开站点 → 账户 → **OpenFeed 银行** → **连接 OpenFeed**
2. 登录 OpenFeed → 勾选要分享的银行账户
3. 回到站点后点 **同步账单**

旧 BankSync / `commbank` 流水仍保留在库里，新同步写入 `openfeed`。
