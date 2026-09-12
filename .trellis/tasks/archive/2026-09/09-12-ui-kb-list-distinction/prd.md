# P9：KB 列表目录与文件视觉区分

## 背景

用户截图反馈：知识库工作台（`/kb`）中栏文件列表里，目录行和文件行
全部渲染成蓝色，毫无区分度，选中/悬停/普通三态糊在一起。

## 根因诊断（已确认）

1. `src/css/materialize.scss` 全局规则：
   `.q-item.q-router-link--active, .q-item--active { --at-apply: 'route-active' }`
2. `uno.config.ts`：`route-active = bg-sec-c text-on-sec-c icon-fill`，其中
   `text-on-sec-c → --tk-accent`（亮蓝文字）、`bg-sec-c → --tk-accent-soft`
   （浅蓝底）、`icon-fill`（实心图标）。
3. `KnowledgeList.vue` 与 `FolderTree.vue` 中**每一行**的 `:to` 都指向
   `path: '/kb'`（目录/文件仅靠 query 区分），而 Vue Router 的激活匹配
   **不比较 query 参数**——只要当前路由是 `/kb`，所有行都命中
   `q-router-link--active`，被整行刷蓝。
4. 自有的选中态 `.kb-row-active` / `.kb-tree-item-active` 同样使用
   `--tk-accent-soft` 底，与全行蓝色融为一体 → 无任何区分。

影响面确认：全项目仅这两个组件用 `:to="{ path: ... }"` 带 query 的写法；
顶栏导航指向不同 path，依赖该全局规则的高亮语义正确，**不动全局规则**。

## 修复规格

### 1. 解除路由激活对行样式的劫持

- `KnowledgeList.vue`、`FolderTree.vue`（含根行与目录行）的 `q-item` 增加
  `active-class="kb-row-nav"`（QItem 支持该 prop，默认
  `q-router-link--active`）。该类无任何样式定义，仅用于断开全局
  route-active 规则的命中，保留 `:to` 的中键/新标签打开能力。

### 2. `KnowledgeList.vue` 行视觉分层

| 状态 | 规格 |
| --- | --- |
| 普通行 | 标题 `--tk-text`；图标 `--tk-text-secondary`（弱化） |
| 目录行 | 标题 `font-weight: medium`；目录图标 `icon-fill`（实心） |
| 文件行 | 标题 `font-weight: regular`；图标保持线框（`icon-unfill`） |
| 悬停 | 维持现状 `--tk-bg` 灰底 |
| 选中（`.kb-row-active`）| `--tk-accent-soft` 底 + 既有 inset 描边 + 标题与图标 `--tk-accent` |

实现方式：scoped CSS 类区分（如 `kb-row-folder`/`kb-row-file` 挂在行上，
图标着色用 `.kb-row .q-icon` 级别规则），不改模板结构、不改 testid。

### 3. `FolderTree.vue`

仅做第 1 步的 `active-class` 中性化；当前目录高亮继续由显式
`:active`（`q-item--active` → route-active）+ `.kb-tree-item-active`
驱动，树内语义不变。

## 验收标准

1. `/kb` 下非选中行：标题近黑、图标灰色，无蓝色文字/蓝底。
2. 目录行与文件行一眼可辨（图标实心/线框 + 字重差异），文件行状态徽标不变。
3. 三态清晰可分：普通（白/深色字）、悬停（灰底）、选中（蓝字+浅蓝底+描边）。
4. 左侧目录树仅当前目录高亮，其余行恢复普通配色。
5. `row-delete-action` 等既有 testid 不变；`IngestionStatus.vitest.ts` 等
   相关测试通过。
6. 质量门：`bun run lint` 0 警告、`bun run test`（vitest）全绿、
   `bun run type-check`（vue-tsc）0 错误。

## 范围外

- 不动 `materialize.scss` 全局规则与顶栏导航高亮。
- 不动后端、不改路由结构。
- 视觉验证由用户在浏览器进行（本会话约定 agent 不自行驱动浏览器）。
