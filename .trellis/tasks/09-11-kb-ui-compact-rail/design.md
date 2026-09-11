# 技术设计：紧凑侧栏 + 文档操作图标化

## 现状（已核实）

- 侧栏：`src/layouts/AppShell.vue` 的 `q-drawer.app-rail`，`:width="uiStateStore.mainDrawerWidth"`；
  `src/stores/ui-state.ts` 中 `mainDrawerWidth = 240`、`mainDrawerBreakpoint = 1200`。
  项为 `q-item`（`avatar` 图标 + `q-item-label` 文案）横排：知识库切换器、提问、知识库、历史、连接器、
  设置、管理控制台（角色可见）、退出登录。导航项带 `data-testid`（`rail-nav-*`）。
- 文档预览头部：`src/components/DocPreview.vue:8-116`，按钮顺序为
  关闭/标题输入/询问这篇文档(label)/历史/编辑-预览(label)/替换(label)/下载/预览/删除/保存(label)。
  其中「询问这篇文档」「替换」「保存」带文案，其余仅图标；提示用 `title=`。
- 既有测试：`tests/components/*`（含 KnowledgeList/DocPreview 相关）。e2e 依赖 `data-testid`。

## 方案

### A. 紧凑侧栏（`AppShell.vue` + `ui-state.ts`）

- `mainDrawerWidth` 由 240 调整为紧凑值（约 76px；含 logo/头像与图标）。
- 导航项改为**竖向紧凑**：图标居中、可选极小号标签或纯图标 + 悬浮 `q-tooltip`；`q-item` 使用
  `flex flex-col items-center`，`q-item-section avatar` 与无 avatar，保证点击区域与可读性。
- 保留：`data-testid`、角色可见性、`kb-switcher` 头像 + 菜单、退出登录、管理控制台入口。
- 移动端（< breakpoint）仍为 overlay 抽屉，行为不变。
- 使用 token（`--tk-*`）控制尺寸/间距；避免硬编码。

### B. 文档操作图标化（`DocPreview.vue`）

头部布局（左 → 右）：
```
[关闭] [标题输入……]  ……  [保存] [询问] [下载] [⋯]
```
- 三个固定按钮：`保存`（`sym_o_save`，primary，`:disable="!document || !dirty"`，`:loading="saving"`）、
  `询问`（`sym_o_chat`，`doc-ask-button`）、`下载`（`sym_o_download`）。全部 `flat dense round`、
  仅图标、`title` 中文提示。
- `⋯`（`sym_o_more_vert`）为 `q-btn` + `q-menu`，菜单项：
  - 替换（仅 `kind==='file' && !readonly`）
  - 编辑/预览切换（仅 `kind==='note' && !readonly`）
  - 历史
  - 预览（`kind==='file'`）
  - 删除（`!readonly`，负向样式，`doc-delete-button`）
- 隐藏的 `<input type=file>` 保留（替换流程不变）。
- 删除/保存/替换的禁用与权限条件照旧；只读上下文不出现写操作项。
- 提示统一：`title` 或 `q-tooltip`（择一，保持全页一致）；`data-testid` 保留。

## 权衡与备选

- **备选 A：侧栏保持 240px 只换样式** —— 未解决「过宽」，弃。
- **备选 B：文档按钮保留文字仅统一样式** —— 与「统一去掉文字、用提示」要求不符，弃。
- **选定**：紧凑图标栏 + 图标优先操作 + 溢出菜单。

## 兼容与回滚

- 纯前端展现层改动；无路由/数据契约变化。`data-testid` 保留以维持 e2e。
- 回滚：`git revert`。

## 测试策略

- vitest：`DocPreview` 头部断言 —— 无中文可见按钮文本、`doc-ask-button`/`doc-close-button` 存在、
  `⋯` 菜单含替换/历史/预览/删除项、只读时不显示写操作。
- 既有 `KnowledgeList`/`DocPreview` 用例保持通过；`data-testid` 不回归。
- 静态：`bun run lint`、`bunx vue-tsc --noEmit`、`bunx vitest run`、`bun test`。
- 手动：宽屏查看侧栏宽度与提示；文档头部悬停看提示；`…` 下拉功能可用。

## Spec

- `.trellis/spec/frontend/ux-design-language.md`：新增「紧凑侧栏」「图标优先操作 + 溢出菜单」两节，
  说明：横排文字项优先收敛为图标 + 提示；高频操作固定、低频收入 `…`；提示用中文；保留可访问性
  （`aria-label`/`title`/`data-testid`）。
