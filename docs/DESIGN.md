# 内网知识库：设计与实现对照

> 本文是**现在该怎么做**的操作说明，比 PRD 更贴代码。PRD 仍是范围合同；本文解决「界面分区、模型放哪、什么该删、预览怎么做」。  
> 日期：2026-08-21

> **历史快照（2026-08-21）**：本文记录切换前的设计（Bun/Hono 服务、Zero 缓存、`/api/mcp`）。legacy 删除发布已移除该运行时：Python 是唯一后端，MCP 规范入口为 `/mcp`。本文保留为设计史证据，不再描述当前架构。

---

## 1. 产品是什么

内网员工把资料放进**一个网盘式目录**，上传后自动解析，可以**基于库内资料提问并带引用**。同一套库以后通过 **MCP 连接器**给公司其他 agent 用。

不是：ChatGPT 壳、Notion、IM、公网 SaaS、MCP 插件市场。

一句话心智：**目录是骨架，文件是血肉，提问是入口，模型只走内网网关。**

---

## 2. 人看见的功能分区（当前锁定）

新手路径：**目录 → 上传文件 → 自动解析 → 提问**。  
对话**不进资料树**（避免和文件抢位置）。笔记入口已拿掉（PRD 的 `note` 仍可后补，不挡现在）。

```
┌─────────────┬──────────────────────────────────────────┐
│ 工作区切换    │ 当前文件夹标题                              │
│ 全部资料树    │ 工具栏：新建文件夹 / 上传文件 / 上传文件夹 / 提问 │
│             │ 文件列表（解析状态：解析中 / 已可提问 / 失败）      │
│ 提问         │ 点文件 → 预览 + 提取文本 + 元信息               │
│ 工作区搜索    │ 点提问 → Copilot（默认搜本库）                 │
│ 回收站       │                                            │
│ 设置         │                                            │
└─────────────┴──────────────────────────────────────────┘
```

| 分区 | 路由 | 谁用 | 里面有什么 |
|---|---|---|---|
| 资料库 | `/folder/:id` `/item/:id` | 所有成员 | 目录、上传、预览、解析状态 |
| 提问 | `/chat/:id` | 所有成员 | 只问库；右上角选**本次**聊天模型 |
| 搜索 | 对话框 | 所有成员 | 文件夹 + 文件 |
| 账号 | `/account` | 登录用户 | 姓名、头像、邮箱、改密 |
| 工作区 | `/workspace` | admin/owner | 名称、成员、邀请、**连接器（签发 MCP Key）**、**模型（网关 / 嵌入 / 检索）** |
| 个人设置 | `/settings` | 登录用户 | 这台设备：外观、语言、发送快捷键 |
| 平台后台 | Admin 应用（`dev:admin`） | 平台管理员 | 用户、工作区、**平台模型与默认值** |

资料树里**只出现**用户文件夹和文件。隐藏：`$chat` `$providers` `$pages` `$files` 等系统目录。

---

## 3. 模型到底放在哪（三层）

这是当前最容易迷路的一点。模型**不是**资料树上的一种文件。

```
① 平台后台 Admin
     全局供应商（公开根 PUBLIC）上的「平台模型」
     全局设置：默认聊天模型 / 标题模型 / embedding / rerank
        ↓ 新工作区创建时拷贝 defaultChatModel
② 工作区「模型 / 网关」页  ← 人应该来这里配内网网关
     实体仍存在 $providers 下，但 UI 不进资料树
     每个网关：baseURL + API Key，下面挂若干聊天模型
        ↓ 提问时可选
③ 提问页右上角调参
     只选「这一次用哪个聊天模型」
     不配 embedding（那是入库用的）
```

| 配置项 | 放哪 | 干什么 |
|---|---|---|
| 内网网关 URL / Key | 工作区 → 模型 | 所有 LLM 调用只打这里 |
| 聊天 / 嵌入 / 重排模型名 | 点开某个网关添加 | 提问、入库向量、检索重排 |
| 默认提问模型 | 工作区 → 模型 | 新对话缺省；提问页仍可改本次 |
| Embedding 模型 | 工作区 → 模型（可留空用平台默认） | 切片向量化；不配则仅关键词检索 |
| 检索方式 | 工作区 → 模型：关键词 / 混合 / 向量 | 提问怎么找片段；默认混合 |
| 召回条数 / 分数阈值 | 工作区 → 模型 | 对标 Dify dataset retrieval 的 top_k / score |
| 混合检索向量权重 | 工作区 → 模型（仅混合） | 对标 Dify `weighted_score`，默认 0.7 / 0.3 |
| Rerank 模型 | 工作区 → 模型，可选 | 检索后重排（先 ACL 再送模型） |
| 平台默认聊天 / embedding / rerank | Admin → 全局设置 | 工作区未覆盖时的缺省 |
| 本次提问用哪个聊天模型 | 提问页 tune | 覆盖工作区默认 |

**当前代码的问题：** 网关藏在隐藏目录 `$providers`，入口是旧的「自定义供应商」欢迎页和 `/models` 定价页（SaaS）。普通人找不到，所以会觉得「模型放哪都不知道」。  
**改法：** 工作区顶栏「模型」页同时配网关、默认提问模型、嵌入、检索方式、重排。Admin 只保留平台默认。个人设置不再放模型。

内网只保留供应商类型：`openaiCompatible`（公司网关）和可选 `ollama`（本机）。OpenAI / Anthropic / OpenRouter 等公网厂商入口应隐藏。

---

## 4. 架构（数据怎么走）

### 4.1 运行时

```
浏览器 Vue/Quasar :9015
    │  /api 代理
    ▼
Hono :3000     Zero cache :4848     Postgres :5430     MinIO :9000
  鉴权、上传、解析队列、KB 检索     同步副本              业务库           文件
  MCP `/api/mcp`：官方 SDK Streamable HTTP（抄 typescript-sdk 的 Hono 示例）
    │
    ▼
内网 LLM 网关（OpenAI 兼容）  ← 禁止公网备援
```

连接器页签发 Key；Cursor 用 `url + Authorization`；只支持 stdio 的客户端用 `npx mcp-remote` 本地桥（geelen/mcp-remote）。

### 4.2 入库

```
上传文件 → 建 item（parseStatus=queued）→ 写 S3
       → 定时任务 parseKb
       → 抽文本 → chunk（~600 字）→ embedding（若已配）
       → 状态 ready / unparsed / failed
```

解析与预览分开：预览看原文件二进制；提问看 chunk/文本。

### 4.3 提问

```
用户问题 → 工作区知识工具 /api/kb/search
        → 按工作区检索方式：关键词 / 向量 / 混合（默认）
        → can() 过滤（含连接器 folderRoot）后再可选 rerank
        → topK / 分数阈值（对标 Dify dataset retrieval）
        → 带 path + quote 的片段进 prompt
        → 流式回答；无命中则说库里没有
```

MCP `/api/mcp` 工具对齐 PRD §9.3：读（list/tree/search/ask/get）+ 写（mkdir/note/upload/move/tags/delete）。传输抄 `@modelcontextprotocol/sdk` 的 Hono WebStandard Streamable HTTP。

`kb_ask` 先用 `ask` 权限检索引用，再按「工作区根目录 `conf.chatModelId` → 平台默认聊天模型」选择 OpenAI 兼容内网网关。无命中固定返回「知识库未收录」，不调用模型；网关未配置、失败或超时时只回退为引用原文，不补写事实。

V1 可以没有 embedding，关键词也能问。有 embedding 后语义更好。

### 4.4 权限（已完成）

文件夹 ACL 由同一套 `can()` 罩住列表、下载、搜索、问答、MCP 和服务端 mutation。`ask` 必须同时具备 `view`；owner 永远不会被 ACL 锁出。对话默认写入个人 ACL，仅自己可见。

`entityPermission` 把每个用户对每个实体的 `view/ask/edit/delete/manage` 权限物化到 PostgreSQL，由实体 ACL/父目录/根目录和成员变化触发重算。Zero 查询先关联这张表，未授权行不会进入客户端副本。迁移还会把该表加入已存在的 Zero publication，升级部署不需要手工维护复制表清单。

---

## 5. 开源对标（预览 / 知识库）

不要自己用 mammoth HTML + markdown 表格硬画 Office。

| 需求 | 开源实现 | 怎么用 |
|---|---|---|
| Word/Excel/PDF 浏览器预览 | [vue-office](https://github.com/501351981/vue-office)（~6k stars） | `@vue-office/docx` `excel` `pdf`；纯前端，不经公网转换服务 |
| PDF 内核 | pdf.js（vue-office 已包一层） | worker 用仓库内 `public/pdf.worker.min.mjs`，禁止 unpkg |
| 知识库产品形态 | IMA / Dify Dataset / Nextcloud+RAG | 学「目录+解析+问」，不学广场和联网搜 |
| 检索配置 | [Dify](https://github.com/langgenius/dify) dataset retrieval | 工作区模型页：关键词/混合/向量、top_k、分数阈值、混合向量权重（weighted_score）、rerank |
| MCP 传输 | [typescript-sdk](https://github.com/modelcontextprotocol/typescript-sdk) Hono WebStandard 示例 | `/api/mcp` Streamable HTTP；Cursor 官方 `url` + `headers.Authorization` |
| Claude Desktop 桥 | [mcp-remote](https://github.com/geelen/mcp-remote) | `--allow-http` + `Authorization` 放 env，避开 Windows 空格拆参 |
| 服务端 RAG | 自研薄管道（已有） | 不引入 LlamaIndex.TS（已归档） |

PPTX：vue-office 的 pptx 内核不是完全开源（需向作者付费）。V1 对 pptx **下载 + 抽文本提问**，不做幻灯片级预览。

OnlyOffice / Collabora 要单独文档服务，内网可以以后上，不挡 V1。

---

## 6. 该删 / 该藏

产品入口必须消失（代码能删就删，schema 可后拆以免 Zero 炸）：

| 项 | 处理 |
|---|---|
| 翻译、频道、Page、MCP 插件页 | 无入口；死视图文件删除 |
| 公网 web / gread 插件 | 不进 builtin 列表；源文件删除 |
| `/models` 定价页 | 删除 |
| Admin 套餐 / 价格 | 侧栏去掉 |
| 工作区订阅/计费/AI 美金额度 | 已从概览拿掉 |
| 供应商欢迎页 SaaS 文案 | 换成工作区模型页 |
| 资料树里的 Chat/Note/Assistant/Provider | 已藏 |

暂不删表：`page` `channel` `translation` `mcpPlugin`（避免一次改 schema 把 Zero 搞挂）。旧频道、翻译、外部 MCP 插件和发布的 Zero 查询/mutation 已取消注册；新工作区不再创建对应隐藏目录。

---

## 7. 验收（按这个测）

1. 登录 → 进「全部资料」，不是聊天首页。
2. 新建工作区 → 空目录提示上传。
3. 工作区 → **模型**：能加内网网关、拉模型列表、保存。
4. Admin：能配默认聊天模型 + embedding；看不到套餐。
5. 上传 pdf/docx/xlsx → 预览像文档而不是一坨 HTML；状态变为已可提问。
6. 提问页能选模型；没配模型有明确提示。
7. 找不到翻译/频道/定价/发布。
8. 工作区 → **连接器**：创建 Key（只显示一次），复制 Cursor `mcp.json` / Claude Desktop `mcp-remote` 模板，可吊销。
9. 用复制出的配置能 `initialize` + `tools/list`；只读 Key 没有写工具。开发环境 URL 为 `http://127.0.0.1:3000/api/mcp`。

### 7.1 2026-08-24 验证记录

- `bun test`：11 个测试通过，覆盖 ACL 和 `kb_ask` 的成功、无命中、无模型、网关失败、超时。
- `bun run test:permissions`：18 条物化权限与预期一致，覆盖继承中断、guest 拒绝、owner 保护和事务回滚。
- `bun run test:mcp`、`bun run test:mcp-live`：握手通过；只读 8 个工具、读写 15 个工具；跨工作区、目录越界、吊销和过期 Key 均拒绝，操作错误带 `isError`。
- `bun run lint`、`vue-tsc --noEmit`、server/PWA/admin 生产构建通过。
- 浏览器：登录态进入「全部资料」；模型和连接器页加载；Page/Search/Assistant/Plans 旧路由进入 404；390×844 视口无横向溢出。Office 实际文件上传与预览仍需带样本人工验收。
