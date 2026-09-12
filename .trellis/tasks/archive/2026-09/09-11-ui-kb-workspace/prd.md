# P3 知识库三栏工作区精修

父任务：`09-11-ui-workspace-refresh`（design.md §4）。

## Goal

知识库页成为专业 Workspace：文件行规格化、工具栏成熟化、预览 Inspector
状态精修、消灭「无法预览」双反馈，并补 <1000px 响应式。

## Requirements

- 布局：tree 232px / list flex / preview `flex: 0 0 clamp(380px, 32vw, 480px)`；
  `<1000px` preview 变覆盖 Drawer（含关闭交互），tree 可折叠；list 永不被压窄
  （min-width 保持）。
- 文件行（KnowledgeList）：48-52px；icon 18px；title 14/500 ellipsis；file 第二
  行状态 12px muted（status → StatusBadge 化，Ready 绿点不喧宾）；行 hover
  `--tk-bg`；选中 `--tk-accent-soft` 背景 + 1px `--tk-accent-soft-stronger` 边；
  hover 才现 More 菜单保持；`加载更多` 行样式收敛。
- 工具栏：tree 头保持（文件夹 + New Folder IconButton）；list 头改 breadcrumb
  （全部资料 / 当前文件夹名，点击回上级）+ New note/Upload secondary
  （34-36px、icon 16、`kb-new-note`/`kb-upload` testid 不变、disable 语义不变）。
- DocPreview：
  - ingestion **ready** → 紧凑行内状态（`✓ 已就绪，可被检索` 13/500 success +
    `版本 n` 12 muted），替换现大 banner；非 ready（进行中/失败/取消）保留 banner
    形态但视觉收敛（radius 8、信息色、去大色块），取消/重试按钮保留。
  - 无法预览：删除 `loadPreviewUrl` 失败时的红色 Notify（DocPreview.vue:505），
    局部渲染 `PaneEmptyState`（document-off icon、「暂不支持预览」、
    「该文件已成功处理并可被检索，但当前格式无法在浏览器中预览。」、「下载文件」
    action）。区分「格式不支持」与「加载失败」：加载失败给「预览加载失败」+ Retry。
  - header 56px 与 icon-first 动作保持（spec §9），不回退。
- 预览空态（未选文档）保持提示但用 PaneEmptyState。
- 全部业务逻辑（上传/替换/保存/删除/版本历史/取消/重试）与 testid 不动。

## 管理知识库弹窗精修（2026-09-11 用户反馈补充）

范围：`KbManageDialog.vue`、`KbMembersPanel.vue`、`KbShareLinksPanel.vue`。

- 文案精简：
  - 重命名区：section 标题「重命名知识库」→「名称」；q-input 去掉 label
    「知识库名称」（输入框内容即当前名称，自解释）。
  - 分享链接区：删除「拿到分享链接的人都可以加入该知识库。」整行说明；
    「有效期（天）」label 与「留空表示不过期。」hint 合并为 placeholder
    「有效期（天），留空不过期」；去掉 hint 后 input 不再撑高创建行。
  - 危险区：删除底部 caption（「删除前需要先归档该知识库。」/「只有已归
    档的知识库才能删除。」）——约束已由「未归档时不显示删除按钮」表达，
    删除确认对话框内已有说明。
  - 空态短文案（「暂无成员」「还没有分享链接」）保留。
- 对齐：rename 行 input 与「重命名」按钮等高（36px）垂直居中；分享创建行
  （role toggle + 有效期 input + 创建按钮）垂直居中、控件等高；section
  间距沿用现有 `gap: var(--tk-space-5)`。
- 不动：全部 testid（`kb-manage-dialog`、`kb-rename-input`、`kb-rename-save`、
  `share-role-toggle`、`share-link-create`、`share-link-new`、`share-link-url`、
  `share-link-copy`、`share-link-revoke`、`kb-member-menu`、`kb-leave`、
  `kb-archive`、`kb-restore`、`kb-delete`）、全部业务逻辑与 isOwner 门控。

## Acceptance Criteria

- [ ] 同一错误不再同时出现局部态 + Toast（无法预览场景验证）。
- [ ] 选中行为柔和（无饱和蓝大条）；行高/字号/状态符合规格。
- [ ] `bun run lint` + `bun run test:unit`（含 DocPreviewHeader.vitest）通过；
      e2e `knowledge-tree.pw.ts` 若本地可跑则通过。
- [ ] 1366/1920 下三栏不挤压、无横向滚动；<1000px preview 为 Drawer。
- [ ] 管理弹窗无句子级说明文字（分享说明/有效期 hint/危险区 caption 已移除
      或并入控件）；rename 行与分享创建行控件等高、垂直居中。
- [ ] 管理弹窗全部既有 testid 保留；重命名/成员/分享链接/归档/删除流程可用。
