# 技术设计：管理端合并进单一前端应用

## 现状（已核实）

- `quasar.config.ts` 用 `process.env.TARGET_APP` 决定 devServer 端口（admin→9017，否则 9015/9016）
  和 `@routes` 别名（admin→`src/admin/routes`，否则 `src/router/routes`）。
- `src/router/index.ts` 只做 `import routes from '@routes'`，两条路由树因此共用同一 router 工厂。
- 前端根：`src/App.vue`（仅 `<router-view/>`）；`src/AppFront.vue`（渲染 `<app-shell/>` + PWA 更新逻辑）；
  `src/admin/AppAdmin.vue`（`<q-layout>` + `Dark.set(false)` + 角色守卫）。
- `src/layouts/AppShell.vue` 自带 `<q-layout>` 与 `<router-view/>`，`adminConsoleUrl`（231-235 行）按端口
  拼接 9017/8081 外链。
- 管理端自身：`src/admin/layouts/MainLayout.vue`（drawer + q-header + `<router-view/>`，**无 q-layout**）、
  `AdminDrawer.vue`（`to="/users"` 等绝对路径）、`EmptyPage.vue`（跳 `/users` 或 `/auth/sign-in`）。
- `authRoute`（`src/router/auth.ts`）被前端树与 admin 树各自嵌套一份（绝对路径 `/auth`）。
- 部署：`Caddyfile` 两个 server block（`:8080` root `/srv/front`，`:8081` root `/srv/admin`），
  除 root 外逐字重复；`Dockerfile.web` 顺序 `build:front` + `build:admin`，COPY 到 `/srv/front` 与 `/srv/admin`。
- e2e：`environment.ts` 导出 `adminPort`/`adminOrigin`；`global-setup.ts` 起两个静态服务器、CORS 含 adminOrigin；
  `identity.pw.ts` / `model-governance.pw.ts` 用 `page.goto(\`${adminOrigin}/...\`)`。
- caddy 路由演练：`listener: 8080 | 8081`、publish 两个端口、mount `/srv/front` + `/srv/admin`。

## 方案

### 路由：一个树，管理端挂 `/admin`

`src/router/routes.ts` 收敛为：

```
[
  { path: '/', component: AppShell, children: [ 用户端全部现有子路由（含 authRoute、catchAll） ] },
  { path: '/admin', component: () => import('src/admin/layouts/MainLayout.vue'),
    meta: { requiresAdmin: true }, children: [
      { path: '', component: () => import('src/admin/pages/EmptyPage.vue') },
      { path: 'users', ... }, { path: 'knowledge-bases', ... },
      { path: 'models', ... }, { path: 'audit', ... },
    ] },
]
```

- `authRoute` **保持在前端子树内**（不 hoist），避免两处 `/auth` 重复注册，也保持前端登录页现状不变；
  管理端守卫重定向到 `/auth/sign-in`（由前端子树解析）。
- 管理端页面与 `MainLayout` 全部**动态 import**（`() => import(...)`），确保不进首屏 chunk。
- 静态路径 `/admin` 优先级高于前端 `catchAll`，无需额外顺序处理。

### 根组件与布局

- `src/App.vue`：加 `Dark.set(false)`（两 app 原先各自设置，现集中一处）。
- `src/layouts/AppShell.vue`：接收 `AppFront.vue` 的 PWA `waitingWorker` 更新逻辑；删除 `AppFront.vue`。
- `src/admin/layouts/MainLayout.vue`：补 `<q-layout view="lHr Lpr lFf">` 包裹（原由 `AppAdmin` 提供）；
  删除 `src/admin/AppAdmin.vue`。
- `src/admin/components/AdminDrawer.vue`：`to` 全部加 `/admin` 前缀。
- `src/admin/pages/EmptyPage.vue`：`/users` → `/admin/users`。
- `src/admin/routes.ts`：删除。

### 角色守卫

在 `src/router/index.ts` `createRouter` 后挂全局前置守卫：

```ts
const ADMIN_ROLES = ['super_admin', 'platform_admin', 'security_auditor']
router.beforeEach(to => {
  if (!to.matched.some(r => r.meta.requiresAdmin)) return
  const roles = session.value.data?.user.platformRoles ?? []
  if (roles.some(r => ADMIN_ROLES.includes(r))) return
  return '/'
})
```

- `session` 来自 `src/utils/identity-client.ts`，已是全局 ref；未登录 → 无角色 → 回 `/`（用户端会引导登录）。
- 入口可见性仍由 `AppShell.canSeeAdminConsole`（角色判断，已存在）控制。

### 入口链接

`AppShell.vue` 的「管理控制台」由跨端口 `:href="adminConsoleUrl" target="_blank"` 改为内部 `to="/admin"`；
删除 `adminConsoleUrl` 计算属性。

### 构建 / PWA chunk 隔离

- `quasar.config.ts`：删除 `TARGET_APP` 端口三元与 `@routes` 别名；devServer 端口固定 9015。
- 新增 `build.extendViteConf`，用 `output.chunkFileNames` 把 `moduleIds` 含 `/src/admin/` 的 chunk 落到
  `assets/admin/[name]-[hash].js`，其余落 `assets/[name]-[hash].js`。
- PWA `extendGenerateSWOptions` 增加 `cfg.globIgnores = ['**/assets/admin/**']`，
  使管理端懒加载 chunk 不进预缓存清单（用户端不为其付费）。
- `package.json`：`dev`（单）、`build`（`-m pwa`）。删除 `dev:front`、`dev:admin`、`build:front`、`build:admin`。

### 部署收敛

- `Caddyfile`：删除 `:8081` block；`:8080` 单一 server，root `/srv/app`。
- `Dockerfile.web`：`bun quasar prepare` + `bun run build` 一次；`COPY --from=builder /app/dist/pwa ./app`；`EXPOSE 8080`。
- `docker-compose.example.yml`：删除 `8081:8081` 映射。

### 测试收敛

- `tests/e2e/environment.ts`：删除 `adminPort`/`adminOrigin`。
- `tests/e2e/global-setup.ts`：删除 `build:admin`、admin 静态服务器、CORS 里的 adminOrigin、admin 进程句柄。
- `tests/e2e/identity.pw.ts` / `model-governance.pw.ts`：`adminOrigin` → 相对 `/admin/...`（baseURL 已是 frontOrigin）。
- `scripts/caddy-routing-drill.ts`：单 listener 8080、单 publish、mount `/srv/app`；`.test.ts` 同步。

## 权衡与备选

- **备选 A：保留双构建、只做 nginx 反代同端口 Path** —— 不删冗余，只把端口藏起来，弃。
- **备选 B：单 app 但用 `?admin=1` query 切布局** —— 与路由/守卫模型冲突，弃。
- **备选 C：不隔离 PWA 预缓存** —— 实现更少，但所有用户后台下载管理端 chunk，是净回归，弃。
- **选定**：一树一路由 + 懒加载 + chunk 目录隔离。代价是 `extendViteConf` 十行左右的构建配置，
  换来首屏包体与预缓存都干净。

## 兼容与回滚

- 行为变化：管理端从 `http://host:8081/` 变为 `http://host/admin/`；旧 8081 不再监听。
  需要在发布说明中告知管理员新地址（本仓库无独立发布说明文件，写入 PR 描述）。
- 无数据模型/后端变化；`git revert` 即可整体回滚（无迁移、无持久化状态）。
- 前端用户端首屏行为除 PWA 预缓存清单缩小外不变。

## 测试策略

- 静态：`bun run lint`、`bunx vue-tsc --noEmit`。
- 单测：`bun test`（含 `scripts/caddy-routing-drill.test.ts`）、`bunx vitest run`（组件测试）。
- 构建产物断言：`bun run build` 后确认 `dist/pwa/assets/admin/` 存在独立 chunk，且 sw 预缓存 manifest 不含之。
- 路由演练：`bun run test:caddy-routing`（单监听、单 root）。
- e2e：`bun run test:e2e`（管理员 `/admin/*` 全流程）。
- 手测：用户端登录 → 侧栏「管理控制台」→ 内部跳转 `/admin`；普通用户无入口且访问被重定向。
