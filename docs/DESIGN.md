# 内网知识库：设计与实现对照

> 本文是**现在该怎么做**的操作说明，比 PRD 更贴代码。PRD 仍是范围合同；本文解决「界面分区、模型放哪、权限怎么算、预览怎么做」。
> 日期：2026-08-31（知识库一等公民重构后重写；2026-08-21 的 Bun/Zero 快照已作废）

---

## 1. 产品是什么

内网员工把资料放进**知识库**：自己创建（成为 owner）或通过分享链接加入（成为 editor/viewer）。库内上传后自动解析，可以**基于库内资料提问并带引用**。同一套库通过 **MCP 连接器**（OAuth 2.1 + PKCE 的 service principal）给公司其他 agent 用。

不是：ChatGPT 壳、Notion、IM、公网 SaaS、MCP 插件市场。

一句话心智：**知识库是骨架，成员角色是唯一授权依据，文件是血肉，提问是入口，模型只走平台治理的内网网关。**

---

## 2. 人看见的功能分区（当前锁定）

新手路径：**创建/加入知识库 → 上传文件 → 自动解析 → 提问**。
对话**不进资料树**（避免和文件抢位置）。

```
┌─────────────┬──────────────────────────────────────────┐
│ 知识库切换    │ 当前文件夹标题                              │
│ (我的全部库)  │ 工具栏：新建文件夹 / 新建笔记 / 上传文件      │
│ 新建/加入库   │ 文件列表（解析状态：解析中 / 已可提问 / 失败）  │
│             │ 点文件 → 预览 + 提取文本 + 元信息             │
│ 提问 (/)     │ 点提问 → 预置当前文档范围                    │
│ 知识库 (/kb) │ 管理面板：成员角色 / 分享链接                 │
│ 历史         │                                            │
│ 连接器       │                                            │
│ 设置         │                                            │
└─────────────┴──────────────────────────────────────────┘
```

| 分区 | 路由 | 谁用 | 里面有什么 |
|---|---|---|---|
| 提问 | `/`、`/ask/:conversationId` | 所有成员 | 组合器 + 引用面板；范围默认「全库」，可收窄到文件夹/文档 |
| 知识库 | `/kb` | 所有成员 | 三栏：目录树、文件列表、预览；`?folderId=` `?doc=` 深链 |
| 历史 | `/history` | 所有成员 | 跨库对话列表（每行带所属库名），打开/重命名/归档/删除/重试 |
| 连接器 | `/connectors` | 登录用户 | 用户级 OAuth 连接器与 service principal（scope 勾选，不含 ask） |
| 设置 | `/settings` | 登录用户 | 单页：个人资料、密码、TOTP、恢复码、会话吊销 |
| 加入库 | `/join/:token` | 拿到分享链接的人 | 展示库名与拟授予角色，确认后入成员表 |
| 授权页 | `/oauth/consent` | MCP 客户端用户 | 仅勾选 scope；不选库、不选文件夹 |
| 平台后台 | Admin 应用（独立部署，生产 8081 / 本地 9015） | `super_admin` / `platform_admin` / `security_auditor` | 用户、知识库登记、审计、模型治理 |

没有会员（无成员记录）时 `/kb` 渲染 onboarding：创建或凭分享链接加入。
标签（tags）、回收站、文件夹 ACL、邀请制群组已全部删除：删除是服务端依赖检查把关的硬删除。

---

## 3. 模型到底放在哪（只有平台一层）

模型**不是**资料树上的一种文件，也**不再**放在库里让人配置。

```
① 平台后台 Admin（唯一配置面）
     网关（baseURL + 一次性密钥）→ 受管模型 → 能力 Profile
     五个固定工作流：grounded_ask / title_generation / summarization / embedding / reranking
        ↓ 发布不可变版本
② 按知识库指派（Admin → 知识库 → profile-assignments）
     PUT /api/v1/admin/knowledge-bases/{kbId}/profile-assignments/{workflow}
     精确版本；未指派 = 409 NO_ASSIGNMENT，终止，不回退
③ 成员只读投影
     GET /api/v1/knowledge-bases/{kbId}/capabilities
     只见业务别名 / 版本 / 状态 / 非机密原因
```

| 配置项 | 放哪 | 干什么 |
|---|---|---|
| 内网网关 URL / Key | Admin → 网关 | 所有 LLM 出站只打这里（受 `IMA_MODEL_ALLOWED_HOSTS/CIDRS` 约束） |
| 聊天 / 嵌入 / 重排模型 | Admin → 受管模型 | 挂到能力 Profile 的对应工作流 |
| 某库用哪个版本 | Admin → 按库指派 | 精确版本；改动触发 `REINDEX_REQUIRED` 等依赖检查 |
| 本次提问用哪个模型 | **没有** | 提问页没有模型选择器；Python 按库的指派执行 |

网关密钥是 write-only 输入：成功/取消/出错/离开即清空，永不回显。审计员只见安全元数据。

---

## 4. 架构（数据怎么走）

### 4.1 运行时

```
浏览器 Vue/Quasar（PWA 前端 :9016 / Admin SPA :9015，生产经 Caddy :8080/:8081）
    │  /api、/mcp、/oauth 代理
    ▼
Python FastAPI（唯一后端）   Postgres（zhparser + vector）   MinIO   Procrastinate worker
  鉴权/库与成员/入库/检索/问答/治理   业务库                    文件     解析-切片-向量-清理
  MCP `/mcp`：官方 Python SDK（mcp==2.1.1）Streamable HTTP
    │
    ▼
内网 LLM 网关（OpenAI 兼容）  ← 守卫式出站：禁公网备援、禁重定向、DNS 预解析
```

连接器页不再签发长驻 Key：MCP 客户端走 OAuth 2.1 + PKCE；service principal 是**用户级**的，由用户自助创建/吊销，scope 不含 `mcp:knowledge:ask`（ask 仅限真人）。`/api/mcp` 已在边缘 `410 Gone`，`/api/v1/internal/*` 恒 `404`。

### 4.2 入库

```
本地算 SHA-256 → 上传票据（绑定文件夹/文档、尺寸、MIME、过期）
             → 直传 S3（Content-Type + x-amz-checksum-sha256）
             → 完成回调：提供方 HEAD 校验校验和/尺寸/MIME 后才推进版本
             → Procrastinate：parse → chunk → embed → cleanup（逐级持久化、幂等、可重试）
             → 状态 ready / unparsed / failed
```

支持解析：text、Markdown、JSON、PDF 文本、DOCX、XLSX。解析与预览分开：预览看原文件（`/file/preview`、`/file/download` 先授权后出 URL），提问看 chunk/文本。替换上传带双版本号，冲突保留现行版本。

### 4.3 提问

```
用户问题 → GET  /api/v1/knowledge-bases/{kbId}/search
        → 关键词(zhparser) + 向量(HNSW) 混合，按成员角色过滤，可选 rerank
        → POST /api/v1/knowledge-bases/{kbId}/ask（SSE）
        → 事件序：conversation/message → citations → delta → completed|knowledge_gap|cancelled|error
        → 无命中固定 knowledge_gap，不调模型、不编造
```

对话存 `ima.conversations`（外键落在 `ima.kb_members` 复合键上，成员被移除即失去访问）；`GET /api/v1/conversations` 是用户级跨库列表，每行带 `kbId`/`kbName`。

### 4.4 权限（成员角色是唯一投票）

`ima.kb_members` 三种角色：`owner` / `editor` / `viewer`。

| 动作 | owner | editor | viewer |
|---|---|---|---|
| 看目录/列表/预览/下载 | ✅ | ✅ | ✅ |
| 搜索 / 提问 | ✅ | ✅ | ✅ |
| 建子文件夹/笔记、上传、移动、重命名、编辑 | ✅ | ✅ | ❌ |
| 删除 | ✅ | ✅ | ❌ |
| 成员管理 / 分享链接 / 归档库 | ✅ | ❌ | ❌ |

没有文件夹 ACL、没有群组：文档/文件夹权限完全由所在库的成员角色推导。
分享链接：仅授 `editor`/`viewer`，token 加盐加 pepper 只存摘要，创建时一次性返回 `{origin}/join/{token}`，可设 1–365 天有效期并可吊销；接受是幂等的，且**从不降级**已有成员。
owner 保护：最后一个 owner 不能离开/降级；转让须先提权再移除。
MCP 每次工具调用都重新检查：scope → 用户级授权 → 目标库成员关系 → 角色门槛（写工具要求 editor+）；授权失败映射成带错误码的 `ToolError`。

---

## 5. 开源对标（预览 / 知识库）

不要自己用 mammoth HTML + markdown 表格硬画 Office。

| 需求 | 开源实现 | 怎么用 |
|---|---|---|
| Word/Excel/PDF 浏览器预览 | [vue-office](https://github.com/501351981/vue-office) | `@vue-office/docx` `excel` `pdf`；纯前端，不经公网转换服务 |
| PDF 内核 | pdf.js（vue-office 已包一层） | worker 用仓库内 `public/pdf.worker.min.mjs`，禁止 unpkg |
| 知识库产品形态 | IMA / Dify Dataset / Nextcloud+RAG | 学「目录+解析+问」，不学广场和联网搜 |
| 检索配置 | [Dify](https://github.com/langgenius/dify) dataset retrieval | 混合检索、top_k、分数阈值、混合权重、先权限后 rerank |
| MCP 传输 | 官方 Python SDK（`mcp==2.1.1`） | `/mcp` Streamable HTTP + OAuth 2.1 PKCE；传输安全设置校验 Origin/宿主 |
| 服务端 RAG | 自研薄管道（已有） | 不引入 LlamaIndex 类框架 |

PPTX：vue-office 的 pptx 内核不完全开源。对 pptx **下载 + 抽文本提问**，不做幻灯片级预览。

---

## 6. 该删 / 已删

知识库一等公民重构删除并禁止复活：

| 项 | 状态 |
|---|---|
| 「工作区」概念、邀请、群组、文件夹 ACL | 删除；授权只剩库成员角色 |
| 标签、回收站 | 删除；删除即硬删除（依赖检查把关） |
| Bun/Zero 运行时、`/api/mcp`、内部桥 | 删除；`/api/mcp` 边缘 410，`/api/v1/internal/*` 恒 404 |
| 遗留 `public.*` 37 表与 `migrate-legacy-*` CLI | 删除（迁移 `20260829_0011`）；检查点历史表留档 |
| 长驻 MCP Key、浏览器端模型选择器 | 删除；换 OAuth 2.1 + PKCE 与平台治理 |

---

## 7. 验收（按这个测）

1. 登录 → 无库时 `/kb` 出现 onboarding；创建库后自动成为 owner 并切换。
2. `/join/:token`：有效链接显示库名与角色，接受后出现在切换器；重复接受幂等；失效/过期链接给明确错误。
3. 上传 pdf/docx/xlsx → 预览像文档而不是一坨 HTML；状态变为已可提问。
4. 提问：引用先于正文出现；无命中显示「知识库未收录」；取消/重试状态正确。
5. 成员面板：owner 可将 editor↔viewer 互改，不能直接降级/移除最后一个 owner。
6. viewer 只读：无新建/上传/删除控件；越权 API 返回 403 且前端无假成功。
7. 连接器：创建 service principal（scope 不含 ask）；`initialize` + `tools/list` 成功；写工具在 viewer 库上被逐调用拒绝。
8. Admin：配置网关/模型/Profile 并按库指派；成员页只见业务投影；审计员全只读。
9. `bun run test:unit`、`bun run test:e2e`、后端 `uv run pytest` 全绿，零跳过。
