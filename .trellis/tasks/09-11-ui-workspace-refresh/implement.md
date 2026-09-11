# 执行计划：UI/UX 系统性重构

子任务顺序执行（P1 是其余一切的地基；P3 最复杂；P4-P7 可在 P2 后并行但串行执行
保持 diff 干净）。每个子任务 = 一个 commit，独立可回滚。

前置阅读：父任务 `prd.md`、`design.md`；spec `ux-design-language.md`、
`component-guidelines.md`、`quality-guidelines.md`。

## 阶段 → 子任务映射

| 阶段 | 子任务 | 验证门 |
|---|---|---|
| P1 | 09-11-ui-tokens-primitives | lint + test:unit + 全页面快速视觉自查 |
| P2 | 09-11-ui-appshell-topbar | lint + test:unit + build(chrome109) + dist grep |
| P3 | 09-11-ui-kb-workspace | lint + test:unit + e2e knowledge-tree（若可跑）|
| P4 | 09-11-ui-ask-home | lint + test:unit + e2e grounded-ask（若可跑）|
| P5 | 09-11-ui-history-list | lint + test:unit |
| P6 | 09-11-ui-connectors-settings | lint + test:unit |
| P7 | 09-11-ui-settings-account | lint + test:unit |
| 收尾 | 父任务 | spec 更新 + 三分辨率视觉验收 + 最终报告 |

## 步骤

### 1. P1 tokens + primitives
- [ ] `tokens.css` 按 design.md §1 表改值 + 新增 `--tk-border-subtle`、
      `--tk-accent-soft-stronger`、`.tk-page-title`、`.tk-focus-ring`。
- [ ] 脚手架类改：`tk-cta`/`tk-cta-secondary` 去 pill（radius 8、h38）；
      `tk-card` 去默认 shadow；`tk-page` 容器策略调整。
- [ ] 新增 `StatusBadge.vue`、`PaneEmptyState.vue`、`SectionHeader.vue`、
      `.tk-list-row` CSS、button variant CSS 类。
- [ ] `uno.config.ts` 不动（theme 引用变量名）。
- 验证：lint / test:unit；浏览器翻 5 页确认无对比度灾难。

### 2. P2 AppShell + TopBar
- [ ] `AppTopBar.vue`（56px、teleport actions 容器 `#topbar-actions`）。
- [ ] `AppShell.vue` 集成 TopBar + StateHeader；五页面删各自 `q-header`，
      hamburger 逻辑迁移；KB 页标题/actions teleport。
- [ ] rail 打磨（active 浅 primary、icon 尺寸、tooltip delay）。
- 验证：lint / test:unit / build；dist grep 禁用 API。

### 3. P3 知识库工作区
- [ ] KnowledgeList 行规格 + 选中态 + status badge 化。
- [ ] list 头 breadcrumb + secondary buttons。
- [ ] DocPreview：ingestion 紧凑化 + 无法预览局部 EmptyState + 删重复 Toast。
- [ ] 布局宽度/响应式（<1000px preview Drawer）。
- 验证：lint / test:unit / vitest DocPreviewHeader；e2e knowledge-tree 若可跑。

### 4. P4 提问页
- [ ] AskHome 布局（视觉中心上移、max-width）。
- [ ] AskComposer 精修（radius/影/toolbar/scope ghost/40px send）。
- [ ] 建议问题与页脚。
- 验证：lint / test:unit；e2e grounded-ask 若可跑。

### 5. P5 历史
- [ ] 容器 + surface 列表 + `.tk-list-row`。
- [ ] `groupConversations` + 分组渲染 + 单测。
- [ ] 行内 meta 格式化（date-fns）。
- 验证：lint / test:unit。

### 6. P6 连接器
- [ ] code field + copy 交互（icon→check 1.5s）。
- [ ] 权限双行制（label 映射表，scope 值不变）+ 两列。
- [ ] CTA 右下角；principals compact 列表 + state label 映射。
- 验证：lint / test:unit。

### 7. P7 设置
- [ ] `src/utils/ua.ts` `uaSummary` + 单测（Chrome/Edge/curl/空 UA）。
- [ ] 会话行改造 + StatusBadge 当前 + destructive ghost。
- [ ] 名称行 outlined 化。
- 验证：lint / test:unit。

### 8. 收尾（父任务 Phase 3）
- [ ] spec `ux-design-language.md` 重写 §1 token 表 + 新增页面原型/TopBar/
      状态反馈章节；核对 §8 i18n 章节与现状。
- [ ] 三分辨率视觉验收（1366/1440/1920）对照 prd 验收标准 17 条。
- [ ] 最终报告（修改文件/tokens/组件/页面改动/未动逻辑/检查结果）。

## 回滚点

每阶段 commit 独立；P1 token 全局生效若有灾难性视觉问题，revert 单 commit
即可恢复。P2 TopBar 若 teleport 与 q-layout 冲突 → 回退方案（design.md §9）。

## 提交规范

`feat(ui): <子任务摘要>` / `docs(spec): <...>`，正文说明视觉意图与不动点。
