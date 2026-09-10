# 合并管理端到单一前端应用

## 背景

当前前端是**一个 Quasar 工程、两套构建产物**：

- `TARGET_APP=front` → PWA，路由 `src/router/routes.ts`，dev 端口 9015 / 生产 8080；
- `TARGET_APP=admin` → SPA，路由 `src/admin/routes.ts`（经 `@routes` 别名切换），dev 端口 9017 / 生产 8081。

两套产物靠 `TARGET_APP` 环境变量、`@routes` 别名、两份 `AppXxx.vue` 根组件、两个 `MainLayout` 拼出来。
部署侧 `Caddyfile` 有 `:8080` / `:8081` 两个除 `root` 外**完全重复**的 server block；`Dockerfile.web` 构建两次；
e2e 需要 `frontPort` + `adminPort` 两个静态服务器；`AppShell.vue` 里还有一段按端口猜测拼接管理端外链的
`adminConsoleUrl`（`port === '9015' || '9016' ? '9017' : '8081'`）。

这套拆分带来的直接问题：本地开发管理端经常落到 9017/9018，用户开 9015 看不到入口；端口猜错就访问不到。

**关键事实：独立端口从来不是安全边界。** 每个 `admin` API 都在后端按 capability + CSRF 鉴权
（`model_governance.require`、`admin.require`）；前端只是入口可见性差异。

## 目标

把管理端合并进**同一个前端应用、同一个端口**，入口按平台角色显示，删除全部双构建/双端口的冗余代码。

## 需求与约束

1. 单一构建目标：一个 `dev`、一个 `build`，不再有 `TARGET_APP`、`@routes` 别名、`src/admin/routes.ts`、`AppAdmin.vue`。
2. 管理端路由挂在 `/admin/*`，与用户端同源同端口；`src/admin/**` 作为功能目录保留。
3. 入口按角色可见（`super_admin` / `platform_admin` / `security_auditor`），非管理员直接访问 `/admin/*` 被重定向。
4. **管理端页面必须懒加载**，不得进入用户端的首屏 chunk；PWA 预缓存不得把管理端 chunk 一并预缓存。
5. 部署与测试配置同步收敛：`Caddyfile` 只留一个 server block，`Dockerfile.web` 只构建一次，
   compose 去掉 8081，e2e 去掉 `adminPort`/`adminOrigin`，caddy 路由演练去掉 8081。
6. 管理端功能行为不变（用户 / 知识库 / 模型配置 / 审计四页可用）。
7. 不新增依赖，不做管理端视觉改版，不改后端。

## 验收标准

- [ ] `bun run dev` 单条命令起一个前端（9015），`/` 用户端、`/admin` 管理端都可用。
- [ ] 管理员登录后侧栏出现「管理控制台」入口，点击**内部跳转**到 `/admin`（不再跨端口开新标签）。
- [ ] 普通用户看不到入口；直接访问 `/admin/users` 被重定向回用户端。
- [ ] 管理端四个页面（用户 / 知识库 / 模型配置 / 审计）功能与合并前一致。
- [ ] 构建产物中，用户端首屏 chunk 不含管理端页面代码；管理端页面为独立懒加载 chunk。
- [ ] PWA 预缓存清单不含管理端 chunk。
- [ ] 冗余全部删除：`TARGET_APP`、`@routes`、`src/admin/routes.ts`、`AppAdmin.vue`、
      `AppFront.vue`（SW 逻辑并入 shell）、`adminConsoleUrl`、Caddy `:8081` block、compose 8081、
      e2e `adminPort`/`adminOrigin`、caddy 演练 8081。
- [ ] 质量关卡通过：`bun run lint`、`bunx vue-tsc --noEmit`、`bun test`、`bunx vitest run`、
      `bun run test:caddy-routing`；e2e（`bun run test:e2e`）绿。

## 非目标

- 不改管理端页面的视觉与交互细节。
- 不改后端任何路由、鉴权或数据模型。
- 不引入路由级代码分割框架之外的新工具。
- 不处理"工作区里已有的其它未提交改动"（scene-model-save 等），本任务只动与合并相关的文件。
