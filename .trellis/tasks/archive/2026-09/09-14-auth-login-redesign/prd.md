# 登录页品牌分栏重设计

## 背景

现有登录页（`/auth/sign-in`）是一张朴素的居中窄卡片：Quasar `filled` 输入框直接堆叠、无品牌呈现、无视觉层次，用户反馈“丑、布局不友好”。项目已有完整的设计系统（`src/styles/tokens.css` 的 `--tk-*` token，主色 `#1677e8`）和明确的 UX 设计语言（`.trellis/spec/frontend/ux-design-language.md`，腾讯 ima 式知识工作台）。

## 目标

参考各大厂（飞书 / 钉钉 / 企业微信 / Google）登录页的主流模式，将认证页重设计为**左右分栏品牌布局**，并与现有 `--tk-*` 设计 token 体系完全一致。

## 需求

### 布局（`src/layouts/AuthLayout.vue`）

- 桌面端（≥1024px）：左右分栏
  - 左侧品牌面板：深色品牌渐变背景（`--tk-accent` 色系延展）、产品 Logo（`public/icons/icon-256x256.png`）、产品名“Nya AI”、一句标语、3 条特性亮点（Material Symbols outlined 图标 + 短文案）、底部版权行
  - 右侧表单面板：浅色背景（`--tk-bg`），表单容器垂直居中，宽度约 400px
- 移动端（<1024px）：折叠为单列 —— 顶部紧凑品牌条（Logo + 产品名），下方表单
- 路由 meta.title（登录/注册/重置密码/接受邀请）渲染为表单区大标题 + 副标题，替代现在的小字标题

### 表单（`src/components/SignInForm.vue`）

- 输入框从 `filled` 改为 `outlined`（各大厂主流），带前置图标（邮箱 / 锁）
- 密码框提供明文可见性切换（append 图标按钮）
- 主按钮：全宽、40px 高、accent 填充（对齐 `tk-btn-primary` 体系）
- 辅助行：左侧“注册”链接（注册关闭时隐藏），右侧“忘记密码”

### 兄弟表单一致性

同一 AuthLayout 下的 `SignUpForm.vue` / `ResetPasswordForm.vue` / `AcceptInviteForm.vue` / `SetPasswordInputs.vue` 输入框统一为 `outlined`，间距节奏一致（`--tk-space-*`）。

## 约束（硬性）

- 所有颜色/圆角/间距引用 `--tk-*` token，不硬编码调色板值；渐变只允许 accent 同色系明度变化，不引入新色相
- Chrome 109 兼容：无 CSS nesting、无 `color-mix()` / `oklch()` / `@container`、不用 `:has()`
- 保持 e2e 契约不变（`tests/e2e/identity.pw.ts` 等）：
  - 输入框 label 文案不变："电子邮件" / "密码" / "显示名称" / "确认密码"
  - 按钮文案不变："登录" / "注册" / "重置密码" / "接受邀请"
  - `data-testid="sign-up-link"` 保留
  - 忘记密码按钮文案"忘记密码"保留
- 表单行为逻辑（提交、TOTP 挑战、注册开关能力查询、重定向）零改动

## 验收标准

1. 桌面视口登录页呈左右分栏：左品牌区渐变 + Logo + 标语 + 特性点，右表单区
2. 移动视口（≤600px）折叠为单列：顶部品牌条 + 表单，无横向滚动
3. 注册 / 重置密码 / 接受邀请页在同一布局下视觉一致
4. 密码可见性切换可用；注册关闭时注册链接不渲染
5. `bun run lint` 通过；`bun run test:unit` 通过
6. 浏览器实测：登录提交、忘记密码对话框、注册页跳转均正常（桌面 + 移动视口）
7. dist 构建无 Chrome 109 禁用语法（`color-mix|oklch|@container` 零命中）
