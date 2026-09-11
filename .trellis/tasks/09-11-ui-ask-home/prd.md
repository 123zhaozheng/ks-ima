# P4 提问页 composer 精修

父任务：`09-11-ui-workspace-refresh`（design.md §5）。

## Goal

提问页成为成熟的 AI Knowledge Assistant landing state：intentional whitespace、
精细 composer、建议问题与页脚。

## Requirements

- 布局：`.ask-home` max-width 780px 居中；视觉中心位于 viewport 顶部 28-34%
  （用 `padding-top: max(12vh, 64px)` 类比例法，禁硬编码像素 top）；不数学垂直居中。
- Hero：「Nya AI」26-30px/600；subtitle「基于你的知识库，想问点什么？」14px
  muted；标题-subtitle 8px、subtitle-composer 28-32px。
- Composer（AskComposer.vue）：
  - 容器 radius 14、padding 16、focus 收敛为 border 加深 + `--tk-shadow-sm`
    （去掉现过重的 12px/32px 大影）；min-height ~120px。
  - textarea 15px、placeholder `#7c8492`、无边框感保持。
  - toolbar 左：scope 按钮 ghost 化（folder icon 16 + label 13 + chevron 下拉，
    `ask-scope-chip` testid 不变、FolderPickerList 交互不变、document scope
    removable chip 保留但视觉统一）；右：send 40px 圆形（disabled 中性灰/
    enabled accent），Stop 按钮保留。
- 建议问题（ask-hint）：高 32-34px、padding 0 12px、13px、白底 border pill、
  hover border 加深 + 文字 primary；一行 flex-wrap；填充行为不变。
- 页脚「回答基于你的知识库内容。」12px muted，margin-top 18。
- onboarding 空态与新建 KB 对话框随 token 自动达标，仅微调 icon 尺寸。
- Enter 发送 / busy→Stop / 无 KB 阻止发送等逻辑全部不动。

## Acceptance Criteria

- [ ] 1440/1920 下 hero+composer 位于视觉中心偏上，无「漂浮」感、无横向滚动。
- [ ] `ask-composer`/`ask-send`/`ask-stop`/`ask-scope-chip`/`ask-hint(s)` testid
      与交互路径不变。
- [ ] `bun run lint` + `bun run test:unit` 通过；e2e `grounded-ask.pw.ts` 若可跑
      则通过（SSE mock 不受样式影响）。
