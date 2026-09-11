# UI/UX 系统性重构：成熟 AI 知识工作台

## 背景

当前前端功能完整，但视觉与信息架构停留在原型感：token 体系在 `tokens.css` 里被调成
Apple HIG 方向（radius 8/12/18、pill CTA、17px body、28px 大标题），spec 文档（Semi
4/6/8）与代码已互相漂移；没有统一 TopBar（每页自带 ~50px q-header）；知识库页文件行
过密、选中态是饱和色整条、无法预览时同时出现局部空态和红 Toast 的重复反馈；历史列表
在宽屏漂浮；连接器把 raw scope 当主文案；设置页把 UA 字符串当主信息。

用户（2026-09-11）给出完整的设计需求书，要求在**完全不动业务逻辑**的前提下把产品
升级为「Linear 的克制 + Notion 的 workspace 感 + AI 产品的安静感」的专业工作台。

## 目标

1. 重调全局 design tokens 为专业工作台方向，spec 与代码重新对齐。
2. 统一 AppShell：保留 76px 紧凑 rail，新增全局统一 56px TopBar。
3. 按 4 种页面原型（Focused AI / Workspace / List / Settings）重构 5 个页面，
   宽屏有意识布局，不再「小组件漂浮在大空白中」。
4. 抽出可复用 primitives，全站 Button/IconButton/Badge/EmptyState/ErrorState 一致。
5. 设计语言写入 `.trellis/spec/frontend/ux-design-language.md`。

## 硬性不变量（违反即失败）

- 不改路由、API 调用、数据结构、权限逻辑、文件操作流程、知识库逻辑、MCP/Connector
  逻辑、登录与 Session 语义、MCP scope 值、session revoke 语义。
- 全部 `data-testid` 保持原名（e2e 契约，见 spec §6）；新增交互需加 testid。
- 现有中文业务文案语义不变（可精修呈现方式，不改含义）。
- Chrome 109 硬约束：无 CSS nesting、无 `color-mix()`/`oklch()`/`@container`/`:has()`、
  无 `toSorted/toReversed/toSpliced`；v-html 内容 FLAT 选择器。
- 不引入新框架/UI library/图标库：Quasar 2 + UnoCSS + Material Symbols 原地改造。
- 不做 dark mode（现状也不支持）。
- 不虚构功能（无搜索逻辑就不放假搜索框，无 Sort/View 功能就不放假按钮）。
- 保留全部 loading/error handling；不删既有交互（Enter 发送、Stop、scope 选择等）。

## 视觉方向

关键词：clean / calm / precise / dense but breathable / professional / workspace /
AI-native / minimal。UI 退后，内容为主。明确不要：CRM 后台感、大圆角 Card Dashboard、
玻璃拟态、渐变科技风、Neon、pill 满天飞、厚阴影。

### Token 目标值（允许 ±微调，保持比例关系）

- 色彩：`--background #F7F8FA`、`--surface #FFFFFF`、`--surface-subtle #FAFBFC`、
  `--foreground #111318`、`-secondary #5F6672`、`-muted #8A919E`、
  `--border #E6E8EC`、`--border-subtle #EEF0F2`、accent 接近 `#1677E8`（沿用蓝系）、
  `primary-soft` ≈ accent 8-10%、`success #168A45`、`danger #D92D20`、`warning #B7791F`。
- Radius：小元素 6px、Input/Button 8px、Card/Panel 10-12px、Popover/Dialog 12px。
  禁止 18/20/24/30px 大圆角。提问 composer 例外允许 14px（AI 输入框惯例）。
- Spacing：严格 4/8 节奏（4/8/12/16/20/24/32/40/48），禁随机 13/18/27/37px。
- Shadow：绝大多数 surface 只用 border；仅 Popover/Dropdown/Modal/Toast/浮层允许
  `0 1px 2px rgba(0,0,0,.04), 0 8px 24px rgba(0,0,0,.06)` 级别轻影。
- Typography：字体栈不变；Page title 20-22px/600、Section title 15-16px/600、
  Body 14px/400、Strong 14px/500、Small/Metadata 12-13px/400、Button 13-14px/500。
  禁 30px+ 页标题、大面积 700 weight。
- 状态色语义：hover `rgba(0,0,0,.025-.04)`、selected primary 6-9% 背景、
  focus-visible 2px primary ring + 2px offset（键盘可达必须可见）。
- 动画：hover 120-160ms ease-out、popover 150-180ms、drawer 180-220ms；
  支持 `prefers-reduced-motion`；禁 bounce/spring/发光/渐变动画。

### AppShell

- 保留 76px rail：图标居中 19-20px、item ~40-42px、hover `#F1F3F5`、active 浅
  primary 背景 + primary icon、radius 9-10px；全部 icon 有 tooltip（延迟 400-600ms）；
  底部 settings/admin/logout 保持 bottom-anchored；全部 rail testid 不变。
- 全局统一 TopBar 56px：`border-bottom: 1px solid border-subtle`、左 hamburger（默认
  transparent，hover 才有背景）+ 页面标题（route meta）、右 page action 区。
  Sidebar+TopBar 构成统一 App Shell。

### 页面原型（每种页面布局不同，禁止全站一个容器）

- **A Focused AI**（提问）：max-width 760-820px 居中，视觉中心在 viewport 顶部
  28-34%（非数学垂直居中）；hero 26-30px/600 + subtitle 14px muted；composer
  min-height 116-132px、radius 14、轻影、padding 16、底部 toolbar 左侧范围选择
  compact ghost button（folder icon+label+chevron）、右侧 40px 圆形 send（disabled
  灰/enabled primary）；建议问题 32-34px 高 pill 距 composer 16-20px；页脚
  「回答基于你的知识库内容。」12px muted。
- **B Workspace**（知识库）：三栏 grid `220-240px / minmax(480px,1fr) / 400-480px`
  （未打开文件时第三栏不存在）；pane 白底 1px vertical divider；无大 Card。
  Folder row 36-40px、active 用 primary-soft；文件行 48-52px、
  `[icon][title+metadata][status][hover actions]`、选中
  `rgba(primary,.06)`+可选 `rgba(primary,.12)` 边、hover `#F7F8FA`、文件名 14px/500、
  metadata 12px muted、Ready 用绿色小点 StatusBadge 不喧宾夺主。列表工具栏含
  breadcrumb + New note/Upload（ghost/secondary 34-36px，icon 16px）。
  预览 Inspector：header 56px（Close/Title 单行 ellipsis/保存/询问/下载/⋯ 全 18px
  icon）；ingestion 状态改为紧凑行内（✓ 已就绪，可被检索 13px/500 绿 + 版本 12px
  muted），不再用大 banner；无法预览 = 局部 EmptyState（document-off icon 32px +
  「暂不支持预览」+「该文件已成功处理并可被检索，但当前格式无法在浏览器中预览。」+
  可选下载按钮），预览加载失败给 Retry，**不再同时弹红 Toast**。
- **C List**（历史）：max-width 920-1040px、`calc(100% - 48px)`、margin 24-32px auto 0、
  不垂直居中；一个白 surface（border、radius 10px）内部 rows 用 divider；row
  min-height 60px、grid `40px/1fr/40px`、左 32px 容器内 18px chat icon、title 14px/500
  + metadata 12px muted（gap 4px）、右 More IconButton 默认 opacity .5 hover 全显、
  row hover `#F8F9FA`；前端按 updatedAt 分组 今天/昨天/更早（12px/500/muted
  section label，margin-top 24px）——仅前端分组，不动后端。
- **D Settings**（连接器 960-1040px、设置 820-900px）：Card 白底 border radius
  10-12px 无影、padding 20-24px、gap 16px。连接器：MCP URL 用 code field
  （#F8F9FA 底、radius 8、monospace 12-13px）+ Copy IconButton（icon→check 1.5s）；
  已连接智能体空态 compact；服务访问表单真实 label（非 placeholder）、38-40px input、
  权限 checkbox 双行制（人类可读 label 13-14px + scope 11-12px muted mono）、可两列；
  CTA「创建服务主体」右下角 auto-width 38px 高 + plus icon。设置：只读信息用 value
  text（admin 不放灰 input）；修改密码/两步验证/活跃会话用 section divider 分区；
  会话行解析 UA 为「浏览器 · 系统」（解析失败显示截断 UA 于第二行）、当前会话用
  「当前」StatusBadge、右侧 Revoke IconButton；「撤销其他会话」destructive ghost。

### 状态与反馈

- Loading 优先 skeleton（不要整页 spinner）；Empty 用 small neutral icon+title+
  optional description+action（无 warning icon）；Error 局部失败局部展示，Toast 仅用于
  操作的瞬时反馈、不重复页面已有错误；Success/Ready/Connected 才用绿，且不大面积。

### 响应式（desktop 优先）

- >1200：完整 rail + 三栏。1000-1200：rail 保持，preview 可缩至 ~380px。
  <1000：preview 变 Drawer、folder pane 可折叠。<768：现状 overlay rail 已有，不重做。

### 「AI 味」黑名单（必须消灭）

每内容都包 Card、大圆角、到处 shadow、大量 pill、渐变、玻璃拟态、一屏一窄卡四周
千 px 空白、全站 max-width 768px、全按钮蓝、每个 icon 配灰圆底、选中项变巨大蓝条、
placeholder 代替 label、metadata 和正文一样黑、随机 radius、混用图标风格、虚构功能。

## 验收标准（来自需求书 §21）

- [ ] 1366×768 / 1440×900 / 1920×1080 三档下：rail 全页一致、Header 高度一致、
      Button 高度一致、icon stroke/size 一致、文字层级一致、Card radius 一致、
      border 色一致。
- [ ] 宽屏无「小组件漂浮在大空白中」感；知识库像专业 Workspace；连接器/设置像
      专业 Settings 页；历史像 list 而非 card gallery；提问页 whitespace 是
      intentional 的。
- [ ] 无横向滚动。
- [ ] 所有可点击 icon ≥32px hit target；icon-only 控件有 tooltip/aria-label。
- [ ] Tab 键 focus 可见（2px ring）。
- [ ] 同一错误不同时出现两次（局部 + Toast 去重）。
- [ ] `bun run lint`、`bun run test:unit`、`vue-tsc`/build（chrome109 target）通过；
      dist grep 无禁用 API。
- [ ] spec 更新：ux-design-language.md 的 token 表、页面原型、TopBar 章节与代码一致
      （移除过时的 §8 i18n 章节描述，记录实际现状）。

## 交付物

1. tokens/primitives/shell/五页面代码 + 每阶段一个 commit（按子任务）。
2. spec 更新（父任务 Phase 3）。
3. 完成报告：修改文件清单、新增 token 清单、抽出的公共组件、各页主要改动、
   未动的业务逻辑、lint/typecheck/build 结果。
