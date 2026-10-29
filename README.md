# StarBegonia

家庭收支与 AA 分摊。当前完成 **M0–M3**：骨架、手动记账、Coles 同步、Jev 分类与待确认。

设计见 `docs/design.md`，技术约定见 `docs/technical.md`。

## 快速开始

```bash
cp .env.example .env   # 如已有 .env 可跳过
docker compose up --build
```

- Web: http://localhost:5173  
- API: http://localhost:5001/health（容器内仍为 5000）  

首次打开会进入「创建家庭账本」。之后可在「邀请」生成码，家人用 `/register` 加入。

## 本地开发（可选）

**后端**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# 需本机 Postgres，或改 DATABASE_URL
export DATABASE_URL=postgresql+psycopg2://starbegonia:starbegonia@localhost:5432/starbegonia
export CATEGORIES_PATH=../config/categories.yaml
alembic upgrade head
flask --app wsgi:app run -p 5001
```

**前端**

```bash
cd frontend
npm install
npm run dev
```

Vite 已将 `/api` 代理到 `localhost:5001`。

## 架构（简）

```
frontend/          React + Tailwind
backend/app/
  api/             薄路由
  services/        领域逻辑
  models/
  sources/         SourceAdapter（manual + coles stub）
config/categories.yaml   分类词表（可改）
```

Coles 实现：`backend/app/sources/coles.py`（BFF auth + orders + detail）。

## 已包含（M0–M3）

- Docker：postgres / redis / api / worker / web  
- 鉴权：bootstrap → 邀请注册 → JWT  
- 手动 Bill / Entry CRUD  
- 成员页：粘贴 `refreshToken`（可选 user_id）并 **同步 Coles**  
- Coles：`GET /api/bff/auth` 续期 → 列表 → `GET /api/bff/orders/{id}` + `x-transaction-id`  
- Jev：词表 `config/categories.yaml` → 结构化分类；低置信度进「分类」待确认；流水可按分类筛选  
- CommBank：经 [BankSync](https://banksync.io/docs)（`X-API-Key` / `banks:read`）拉取流水，每笔为单条 `general` entry  

`.env` 中配置 `JEV_API_KEY`、`BANKSYNC_API_KEY`（勿提交真实 key）。在 BankSync 先连接 CommBank，再在账户页启用同步。

Worker 默认在 **Australia/Sydney 00:00** 串行增量同步所有已配置源（间隔见 `DAILY_SYNC_GAP_SECONDS`）。

Google Cloud 免费层部署见 [`docs/deploy-gcp-free.md`](docs/deploy-gcp-free.md)（使用 `docker-compose.free.yml`）。
