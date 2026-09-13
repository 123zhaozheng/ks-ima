# PRD: 清理工作区冗杂文件与目录

依据 `.trellis/spec/frontend/identity-admin-contracts.md` 测试质量原则"冗杂内容一律删除"的精神，清理仓库根目录的冗杂内容。

## 盘点结论（2026-09-13）

### 删除（可再生成的产物 / 误命名垃圾）
- `D：codepythonnyaai.env` — 误命名的 env 文件（命令重定向路径笔误产物），内容为 `.env` 的部分旧副本
- `quasar.config.ts.temporary.compiled.1788071370970.mjs`、`...1788158469614.mjs` — Quasar 临时编译残留（.gitignore 已覆盖）
- `test-results/` — Playwright 运行残留（.gitignore 已覆盖）
- `.dev-pg/` — 本地 Postgres 脚本的日志残留（.gitignore 已覆盖）
- `dist/` — PWA 构建产物，`bun run build` 可再生（.gitignore 已覆盖）
- `.quasar/` — Quasar dev 缓存（.gitignore 已覆盖；dev 服务器当前未运行）
- `.mypy_cache/`、`.ruff_cache/`、`.pytest_cache/` — 工具缓存，可再生

### 保留（在用）
- `frontend/generated/openapi.json` — `bun run generate:api` 与后端契约脚本使用
- `assets/`（README 截图）、`docs/`（设计文档）、`src-pwa/`（PWA service worker 源码）、`public/`、`src/`、`tests/`、`scripts/`、`backend/src`
- `.trellis/`、`.agents/`、`.codex/`、`.github/`、`.vscode/`

### 用户确认后保留（2026-09-13 决定：都不删除）
- `backend/.venv/`（约 280MB，后端依赖环境）
- `.codegraph/`（18.5MB，codegraph MCP 索引）
- `.claude/`、`.qoder/`（用户其他 AI 工具的本地数据）

## 验收标准
1. 删除清单执行后 `git status` 无新增未跟踪垃圾。
2. 保留清单中的目录与文件不受影响。
3. 构建/测试链路不受影响（产物可再生成）。
