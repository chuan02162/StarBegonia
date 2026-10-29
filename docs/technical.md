# StarBegonia 技术文档

对应产品设计见 `docs/design.md`。本文约定实现边界、架构与关键技术决策；Coles 等平台抓取细节由实现方自行填充，此处只保留接入约定。

---

## 1. 后端技术意见（Flask 固定）

在 **Python + Flask 必须** 的前提下，对原 idea 中的配套选型建议如下调整：

| 项 | idea 原案 | 建议 | 原因 |
|----|-----------|------|------|
| 数据库 | SQLite | **PostgreSQL**（云） | 多账号并发、credential 敏感数据、云备份与扩展；SQLite 不适合作为云主库 |
| ORM / 迁移 | SQLAlchemy | SQLAlchemy 2.x + **Alembic** | 与 Flask 搭配成熟；云环境必须有可重复迁移 |
| 认证 | 未写 | **每人账号** + session 或 JWT（见 §5） | 账号仅作身份识别，不做权限矩阵 |
| 异步任务 | 未写 | **RQ 或 Celery** + Redis | 主要用于 **Coles 等源同步**（耗时长、易失败需重试）；批量导入后的分类也可入队，避免拖住 HTTP（见 §4.4） |
| Credential 存储 | 未写 | 应用层加密（如 Fernet）+ 环境主密钥；云上优先 KMS/密钥托管 | 成员挂载各源凭证，云部署风险更高 |
| API 风格 | 未写 | Flask + Blueprint 的 **JSON REST** | 前后端分离清晰；后期 MCP 可复用同一领域服务层 |
| 进程模型 | 未写 | Web（gunicorn/waitress）与 Worker 分进程 | 同步任务与 HTTP 隔离 |
| MCP | fastmcp | 后期独立进程，调用同一 service 层 | 避免与 Web 鉴权混在一个入口 |

**仍建议保留：** Flask、SQLAlchemy、Docker、React + Tailwind + TypeScript、后期 fastmcp。

**不建议前期做：** 微服务拆分、复杂权限/RBAC、多租户 SaaS 隔离（当前是「一个家庭账本 + 多个身份账号」）。

已确认采用：PostgreSQL + Alembic + Redis 任务队列。下文按此书写。

---

## 2. 总体架构

```
[ Web UI (React) ]
        │ HTTPS / JSON
        ▼
[ Flask API ] ──► [ PostgreSQL ]
        │              ▲
        │              │
        ├── 领域服务（账单 / AA / 结算 / 成员 / 分类）
        │         │
        │         └── 读 config/categories.yaml（词表）
        │         └── 调用 TypeSafe Jev API（外部分类服务）
        │
        ├── Source 适配层（Manual / Coles / …）
        │         └── Coles：实现留白
        │
        └── 任务队列 Worker（Redis）
                  └── 源同步（主因）；可选：批量条目再调 Jev
```

- **单一家庭账本**：所有登录成员操作同一套流水与规则；账号只用来标识「谁」以及挂谁的 credential。
- **加人方式：邀请制**（已有成员发出邀请，受邀者注册并绑定 Person）。
- **不做**：按成员过滤可见账单、角色权限、多家庭租户。
- **货币**：默认 **AUD**；金额与账户/账单带 `currency` 字段，汇率与多币种汇总为可扩展点（前期可只支持录入多币种 + 按币种分别汇总）。

---

## 3. 技术栈

| 层 | 选型 |
|----|------|
| 前端 | React、TypeScript、Tailwind CSS、Vite（或同等） |
| 图表 | 轻量图表库（如 Recharts），风格克制，避免仪表盘堆砌 |
| 后端 | Python 3.12+、Flask、Flask-SQLAlchemy（或纯 SQLAlchemy）、Alembic |
| 数据库 | PostgreSQL |
| 队列 / 缓存 | Redis + RQ（或 Celery） |
| 分类智能 | TypeSafe **Jev**（结构化决策；分类为其典型用法） |
| 部署 | Docker / Docker Compose；云主机或容器平台 |
| 后期 | fastmcp（MCP 进程） |

---

## 4. 领域模型（逻辑）

### 4.1 账号与成员

- **User（登录账号）**：邮箱/用户名 + 密码哈希；与 **Person（家庭成员身份）** 一对一或可关联。
- **Person**：展示名、用于 AA 的身份；其上挂载各 **SourceCredential**。
- 登录后请求上下文带当前 `person_id`，用于「谁同步的」「credential 用谁的」，**不**用于限制读写范围。

### 4.2 数据源

- **SourceType**：`manual` | `coles` | …（枚举可扩展）
- **SourceCredential**：`person_id` + `source_type` + 加密后的凭证载荷 + 元数据（上次校验时间等）
- **SourceAdapter**（代码接口，非表）：`pull` / `parse` → 标准化 `Bill` + `Entry[]`  
  - `ManualAdapter`：API 直接创建  
  - `ColesAdapter`：**接口与注册位保留，实现由你填写**

### 4.3 账单

- **Bill**：来源类型、所属/同步所用 person、发生时间、商户/原始标识、币种、外部幂等键、原始载荷引用（可选）、去重状态等  
- **Entry**：隶属 Bill；名称、数量、单价、折扣、小计、币种、分类、标签等  
- 银行类源未来可落为单条 `general`（或同类）Entry

### 4.4 分类与标签（Jev）

- **词表文件：** [`config/categories.yaml`](../config/categories.yaml)  
  可直接编辑；程序读取该文件作为 Category / Tag 候选及 AA 剩余份额名义。不要轻易改已有 `id`（会影响已落库数据）；改 `label` 只影响展示。
- **Jev 跑在哪：** Jev 是 TypeSafe 的**云端 API**，本项目只发 HTTP 请求，**并不把 Jev 装进 Redis/Worker**。  
  Redis 队列的主用途是 **源同步**（登录、拉账单、耗时长）。同步进来一批 Entry 后，再逐条（或批量）调用 Jev 做结构化分类；若在同步的 HTTP 请求里同步打完所有分类，接口容易超时，所以「批量分类」可以跟在同步 Job 后面在 Worker 里做——调的仍是外部 Jev。  
  单笔手动记账：延迟低，也可在 API 进程里**同步调一次 Jev**，不必强制走队列。
- 调用时把词表里的 `categories` / `tags` 固定进 Jev 的结构化输出 schema；模型在候选里做决策并带置信度，不自由发明类目。
- 低置信度进入「待确认」；用户可手工改。

### 4.5 AA 与结算

- **AaRule**：数据源组合（一个或多个 `SourceType`）+ 是否参与 AA + 各 Person 的百分比（**总和可不等于 100%；允许 0%**）
- **比例未满 100%：** 剩余份额归入统一名义（词表中 `aa_residual`，默认 id `family_subsidy` / 展示名「家庭补贴」），对应父母出资等场景；该部分**不进入成员间再分摊**，结算与报表中单独归入该名义。
- **Settlement**：周期、参与人、计算结果（净应付矩阵或配对欠款列表；含「家庭补贴」份额展示）、状态（草稿/已确认/已结清）、结清记录

### 4.6 去重

- 同级：同一源外部幂等键防重复导入  
- 跨源：超市明细 vs 银行扣款等候选匹配（金额、时间窗、商户）；状态：`unmatched` / `suggested` / `linked` / `ignored`  
- 汇总与 AA 默认只计「主记录」，避免双计（主从规则实现时定）

---

## 5. 认证与安全

- 每人一个账号；登录后识别当前 Person。
- **邀请制注册**：已登录成员创建邀请（链接或码）→ 受邀者注册并绑定/创建 Person。不开放公开自助注册进同一账本。
- **无 RBAC**：凡登录成员均可查看/编辑账本、规则、结算、他人 credential 配置入口（产品已定「不管权限」）。若日后要限制改他人凭证，再加细规则。
- 密码：强哈希（如 Argon2/bcrypt）。
- Credential：落库前加密；API 回传前端时脱敏（仅显示「已配置」/末几位等）。
- 云部署：HTTPS 终止、密钥走环境变量或云密钥服务（含 Jev API Key）、数据库不公网暴露。
- 审计（建议）：谁改了 AA 规则、谁触发了同步——轻量操作日志即可。

---

## 6. API 约定（概要）

REST，JSON，版本前缀如 `/api/v1`。

| 域 | 示例职责 |
|----|----------|
| Auth | 注册/登录/登出、当前用户 |
| People | 成员资料；各源 credential 的配置与更新 |
| Bills / Entries | CRUD、筛选、手动创建 |
| Sources | 触发同步、任务状态；Coles 走同一触发入口 |
| Categories / Tags | 词表管理；待确认分类队列；人工确认 |
| Analytics | 按日/周/月/季/年、按来源/分类的汇总 |
| AaRules | 数据源组合与分摊比例 |
| Settlements | 生成、确认、结清、历史 |
| Dedup | 候选列表、确认关联、忽略 |

同步与 Jev 分类返回 **job id**，前端轮询或日后 SSE；前期轮询足够。

领域逻辑放在 service 层，Flask 路由保持薄，便于后期 MCP 复用。

---

## 7. Source 接入约定（含 Coles 留白）

```text
SourceAdapter
  - source_type: str
  - validate_credential(cred) -> bool
  - fetch_raw(cred, cursor) -> RawPayload      # Coles: 你实现
  - parse(raw) -> list[BillDraft]             # Coles: 你实现
  - external_id(bill_draft) -> str            # 幂等
```

- 注册表：`manual`、`coles`、…  
- `coles`：可先提供 `NotImplemented` / stub，测试用假数据；真实抓取不进公共抽象层。  
- Worker：取某 Person 的 Coles credential → `fetch` → `parse` → 幂等写入 → 入队 Jev 分类。

---

## 8. 前端：信息架构与视觉

### 8.1 风格原则（简洁大方）

- **浅色留白**：页面背景近白/浅灰，区块之间用留白分隔，少用重阴影与描边框「卡片堆」
- **主题色：墨绿**（建议 CSS 变量，例如主色约 `#1B4332` / `#2D6A4F` 一带，具体色值实现时定一套 50–900）
- 点缀：墨绿用于主按钮、关键链接、图表主系列；成功/结清态可用同色相浅绿
- 字体：清晰的无衬线正文 + 稍有气质的标题字体（避免 Inter/系统默认堆砌感，也不要用夸张装饰字体）
- **第一屏不做仪表盘墙**：概览页 = 简短周期结余 + 一两个主图表 + 入口，明细进二级页
- 动效：克制（页面切换淡入、数字变更等 2–3 处即可）
- 图表：细线、低饱和辅助色，避免霓虹与厚重渐变

### 8.2 主要界面（与里程碑对齐）

1. 登录  
2. 概览（周期汇总）  
3. 流水 / 账单详情  
4. 手动记账  
5. 数据源同步（含 Coles）与成员 Credential 配置  
6. 分类待确认  
7. AA 规则（按来源组合）  
8. 结算中心  
9. 去重待处理（后期）  

布局：顶栏或侧栏导航保持简单；表单与表格信息密度中等，不挤满。

---

## 9. 部署（云）

- 容器：`web`（前端静态 + nginx 或由 CDN）、`api`、`worker`、`postgres`、`redis`
- 环境变量：数据库 URL、Redis、密钥、Jev API Key、应用密钥等  
- 备份：PostgreSQL 定期快照  
- 前端静态资源与 API 分域名或同域反代均可  

---

## 10. 分期与技术依赖

与 `docs/design.md` 里程碑一致，技术侧补充：

| 阶段 | 技术要点 |
|------|----------|
| M0 | 仓库结构、Docker、Flask 骨架、Postgres、鉴权空壳、Source 注册与 Coles stub |
| M1 | User/Person、手动 Bill/Entry、credential 配置 UI |
| M2 | Coles 适配实现位 + 同步 Job |
| M3 | Jev 对接、词表、待确认流 |
| M4 | 汇总 API + 概览图表 |
| M5–M6 | AaRule、Settlement 计算与 UI |
| M7+ | 去重、更多 Source、OCR、预算、MCP、投资 |

---

## 11. 已确认决策

| 项 | 结论 |
|----|------|
| AA 比例 &lt; 100% | 剩余归入 `aa_residual`（默认「家庭补贴」），见 `config/categories.yaml` |
| 注册 | 邀请制 |
| Jev | 已有 API Key；词表文件可改，程序读文件 |
| Postgres + Redis | 采纳；队列主服务源同步，不是「Jev 跑在 Redis 上」 |

---

## 12. 相关文档

- `docs/idea.md` — 原始设想  
- `docs/design.md` — 产品设计与里程碑  
- `config/categories.yaml` — 分类 / 标签 / AA 剩余名义词表  
- Jev 介绍：[Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
