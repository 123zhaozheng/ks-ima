# 执行计划：紧凑侧栏 + 文档操作图标化

前置阅读：`prd.md`、`design.md`、`implement.jsonl` 的 spec。

## 步骤

1. [ ] `src/stores/ui-state.ts`：`mainDrawerWidth` 收敛为紧凑值（约 76）。
2. [ ] `src/layouts/AppShell.vue`：导航项改紧凑竖排（图标为主 + 中文提示），保留 `data-testid`、
       知识库切换器、角色可见性、退出登录。
3. [ ] `src/components/DocPreview.vue`：头部改为
       `[关闭][标题] …… [保存][询问][下载][⋯]`，全部纯图标 + 中文提示；`⋯` 下拉收纳
       替换/编辑-预览/历史/预览/删除；保留禁用/加载/只读条件与 `data-testid`。
4. [ ] 更新/新增 vitest（DocPreview 头部图标与下拉；侧栏若有用例一并调整）。
5. [ ] `bun run lint`、`bunx vue-tsc --noEmit`、`bunx vitest run`、`bun test`。
6. [ ] 更新 `.trellis/spec/frontend/ux-design-language.md`（紧凑侧栏 + 图标优先 + 溢出菜单）。

## 回滚点

- 纯前端展现层；`git revert` 即可。

## 审查门

- 确认无中文可见按钮文字、提示为中文、`data-testid` 未丢、只读上下文无写操作。
