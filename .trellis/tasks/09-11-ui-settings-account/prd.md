# P7 个人设置页成熟化

父任务：`09-11-ui-workspace-refresh`（design.md §8）。

## Goal

设置页成为成熟 Account/Security Settings：只读信息不再像禁用输入框、会话信息
降噪、危险操作层级正确。

## Requirements

- 容器 max-width 860px。
- 个人资料：名称行保留可编辑语义（AInput change→updateProfile 不动），视觉从
  `filled` 灰底改 `outlined` 白底（不再像 disabled）；电子邮件保持 value text。
- Security 卡：修改密码 row（lock icon + 标题 + chevron，整行 hover）→ 已有
  CommonItem 结构，统一到 SettingsRow 视觉（可用 `.tk-list-row` 变体）；两步
  验证区保持（按钮 34-36px 高）。
- 活跃会话：
  - 新增 `src/utils/ua.ts`：`uaSummary(ua)` 纯函数 → `{ summary: 'Chrome · Windows',
    raw }`；覆盖常见 UA（Chrome/Edge/Firefox/Safari、Windows/macOS/Linux/Android/iOS、
    curl/wget/PostmanRuntime/空值 → 「未知客户端」）；单测覆盖。
  - 会话行：第一行 `summary` + 当前会话 StatusBadge「当前」（替换蓝 badge）；
    第二行 `最后活跃 … · 过期时间 …`（date-fns 相对/短格式）；原始 UA 不再作
    主信息（`title` 属性携带 raw 即可）。
  - 右侧 Revoke IconButton（tooltip「撤销会话」，非当前会话才显示，语义不变）。
  - 「全部撤销」→ destructive ghost「撤销其他会话」（调 revokeAllSessions 语义
    不变，文案明确为撤销其他会话）。
- session revoke/TOTP/改密全部业务逻辑与 testid（`settings-revoke-all`、
  `settings-totp-setup`、`settings-change-password`）不动。

## Acceptance Criteria

- [ ] 会话行主信息为「浏览器 · 系统」而非原始 UA 串；「当前」为 badge 而非蓝字。
- [ ] `uaSummary` 单测通过（≥6 用例）；`bun run lint` + `bun run test:unit` 通过。
- [ ] revoke 交互语义不变（单撤销、全部撤销）。
