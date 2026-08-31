# Design — 控制台全中文化、模型一键配置与 UX 修复

## 现状要点（探索结论）

- i18n：自研封装 `src/utils/i18n.ts`（i18n-pro），键即英文原文，`i18n/zh-CN.json` 英→中映射；约 558 处 `t(`，48 个文件。无 vue-i18n。
- 模型治理前端：`src/admin/pages/ModelsPage.vue`（758 行，4 tab，全英文键）。后端已具备：
  - `POST /api/v1/admin/model-gateways/{id}/discover` → 拉取远端 `/v1/models`（`backend/src/ima/infrastructure/model_gateway/egress.py:225`）
  - governed-models CRUD/validate/enable/disable；capability-profiles 草稿/验证/发布；profile-assignments；impact。
  - 前端 client：`src/utils/identity-client.ts:174-198`。
- 审计：`src/admin/pages/AuditPage.vue` 直接渲染 action/result 原码；数据 `GET /api/v1/admin/audit-events`。
- KB 切换 bug：`AppShell.vue` 标签绑定异步 `kbStore.kb`；`stores/knowledge-base.ts` 的 watcher 会静默重置 id；`switchKb` 强制 `router.push('/')`；`isOwner` 用详情接口不返回的 `owned`。分享面板仅 `KbManageDialog`（owner），唯一入口是 `/kb` 工具栏无文字图标。

## 并发波次与文件所有权（互不相交）

### Agent A — i18n 基础设施 + 非 KB 组件/页面
拥有：
- 删除：`i18n/`、`i18nrc.ts`、`src/utils/i18n.ts`、`src/utils/english-plural.ts`、`tests/components/i18n-mock.ts`
- 编辑：`package.json`（去 i18n-pro 与 "t" script）、`quasar.config.ts`（仅加 `lang: 'zh-CN'`，**不得动 devServer.port 行**——有未提交的 admin 9017 修复）、`src/utils/local-data.ts`、`src/utils/api-error.ts`、`src/stores/readonly-state.ts`、`src/router/auth.ts`、`src/router/routes.ts`、`vitest.config.*`/`tests/setup-dom.ts`（去 i18n-mock 别名）、`src/components/SettingsList.vue`（删语言切换器）
- 编辑（t→中文）：components 下 AcceptInviteForm、AskComposer、ChangePasswordDialog、CitationSources、CreateNoteDialog、DocPreview、FileInputArea、FolderPickerList、FolderTree、ForgotPasswordDialog、NewFolderDialog、ResetPasswordForm、SaveAnswerDialog、SetPasswordInputs、SettingsSecurity、SignInForm、SignUpForm、UploadDialog、VerifyTotpDialog；layouts/SettingsLayout.vue；pages 下 AskHome、ConnectorsPage、ConversationView、HistoryPage、JoinKnowledgeBase、NotFoundPage、OAuthConsentPage
- 更新上述组件对应的 tests/components/* 测试（断言改中文）

### Agent B — 知识库切换/分享 UX（含其 t→中文）
拥有：`src/layouts/AppShell.vue`（**保留未提交的 adminConsoleUrl 9017 改动**）、`src/stores/knowledge-base.ts`、`src/components/KbMenuList.vue`、`KbManageDialog.vue`、`KbMembersPanel.vue`、`KbShareLinksPanel.vue`、`KnowledgeList.vue`、`src/pages/KnowledgeBase.vue`，及这些组件的测试。

### Agent C — 管理台重写（含其 t→中文）
拥有：`src/admin/**` 全部（AppAdmin.vue、routes.ts、AdminDrawer.vue、BanUserDialog/CreateUserDialog/UpdateUserDialog、KnowledgeBasesPage、UsersPage、ModelsPage.vue 重写、AuditPage.vue 重写），新增 `src/admin/components/ModelAvatar.vue`、`src/admin/model-catalog.ts`，及 admin 测试。logo 静态资源 `src/assets/model-logos/*.svg` 由主会话预下载，C 只引用不下载。

## 模型页 UX 规格（Agent C）

Tab（3 个）：「模型服务」「场景配置」「知识库分配」。页头：模型配置 / 副标题「集中管理系统使用的 AI 服务商与模型」。

### 模型服务 tab
- 服务商卡片区 + 右上「添加服务商」按钮。卡片：logo（按 baseUrl/名称识别厂商，见 model-catalog）、名称、脱敏地址、启用开关、动作：拉取模型（主色）/健康检查/编辑/删除。
- 添加/编辑对话框字段：名称、API 地址（placeholder 例 `https://api.deepseek.com/v1`）、API 密钥（仅显示一次）、开关「允许白名单内的内网 HTTP 地址」附说明文案。
- 「拉取模型」对话框：调 discover → 复选列表；行 = logo + 模型 ID + 能力标签（自动：含 embedding/bge→向量化；含 rerank→重排序；其余对话）+ 已知维度自动填（可改）；底部「导入所选 (n)」→ 批量创建 governed models（默认启用，label=模型 ID）。已存在的模型行置灰标「已导入」。
- 卡片下方「模型清单」表：logo/名称/能力（中文 tag）/远端名称/状态（已验证·草稿）/启用开关/验证/删除。

### 场景配置 tab（原工作流配置）
五张卡片，中文命名+一句说明：
- 知识库问答（grounded_ask）：用户提问时使用的对话模型与检索参数
- 标题生成（title_generation）：自动生成对话标题
- 摘要（summarization）：长文摘要
- 向量化（embedding）：文档转向量；换模型可能需要重建索引
- 重排序（reranking）：检索结果精排
卡片内容：当前生效版本徽标；结构化表单（按 workflow 类型显示：对话模型 select / 向量模型 select / topK 数字等，选项来自已启用 governed models 对应能力）；「高级」折叠显示原始 JSON textarea；按钮：保存草稿/验证/发布/停用。

### 知识库分配 tab（原分配与影响）
每个知识库一张卡片：各 workflow 的已发布 profile 版本 select + 「保存分配」；「检查影响」→ 人话横幅：`切换后将有 N 个索引需要重建` / `无需重建索引`。

### model-catalog.ts 规格
- `detectVendor(modelIdOrUrl): Vendor` 前缀/子串规则：gpt-/o1/o3/text-embedding→openai；deepseek；qwen/tongyi；glm/cogview→zhipu；moonshot/kimi；baichuan；mistral/mixtral；claude→anthropic；gemini→google；hunyuan；spark；yi-→yi；minimax；bge→baai。
- `VENDORS: {id, 中文名, color, logo?}`，logo 从 `src/assets/model-logos/<id>.svg` import；无 logo 用首字母彩色圆底。
- `guessCapability(id)`、`KNOWN_DIMENSIONS: Record<string, number>`（text-embedding-3-small 1536、3-large 3072、ada-002 1536、bge-m3 1024、bge-large-zh-v1.5 1024、embedding-3 2048 等）。

## 审计页规格（Agent C）
- 先 `grep -rn '"[a-z_]*\.[a-z_.]*"' backend/src/ima --include=*.py` 穷举 `_audit(` 的 action 与 PolicyReason/reason 码，建 `AUDIT_ACTIONS: Record<string,{label:中文,group:权限|知识库|模型|账户|MCP}>`、`REASONS`、`RESULTS={success:成功,failure:失败}`。
- 列：时间（相对+title 绝对）、操作者、动作（中文主+原码小灰字）、对象、结果徽标。筛选：分组 select + 结果 select。未知码原样显示。

## KB UX 规格（Agent B）
- 名称同步来源改为成员列表：`current = memberships.find(m=>m.id===id)`；列表加载前显示骨架而非「未选择」。
- watcher 仅在 `id==null || !ids.includes(id)` 时初始化，不覆盖用户刚选的值。
- `switchKb` 删除 `router.push('/')`。
- `isOwner` 用成员列表 role==='owner'。
- `/kb` 工具栏：带文字「分享」按钮（owner），打开 KbManageDialog 并默认定位分享面板；KbMenuList 当前 KB 行下加「管理与分享」项。
- 保留 AppShell 未提交的 adminConsoleUrl（9017/8081）逻辑。

## 风格基线（B、C 共用）
苹果风：`rounded-lg`(12px) 卡片、1px 淡边框、充足 padding、标题 17-20px 半体、次级文字灰、主按钮单一主色、危险操作红色文字按钮；不堆砌图标；文案口语化中文。

## 验证
每波完成后主会话跑：`bunx vue-tsc --noEmit`、`bun run test`（vitest）、双构建、后端 pytest；再交 trellis-check 复核。
