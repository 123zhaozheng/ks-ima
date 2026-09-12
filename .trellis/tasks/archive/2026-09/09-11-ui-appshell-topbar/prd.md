# P2 统一 AppShell 与 56px TopBar

父任务：`09-11-ui-workspace-refresh`（design.md §3 TopBar 方案与回退）。

## Goal

Sidebar + Header 成为统一 App Shell：56px TopBar 全站一致，五页面删除各自
`q-header`；rail 打磨 active/hover/尺寸。

## Requirements

- 新建 `src/components/AppTopBar.vue`：高 56px、白底、
  `border-bottom: 1px solid var(--tk-border-subtle)`；左 hamburger（transparent
  默认、hover 才有背景，迁移现有 `uiStateStore.toggleMainDrawer`）+ 标题
  （`route.meta.title`；KB 页显示 `kbStore.current?.name`）；右侧 actions 区
  用 teleport 容器 `#topbar-actions`（页面 `<teleport to="#topbar-actions">` 注入）。
- `AppShell.vue` 集成 TopBar；`MainLayout.vue` 的 `StateHeader`（全局错误条）
  移入 AppShell 紧贴 TopBar 下方，全站生效。
- 五页面（AskHome/KnowledgeBase/HistoryPage/ConnectorsPage/SettingsLayout）删
  各自 `q-header` 与 hamburger；KB 页的 只读/已归档 badge + 分享按钮 teleport
  到 actions。
- 若 teleport 与 q-layout/q-header 定位冲突 → 回退方案：抽 `PageHeader.vue`
  组件替换五处模板（视觉达标、结构不变），并在父任务 design.md 记录决策。
- Rail：item ~40px、icon 19-20px、active 浅 primary 背景（`--tk-accent-soft`）+
  primary icon、radius 9-10px、tooltip 延迟 400-600ms；hover `--tk-surface`。
  全部 rail testid（`kb-switcher`、`rail-nav-*`）不变；退出登录仍 hover 红。
- `view` 字符串 / q-page-container 结构调整后无布局回归（AskHome 的
  `calc(100vh - header)` 类样式同步为新高度）。

## Acceptance Criteria

- [ ] 全站 5+ 页面 header 高度/背景/底线完全一致；标题来自 route meta/KB 名。
- [ ] KB 页分享/只读/归档入口在 TopBar 可用，testid 不变（`kb-manage`）。
- [ ] `ask-home-menu` 等 e2e 入口不破坏（若迁移则同步 e2e 引用并跑通）。
- [ ] rail testid 全部保留；admin 门控不变。
- [ ] `bun run lint` + `bun run test:unit` + `bun run build` 通过；dist grep
      `toSorted|toReversed|toSpliced|color-mix|@container|oklch` 零命中。
