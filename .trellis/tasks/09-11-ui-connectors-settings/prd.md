# P6 连接器页面成熟化

父任务：`09-11-ui-workspace-refresh`（design.md §7）。

## Goal

连接器页成为成熟 Developer/Integration Settings：code field、人类可读权限、
紧凑列表、CTA 层级正确。

## Requirements

- 容器 max-width 1000px；卡片 padding 20-24、radius 12（`--tk-radius-lg`）、
  border 无影；卡间 gap 16；`SectionHeader` 替换卡头。
- MCP 资源：code field 展示（`--tk-surface-deep` 底、radius 8、mono 13px、
  `overflow-wrap anywhere`）+ Copy IconButton；点击 icon→`sym_o_check` 1.5s
  后还原（tooltip「已复制」）；成功时不再发 positive Notify（icon 变化即反馈），
  复制失败才 Notify。
- 已连接智能体：空态 compact（neutral icon 24 +「暂无已授权的智能体」+
  「完成 OAuth 或连接授权后会显示在这里。」）；有数据 `.tk-list-row` 行。
- 服务访问表单：名称/用途两列、有效天数（1-90 clamp 逻辑不变）；label 已是
  真实 label（保持 outlined）。
- 权限区：新增 section label「权限范围」；每项两行——人类可读 label 13-14px
  （映射：mcp:knowledge-bases:read→读取知识库、mcp:knowledge:read→读取知识内容、
  mcp:knowledge:search→搜索知识、mcp:knowledge:write→写入知识）+ scope 原值
  11-12px muted monospace 第二行；两列 grid；**`form.scopes` 仍存原 scope 值**。
- CTA「创建服务主体」：移出 grid、右对齐、auto-width、height 38、plus icon。
- principals 列表：compact 行（displayName + purpose · 状态 · 到期时间）；state
  映射中文 label（active→启用、revoked→已撤销、expired→已过期；仅展示层，
  StatusBadge 化）；凭据行保持（前缀 + 时间 + 撤销）。一次性凭据 banner 视觉
  收敛（radius 8），语义与复制交互不变。
- 加入知识库卡（showJoin 时）随规格统一。
- 全部 API 调用、scope 值、校验、错误处理逻辑不动。

## Acceptance Criteria

- [ ] 权限四项均为「人类可读 + mono scope」双行两列；创建请求体 scope 值与
      改造前一致（单测或手测）。
- [ ] copy 成功无 toast、icon 变化 1.5s 还原；失败有 toast。
- [ ] CTA 不再横铺；`bun run lint` + `bun run test:unit` 通过。
