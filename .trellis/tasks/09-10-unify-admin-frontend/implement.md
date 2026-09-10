# 执行计划：管理端合并进单一前端应用

前置阅读：`prd.md`、`design.md`，以及 `implement.jsonl` 列出的 spec。
本地验证环境：后端 9016（`backend/run_server.py`），前端合并后固定 9015。

## 步骤

### 1. 路由与根组件合并
- [ ] `src/router/routes.ts`：`/` 用 `AppShell`；新增 `/admin`（`meta.requiresAdmin`，`MainLayout` 与五个页面动态 import）；保留前端子树与 `authRoute`。
- [ ] `src/router/index.ts`：删除 `@routes` 导入，改为 `./routes`；挂全局 `beforeEach` 角色守卫（ADMIN_ROLES）。
- [ ] `src/App.vue`：加 `Dark.set(false)`。
- [ ] `src/layouts/AppShell.vue`：并入 `AppFront` 的 PWA 更新逻辑；入口改内部 `to="/admin"`；删 `adminConsoleUrl`。
- [ ] `src/admin/layouts/MainLayout.vue`：补 `<q-layout>` 包裹。
- [ ] `src/admin/components/AdminDrawer.vue` / `src/admin/pages/EmptyPage.vue`：路径加 `/admin` 前缀。
- [ ] 删除 `src/AppFront.vue`、`src/admin/AppAdmin.vue`、`src/admin/routes.ts`。
- 验证：`bunx vue-tsc --noEmit` 通过；`bun run dev` 后 `/` 与 `/admin` 均可打开。

### 2. 构建配置收敛
- [ ] `quasar.config.ts`：删 `TARGET_APP` 端口三元与 `@routes` 别名；端口 9015；加 `extendViteConf`（admin chunk → `assets/admin/`）；PWA `globIgnores: ['**/assets/admin/**']`。
- [ ] `package.json`：`dev` / `build` 单命令，删 `dev:front|dev:admin|build:front|build:admin`。
- 验证：`bun run build` 成功；`dist/pwa/assets/admin/` 有独立 chunk；sw 清单不含 admin chunk。

### 3. 部署与演练收敛
- [ ] `Caddyfile`：删 `:8081` block，`:8080` root 改 `/srv/app`。
- [ ] `Dockerfile.web`：单次构建，COPY `dist/pwa` → `/srv/app`，`EXPOSE 8080`。
- [ ] `docker-compose.example.yml`：删 8081 映射。
- [ ] `scripts/caddy-routing-drill.ts` + `.test.ts`：单 listener 8080、单 publish、mount `/srv/app`。
- 验证：`bun run test:caddy-routing` 通过。

### 4. e2e 收敛
- [ ] `tests/e2e/environment.ts`：删 `adminPort`/`adminOrigin`。
- [ ] `tests/e2e/global-setup.ts`：删 `build:admin`、admin 静态服务器与进程句柄、CORS 里的 adminOrigin。
- [ ] `tests/e2e/identity.pw.ts` / `model-governance.pw.ts`：改走相对 `/admin/...`。
- 验证：`bun run test:e2e` 绿（需 docker）。

### 5. 质量关卡（最后一轮全量）
- [ ] `bun run lint`、`bunx vue-tsc --noEmit`、`bun test`、`bunx vitest run` 全过。
- [ ] `rg "TARGET_APP|@routes|adminOrigin|adminPort|8081|AppAdmin|AppFront|adminConsoleUrl"` 无残留（除 archive/spec 历史文档）。
- [ ] 手测：管理员侧栏入口内部跳转 `/admin`；普通用户无入口、直访被重定向。

## 回滚点

- 每步独立可回退；整体 `git revert`（无迁移、无持久化副作用）。

## 审查门

- 步骤 1 完成后自查路由树与守卫（无重复 `/auth`、catchAll 不吞 `/admin`）。
- 步骤 5 全绿后方可报告完成；`git status` 确认未误动 scene-model-save 等无关改动。
