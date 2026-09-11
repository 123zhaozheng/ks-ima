# 技术设计：UI/UX 系统性重构

## 现状（已核实）

- 栈：Vue 3.6 + Quasar 2.16 + UnoCSS（attributify/rem-to-px，theme 映射到 `--tk-*`）
  + Pinia + vue-query。图标统一 Material Symbols `sym_o_*`。
- `src/styles/tokens.css`：完整 `--tk-*` 体系，但当前值是 Apple HIG 方向
  （radius sm/md/lg = 8/12/18、pill CTA `tk-cta`、body 17px、大标题 28px、
  accent `#0071e3`、bg `#fbfbfd` / surface `#f5f5f7`）。`uno.config.ts` 的
  theme colors 引用这些变量（`bg-sur`、`text-on-sur-var` 等旧名）——**改 token 值
  即全局生效，不需要动 uno.config.ts**。
- Shell：`AppShell.vue`（76px rail + tooltip + 全部 testid 已达标）；
  **无全局 header**，每页自带 `q-header`（AskHome/KnowledgeBase/History/
  Connectors/SettingsLayout 各一份，约 50px，样式重复）。`MainLayout.vue` 只包
  `StateHeader`（全局错误条）+ router-view，仅 `/`、`/ask/*`、`/kb` 走它。
- 已有可复用：`tk-card/tk-empty/tk-caption/tk-header` 脚手架类、`CommonItem`、
  `MenuItem`、`AAvatar`、`AInput`。缺：Button 层级规范、IconButton、StatusBadge、
  局部 ErrorState、ListRow、SectionHeader。
- 关键问题点位（已核实行号）：
  - `DocPreview.vue:505` `loadPreviewUrl` 失败 → Notify 红 Toast + `:282` 局部
    「无法预览」双反馈。
  - `KnowledgeList.vue` 行 38px、选中 `--tk-accent-soft`（8% 偏饱和）。
  - `ConnectorsPage.vue:338` `scopeLabel` 把 scope 拆成 `knowledge · read`。
  - `SettingsSecurity.vue:129` 会话行直接渲染完整 UA。
  - `HistoryPage.vue` 860px q-list、`toLocaleString()` 未分组。
  - `AskComposer.vue:150` composer radius 20px、focus 影过重。

## 方案

### 1. Token 重映射（P1，唯一改动点 tokens.css + spec）

策略：**保留全部 `--tk-*` 变量名**（uno.config、各组件引用不动），只改值 + 增补
少量新变量。语义有些名字与新值含义相反（`--tk-surface` 现在是灰底、新方案灰底叫
background），为避免全站语义反转错乱，采用「值微调、语义不变」方案：

| 变量 | 现值 | 新值 | 说明 |
|---|---|---|---|
| `--tk-bg` | `#fbfbfd` | `#f7f8fa` | 页面地面 |
| `--tk-surface` | `#f5f5f7` | `#f1f3f5` | rail、header、inset（hover 同域） |
| `--tk-surface-deep` | `#fafafc` | `#fafbfc` | subtle 白面 |
| `--tk-surface-white` | `#fff` | `#fff` | 卡片/输入（不变） |
| `--tk-border` | `rgba(0,0,0,.08)` | `#e6e8ec` | hairline |
| `--tk-border-strong` | `#d2d2d7` | `#d0d4da` | 强调线 |
| 新 `--tk-border-subtle` | — | `#eef0f2` | header 底线等更轻分隔 |
| `--tk-text` | `#1d1d1f` | `#111318` | |
| `--tk-text-secondary` | `#6e6e73` | `#5f6672` | description |
| `--tk-text-tertiary` | `#86868b` | `#8a919e` | metadata |
| `--tk-accent` | `#0071e3` | `#1677e8` | hover/active 随之同亮度阶 |
| `--tk-accent-soft` | `rgba(0,113,227,.08)` | `rgba(22,119,232,.08)` | active/selected |
| 新 `--tk-accent-soft-stronger` | — | `rgba(22,119,232,.12)` | selected 边框 |
| `--tk-danger` | `#d70015` | `#d92d20` | |
| `--tk-success` | `#248a3d` | `#168a45` | |
| `--tk-warning` | `#b25000` | `#b7791f` | |
| `--tk-radius-sm` | `8px` | `6px` | 小元素 |
| `--tk-radius` | `12px` | `8px` | input/button/card 通用 |
| `--tk-radius-lg` | `18px` | `12px` | panel/popover/dialog |
| `--tk-radius-pill` | `980px` | `999px` | 仅建议问题 chip、composer send 用 |
| 字号 | xs 12 / sm 14 / md 17 / lg 22 / xl 28 | 12 / 14 / 15 / 17(标题) / 21(页标题) | body=14 落地；`md` 语义改为 section/body-strong，页面标题统一走新 `tk-page-title` |
| `--tk-control-h` | `40px` | `36px` | 常规按钮 |
| `--tk-input-h` | `44px` | `38px` | 表单输入 |
| `--tk-row-h` | `48px` | — | 文件行改由组件定 48-52px |

脚手架类同步改：`tk-cta` 去 pill → radius 8、height 38；`tk-cta-secondary` 同理；
`.tk-card` 去掉默认 shadow（只 border）；`.tk-page` 从 900px 固定改为由各原型页面
自带容器宽度；新增 `.tk-page-title`（21px/600/1.3）、`.tk-focus-ring` 通用
focus-visible 样式（2px accent ring + offset 2）。Quasar 覆盖：`q-field--outlined`
radius 8 → 保持；`q-btn` 全局 focus-visible ring。

### 2. Primitives（P1，src/components/ 或复用现有）

不抽象过度——只抽真正多页面复用的：

| 组件/类 | 形式 | 用途 |
|---|---|---|
| `TButton.vue` | q-btn 薄封装（variant: primary/secondary/ghost/destructive-ghost） | 全站按钮层级；height 36（CTA 38） |
| `IconButton` | 约定而非组件：`flat dense round` + `size` 固定 32-36 hit + title/aria-label 必填 | 用 eslint 难约束，靠 spec 约定 + review |
| `StatusBadge.vue` | 小点/图标 + 12px label，tone: success/muted/warning/danger | 文件 Ready、会话「当前」、只读 |
| `PaneEmptyState.vue` | 局部空/错态（icon 32 + title + desc + 可选 action） | preview 无法预览/加载失败、列表空态 |
| `SectionHeader.vue` | icon + title + desc + 右侧 action 槽 | 连接器卡片头、设置分区头 |
| `.tk-list-row` | 纯 CSS 类（grid 40px/1fr/40px、min-height 60px、hover） | 历史、会话、principals 列表 |
| `uaSummary()` | `src/utils/ua.ts` 纯函数：UA → {browser, os} 中文 label + 截断串 | 设置会话行 |
| `groupConversations()` | `src/utils/conversations.ts`：按 updatedAt → 今天/昨天/更早 | 历史分组 |

Button variants 落地为 CSS 类（`tk-btn-primary` 等）+ 必要时薄组件，**优先 CSS 类**
（Quasar q-btn 已有 disable/loading 逻辑，包一层组件会丢透传）。

### 3. 统一 TopBar（P2）

决策：**把 header 从各页面上提到 AppShell**，新建 `src/components/AppTopBar.vue`：

- 结构：`<header class="tk-topbar">`：左 `hamburger`（已有 toggle 逻辑迁移）+
  `q-toolbar-title` ← `route.meta.title`（KB 页例外：显示 `kbStore.current?.name`，
  通过 provide/inject 或 route query 提供覆盖 hook）；右 `<slot name="actions">`。
- 实现方式：AppShell 内 `<app-top-bar><template #actions>` + 子路由通过
  `router-view` 的 component 与 slot 传递困难 → 采用 **provide/inject 的
  header-actions 注册模式**（页面 onMounted 注册 vnode，TopBar teleport 渲染），
  或更简单：TopBar 放 AppShell，actions 用 `<teleport to="#topbar-actions">`
  由页面注入。选 **teleport 方案**（无生命周期管理、天然响应式）。
- 各页面删除自己的 `q-header`；`MainLayout.vue` 的 `StateHeader` 移到 AppShell
  TopBar 之下（全局错误条全站生效）。
- KB 页 badges（只读/已归档）与「分享」按钮 teleport 到 actions；标题用 kb 名。
- `q-layout view` 字符串同步调整（header 从页面级提为 layout 级）。
- 高度 56px、`border-bottom: 1px solid var(--tk-border-subtle)`、背景白（与
  页面内容同色，靠底线分隔）。hamburger 默认 transparent、hover 才有背景。

### 4. 知识库工作区（P3）

- 布局：保持现有 flex 三栏，规格化 tree 232px / list flex / preview
  `flex: 0 0 clamp(380px, 32vw, 480px)`；`<1000px` 时 preview 改为覆盖式 Drawer
  （Quasar q-drawer overlay 或绝对定位 panel + 遮罩），tree 可折叠。
- 文件行：48-52px；icon（folder/note/file）18px；title 14/500 单行 ellipsis；
  file 第二行 status（12px muted + StatusBadge 化 `fileStateView` 输出）；
  行 hover `--tk-bg`，选中 `--tk-accent-soft`（8%→已调 8% 蓝，比旧值视觉更轻）
  + 1px `--tk-accent-soft-stronger` 边；hover 才现 More 菜单保持。
- 工具栏：tree 头「文件夹 + New Folder IconButton」保持；list 头改为
  breadcrumb（全部资料 / 当前文件夹名，可点击）+ 右侧 New note/Upload
  secondary button（icon 16 + label，height 34）。无文件夹选中时按钮 disable
  （现状语义）。
- Preview Inspector：header 56px 已接近，保持 icon-only 动作（spec §9 语法）；
  **ingestion banner 拆解**：ready → 紧凑行内 `✓ 已就绪，可被检索`（success
  13/500）+ `版本 n`（12 muted）；非 ready 保留 banner（进行中/失败仍需显眼 +
  取消/重试按钮）但收敛视觉（info 色调、radius 8、去大色块）。
  **无法预览**：删 `Notify` 红 Toast（DocPreview.vue:505），局部渲染
  `PaneEmptyState`（document-off icon、「暂不支持预览」、说明文案、「下载文件」
  action）；预览 URL 加载失败（区别于格式不支持）给「预览加载失败」+ Retry。

### 5. 提问页（P4）

- 容器：`.ask-home` max-width 780px；页面 padding-top 用 `max(12vh, 64px)` 类
  比例法（非硬编码 top），视觉中心 ~30%。
- Hero：「Nya AI」27px/600；subtitle 14 muted；间距按需求书。
- Composer：radius 14、focus 影收敛为 `--tk-shadow-sm` + border 加深；textarea
  min-height ~120px、15px 文本、placeholder `#7c8492`；toolbar：scope 按钮
  ghost 化（folder icon 16 + label 13 + chevron）、send 40px 圆形
  （disabled 中性灰底白字 → enabled accent，已有 round q-btn 调色即可）；
  Stop 保留。
- 建议问题：高度 32px、padding 0 12px、13px、白底 border pill、hover
  border 加深 + 文字 primary。一行 flex-wrap。

### 6. 历史（P5）

- 容器 960px、`margin: 24px auto 0; width: calc(100% - 48px)`。
- 列表：白 surface（border + radius 10）内 rows（q-list separator 已有）+
  `.tk-list-row`；分组 今天/昨天/更早（section label 12/500 muted,
  margin-top 24，第一组 0）。分组逻辑 `groupConversations`（updatedAt →
  startOfDay 比较；纯前端）。
- 行内：chat icon 18px 于 32px 容器；title 14/500 + meta 12 muted
  （kb 名 · 更新于 M/D HH:mm，date-fns 已有依赖用 `format`）；More 菜单
  opacity .5 → row hover 1。
- 空态/错态沿用 `tk-empty` 但收敛 icon 尺寸（48→32）。

### 7. 连接器（P6）

- 容器 1000px。卡片 padding 20-24、radius 12（`--tk-radius-lg`）、无影。
- MCP URL：code field（`--tk-surface-deep` 底、radius 8、mono 13）+ Copy
  IconButton（点击 icon→`sym_o_check` 1.5s 后还原，tooltip「已复制」；保持
  「已复制」positive Notify 可保留其一——选 icon 变化 + 无 toast，减少噪音；
  复制失败才 toast）。
- 已连接智能体：空态 compact（`sym_o_link_off` 24 + 「暂无已授权的智能体」+
  desc）；有数据用 `.tk-list-row`。
- 服务访问表单：grid 2 列（名称/用途、有效天数半宽）；label 用 q-input
  outlined 自带 label（已是真实 label，OK）。
- 权限区：新增 section label「权限范围」；每项两行
  （label 13px：读取知识库/读取知识内容/搜索知识/写入知识 + scope 11px muted
  mono `mcp:knowledge-bases:read`）；两列 grid；**scope 值本身不变**，
  表单 `form.scopes` 仍存原值。
- CTA：移出 grid，右对齐 auto-width（icon plus + label，height 38）。
- principals 列表：compact 行（名称 + purpose · state · 到期），state 用
  StatusBadge 中文化（active→启用 等，文案语义不变前提下补 label 映射——
  现状直接显示英文 state 字符串，属展示层补全，允许）。

### 8. 设置（P7）

- 容器 860px。
- 个人资料：名称行——displayName 是可编辑的（现有 AInput change 保存逻辑），
  保留可编辑但视觉改为「value text + 编辑态切换」成本高；**取低侵入方案**：
  保持 AInput 但从 filled 灰底改为 outlined 白底（不再像 disabled），email 行
  保持文本。
- 安全会话：`uaSummary(ua)` → `Chrome · Windows` / `curl` 等简洁名 + 第二行
  最后活跃/过期时间（date-fns 相对格式）；当前会话 StatusBadge「当前」；
  撤销按钮 icon + tooltip「撤销会话」；「全部撤销」→ destructive ghost
  （「撤销其他会话」，语义=撤销其他全部会话与现状 revokeAllSessions 一致）。

### 9. 不改的东西（明确清单）

路由表、stores、api clients、composables、全部业务 handler 与确认对话框语义、
e2e 依赖的交互路径（菜单项、testid）、上传/替换/保存/删除流程、KB 权限分支
（isViewer/isArchived/canWrite）、StateHeader 错误条逻辑。

## 兼容与回滚

- 每个子任务独立 commit，可单独 revert。
- token 改值风险最高（全站生效）——P1 提交后全页面视觉自查再进入后续阶段。
- TopBar 上提涉及 q-layout 结构，若 teleport 方案与 q-header 冲突（Quasar
  q-layout 对 q-header 有定位假设），回退方案：保留每页 q-header 但统一抽
  `PageHeader.vue` 组件替换五处重复模板（结构不变、视觉达标）。

## 验证

- 每子任务：`bun run lint` + `bun run test:unit`；涉模板大改加跑相关
  vitest（DocPreviewHeader、ConversationView 等）。
- P2 后：`bun run build`（chrome109）+ dist grep
  `toSorted|toReversed|toSpliced|color-mix|@container|oklch`。
- P3/P5 后：e2e `tests/e2e/grounded-ask.pw.ts`、`knowledge-tree.pw.ts`（若本地
  可跑 playwright）。
- 视觉验收：浏览器 1366/1440/1920 三档人工/截图检查（最终父任务阶段）。
