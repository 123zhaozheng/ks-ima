# P1 全局设计 tokens 与基础组件

父任务：`09-11-ui-workspace-refresh`（读其 prd.md「硬性不变量」与 design.md §1/§2）。

## Goal

把 `src/styles/tokens.css` 从 Apple HIG 方向重调为专业工作台方向，并抽出全站
primitives。本阶段只动 tokens.css（+ 新增组件文件），不动任何页面业务代码——
页面的视觉会随 token 值全局变化，结构性页面改造留给 P2-P7。

## Requirements

- Token 改值严格按父 design.md §1 映射表执行（变量名全部保留，`uno.config.ts` 不动）。
- 新增变量：`--tk-border-subtle`、`--tk-accent-soft-stronger`、`.tk-page-title`、
  `.tk-focus-ring`（focus-visible 2px ring + 2px offset，全局键盘可见）。
- 脚手架类：`tk-cta`/`tk-cta-secondary` 去 pill（radius 8、h38）；`.tk-card` 去
  默认 shadow 只留 border；`.tk-page` 不再固定 900px（由各页面原型自带宽度）。
- 新增 primitives（放 `src/components/`，遵守 component-guidelines）：
  - `StatusBadge.vue`：tone success/muted/warning/danger，点/图标 + 12px label。
  - `PaneEmptyState.vue`：局部空/错态（icon 32 + title + desc + 可选 action 槽）。
  - `SectionHeader.vue`：icon + title + desc + 右侧 action 槽。
  - `.tk-list-row` 全局 CSS 类（grid 40px/1fr/40px、min-height 60px、hover、
    more-btn 默认 opacity .5）。
  - Button variant CSS 类：`tk-btn-primary/secondary/ghost/destructive-ghost`
    （基于 q-btn 类组合，spec 记录用法）。
- Chrome 109：无 CSS nesting / color-mix / oklch / @container / :has。
- 组件需带 vitest 冒烟测试（render + props）。

## Acceptance Criteria

- [ ] tokens.css 全部值符合映射表；grep 无 `18px`/`20px`/`24px`/`30px` radius、
      无 `980px` pill（保留 `999px` 供建议 chip/send）。
- [ ] 5 个页面在 token 变更后无不可读文本/无对比度事故（浏览器自查）。
- [ ] 新 primitives 有单测；`bun run lint` + `bun run test:unit` 通过。
- [ ] 不改任何 `data-testid`、业务代码、uno.config.ts。
