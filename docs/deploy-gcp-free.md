# 部署到 Google Cloud 免费层（e2-micro）

目标机型：`e2-micro` · `us-west1-a` · Ubuntu 24.04 · 30 GB pd-standard · 临时外网 IP。

Always Free 大约提供：1× e2-micro、30 GB 标准盘、1 GB/月出站流量。本方案按 **1 GiB 内存** 瘦身，串行夜间同步，避免同步高峰 OOM。

## 1. 部署前安全检查（必做）

| 项 | 风险 | 要求 |
|----|------|------|
| `SECRET_KEY` / `JWT_SECRET_KEY` | 伪造登录 | 随机长串，禁止示例值 |
| `CREDENTIAL_FERNET_KEY` | Coles/银行凭证可读 | Fernet key；生产禁止空（勿依赖 SECRET_KEY 派生） |
| `POSTGRES_PASSWORD` | 库被扫 | 强密码；**不要**把 5432 暴露到公网 |
| `CORS_ORIGINS` | 跨站滥用 API | 设为 `http://YOUR_IP` 或日后的 `https://域名`，禁止 `*` |
| `STARBEGONIA_ENV=production` | 弱配置上线 | free compose 已设；弱密钥会直接拒绝启动 |
| Redis / Postgres 端口 | 公网入侵 | free compose **不映射** 6379/5432 |
| 防火墙 | 横向扫描 | 只放行 **22**（或 IAP）与 **80**（或 443） |
| `.env` | 密钥泄漏 | 已在 `.gitignore`；勿提交、勿打进镜像 |
| Bootstrap | 首个账号开放注册 | 上线后立刻完成 bootstrap；之后接口会关闭 |
| JWT 7 天 | 失窃窗口长 | 家庭自用可接受；可把 `JWT_ACCESS_TOKEN_EXPIRES` 调短 |
| 出站 1 GB/月 | 超额计费 | 依赖增量同步；少开全量 `full_sync` |
| HTTPS | 中间人 | 免费层先 HTTP+强密码可过渡；有域名后上 Caddy/Let’s Encrypt |

生成密钥示例：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 2. VM 准备（稳定跑满 1 GiB 的关键）

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER   # 重新登录生效

# 交换分区：e2-micro 强烈建议
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo sysctl vm.swappiness=10
```

防火墙（示例 ufw）：

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw enable
```

## 3. 应用部署

```bash
git clone <your-repo> StarBegonia && cd StarBegonia
cp .env.example .env
nano .env   # 填齐下方生产项
```

`.env` 至少包含：

```env
STARBEGONIA_ENV=production
SECRET_KEY=...
JWT_SECRET_KEY=...
CREDENTIAL_FERNET_KEY=...
POSTGRES_PASSWORD=...
CORS_ORIGINS=http://YOUR_EXTERNAL_IP
JEV_API_KEY=...
BANKSYNC_API_KEY=...
DEFAULT_CURRENCY=AUD
```

启动（只用 free compose，不要用开发版把 DB 端口打出去）：

```bash
docker compose -f docker-compose.free.yml --env-file .env up -d --build
docker compose -f docker-compose.free.yml ps
curl -s http://127.0.0.1/health
```

浏览器打开 `http://YOUR_EXTERNAL_IP` → 完成 bootstrap → 配置 Coles / CommBank。

## 4. 夜间同步行为

- Worker 内置调度：默认 **Australia/Sydney 00:00**
- 按 `source_type, person_id` **串行**拉 Coles → CommBank…，默认间隔 **60s**（`DAILY_SYNC_GAP_SECONDS`）
- 使用现有增量水位，避免每晚全量
- API 容器关闭调度（`DAILY_SYNC_ENABLED=0`），避免双跑

手动立刻跑一轮：

```bash
docker compose -f docker-compose.free.yml exec -T worker \
  python -m app.jobs.daily_sync
```

## 5. 资源预算（约）

| 服务 | mem_limit |
|------|-----------|
| postgres | 192m |
| redis | 48m |
| api | 220m |
| worker | 220m |
| web | 32m |
| **合计上限** | **~712m** + OS/Docker |

尖峰靠 **2G swap** 缓冲。若仍 OOM：把 `DAILY_SYNC_GAP_SECONDS` 提到 90–120，或暂时关掉 RQ 异步、只保留夜间串行。

## 6. 运维

```bash
docker compose -f docker-compose.free.yml logs -f worker
docker compose -f docker-compose.free.yml restart worker
```

备份 Postgres：

```bash
docker compose -f docker-compose.free.yml exec -T postgres \
  pg_dump -U starbegonia starbegonia | gzip > backup-$(date +%F).sql.gz
```

## 7. 已知限制

- e2-micro CPU 共享，同步窗口会慢，属预期
- 无 HTTPS 时浏览器会警告；家庭自用可先接受，有域名再上证书
- 免费出站额度紧：图片 URL 走 CDN 外链即可，勿在本机缓存大图
- 若要更稳，升级 **e2-small（2 GiB）** 比继续硬挤 micro 更省心
