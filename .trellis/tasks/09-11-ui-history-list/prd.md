# P5 历史记录列表化

父任务：`09-11-ui-workspace-refresh`（design.md §6）。

## Goal

历史页成为专业 conversation history list：单 surface、行内 divider、日期分组、
宽屏不再漂浮。

## Requirements

- 容器：max-width 960px、`width: calc(100% - 48px)`、`margin: 24px auto 0`、
  不垂直居中。
- 列表：一个白 surface（border + radius 10px）内 rows 用 divider 分隔；
  `.tk-list-row`（grid 40px/1fr/40px、min-height 60px、padding 10px 14px）；
  左 chat icon 18px 于 32px 容器；title 14/500 + meta 12 muted（kb 名 · 更新于
  M/D HH:mm，用 date-fns `format`；已归档行保持标识）；右 More IconButton
  （`history-item-menu`）默认 opacity .5、row hover 全显；row hover `#f8f9fa`。
- 日期分组（纯前端）：`src/utils/conversations.ts` `groupConversations(items)`
  按 updatedAt 分 今天/昨天/更早（startOfDay 比较），返回有序分组；空/边界
  （跨月、时区）有单测。分组 label：12px/500/muted、margin-top 24（首组 0），
  不在 surface 卡内部加多余分隔。
- 错态/空态沿用现有结构与 testid（`history-list`/`history-item`/
  `history-item-menu`/`history-go-ask`），icon 收敛为 32px 级别。
- 菜单语义（重命名/归档恢复/删除确认）不动。

## Acceptance Criteria

- [ ] 1700px+ 宽屏列表不再「漂在大空白中」（容器宽度按规格）。
- [ ] 分组正确（今天/昨天/更早，跨天边界有单测）；`bun run lint` +
      `bun run test:unit`（含新 groupConversations 单测）通过。
- [ ] 全部 testid 不变；菜单操作路径 e2e 兼容。
