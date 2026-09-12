# P8 管理控制台对齐 AppShell 与页面成熟化

父任务：`09-11-ui-workspace-refresh`。来源：2026-09-11 用户反馈——admin 左侧
仍是宽抽屉、与首页紧凑 rail 完全断裂。

## Goal

/admin 从独立 MainLayout 迁入 AppShell：全站共享紧凑 rail + 56px TopBar；
admin 四页（用户/知识库/模型配置/审计）清除旧样式类，按 design tokens 成熟化。

## Requirements

- 路由/布局：
  - `/admin/*` 路由迁入 AppShell children，保持懒加载（独立 chunk 隔离不变）
    与 `meta.requiresAdmin` 门控；`rail-nav-admin` testid 与 platformRoles 门控不变。
  - 删除 `src/admin/layouts/MainLayout.vue` 与 `src/admin/components/AdminDrawer.vue`
    （宽抽屉 + 旧 q-header 退役）；「返回应用」入口不再需要（rail 全站可见）。
  - admin 区局部导航：在 admin section 内做紧凑二级导航栏（180-200px 列表栏，
    沿用 KB 工作区 pane 的视觉语言），含 用户/知识库/模型配置/审计 四项，沿用现有
    platformRoles 门控（`canManageUsers` / `canReadModelGovernance`）；设置入口
    （`UpdateSettingsDialog`，`canManageSettings` 门控）迁入二级导航底部。
  - `SystemStatusIndicator` 不得丢失：移到 admin 页 TopBar actions（teleport 到
    `#topbar-actions`）或二级导航头部。
  - TopBar 标题经 route.meta.title 生效（管理控制台/用户/知识库/模型配置/审计）。
  - admin 页模板去掉自身 `q-page-container` 嵌套（迁入后由 AppShell 提供）。
- 页面成熟化（UsersPage/KnowledgeBasesPage/ModelsPage/AuditPage）：
  - 清除旧 utility 类（`bg-sur-c-low`、`bg-pri-c`、`text-on-pri-c`、`bg-err-c`、
    `text-on-err-c` 等 sur/pri/err-c 系列），改用 `--tk-*` tokens 与 tk-btn 体系。
  - 页内工具栏：搜索/筛选 dense；主按钮 36px、与主 app primary/secondary 规格一致。
  - 错误/提示 banner 收敛：radius 8、信息色、去大色块（与 kb-workspace banner 规格一致）。
  - q-table：flat；行高 40-48px、字号 13-14px；表头 13px muted；空态用 PaneEmptyState。
- 硬约束：Chrome 109（禁出 `toSorted|toReversed|toSpliced|color-mix|@container|oklch`）；
  不新增平行色值；全部业务逻辑、API 调用与既有 testid 不动；文案不做句子级堆砌。

## Acceptance Criteria

- [ ] /admin/* 在 AppShell 内渲染：紧凑 rail 与 56px TopBar 持续可见，主 app 与
      admin 之间来回导航无布局跳变；浏览器前进/后退正常。
- [ ] admin 四项导航与设置入口的 platformRoles 门控与迁移前完全一致；非 admin
      用户不可见不可达（requiresAdmin 守卫不变）。
- [ ] SystemStatusIndicator 在 admin 区可见可用。
- [ ] 四页无 sur/pri/err-c 系列旧类残留；按钮/表格/banner 规格与主 app 一致。
- [ ] `bun run lint` + `bun run test:unit` + `bunx vue-tsc --noEmit` +
      `bun run build` 通过；dist grep 零命中；admin 仍为独立懒加载 chunk
      （`dist/pwa/assets/admin/` 存在，主 bundle 不内联 admin 页面）。
- [ ] 浏览器验证：admin 用户在四页间导航、返回主 app；1366/1920 宽度无横向滚动。
