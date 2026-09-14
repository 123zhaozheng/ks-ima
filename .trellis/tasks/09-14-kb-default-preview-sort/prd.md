# 知识库默认预览首文件 + 列表排序

## 背景

知识库页（`/kb`）三栏布局：文件夹树 / 内容列表 / 预览面板。两个体验问题：

1. **进入知识库或切换文件夹时不默认预览任何文档**，预览面板显示空态「选择一篇文档以预览」，用户必须手动点一篇才看到内容，多一步操作。
2. **内容列表无排序控件**，顺序完全由后端按 `orderKey`（手动排序键）+ 标题返回，用户无法按「文件夹优先 / 文件优先」「上传时间」「名称」整理视图，条目一多就显得乱。

## 现状关键事实（已核代码）

- 列表数据：`KnowledgeList.vue` → `useFolderContents(folderId)` → `knowledgeClient.contents(folderId, { cursor, limit, kind })`（`src/api/knowledge-client.ts:33`）。
- 后端 `list_contents`（`backend/src/ima/application/knowledge.py:149`）：SQL `ORDER BY order_key, lower(title), id`，游标 `ListingCursor` 绑定 `(parent_id, children_version, order_key, normalized_name, item_id)`，翻页依赖该排序。
- 返回 `ContentRow` 字段：`id / kind / title / orderKey / version / lifecycle / fileState`，**无时间字段**（`src/api/generated/schema.ts:2309`）。
- 预览选中态：路由 query `?folderId=` + `?doc=` 驱动（`KnowledgeBase.vue:328-335`）；`previewCollapsed` 初始 `true`，选中后置 `false`。
- 「新建笔记」「上传」按钮在 `KnowledgeBase.vue` 的 `kb-list-header`（153-174 行）；排序按钮将加在「新建笔记」旁。
- `DocumentResponse` 已有 `createdAt`（`knowledge_contracts.py:58`），但列表用的 `ContentRow` 没有。

## 需求

### A. 默认预览第一篇文档

- 进入知识库、或切换文件夹后，若当前 URL **没有** `?doc=`，自动选中并预览当前排序下的**第一篇可预览文档**（`kind` 为 `file` 或 `note`，跳过 `folder`）。
- 通过路由跳转写入 `?doc=`（与现有选中态一致），可刷新保留、可分享链接。
- 若文件夹为空 / 只有文件夹没有文档，保持预览空态，不跳转。
- 用户手动关闭预览后不因列表重取而被强制重新打开。

### B. 列表排序控件

- 在「新建笔记」按钮旁加**排序按钮**（图标 + 下拉菜单，`q-menu`，复用现有模式）。
- 菜单项：
  - **分组**：文件夹优先（folders first）／ 文件优先（files first）。
  - **排序字段**：上传时间（createdAt）／ 名称（title）。
  - **方向**：升序 / 降序（时间默认降序=最新在前，名称默认升序）。
  - **默认 / 手动排序**：恢复 `orderKey`（用户手动排序）作为默认选项。
- 排序选择持久化（localStorage），跨文件夹、跨会话生效。
- 切换排序后重新拉取列表并从头分页。

## 已确认决策（用户拍板）

1. **排序走后端**：给 `contents` 接口加排序参数，`ContentRow` 增加 `createdAt`（文档为上传/创建时间；文件夹为其 created_at）。全量排序、可正确翻页。
2. **保留 orderKey**：`orderKey` 作为「默认 / 手动」排序选项；用户选时间/名称排序时覆盖它。不引入拖拽排序 UI。
3. **默认预览用路由**：进入时若无 `?doc=` 则 `router.replace` 跳转到第一篇文档。

## 约束（硬性）

- 排序参数与游标联动：排序键变化必须使旧游标失效并从头分页（沿用现有 `LISTING_CHANGED` 机制或把排序纳入游标），**不允许** 把 A 排序的游标用于 B 排序的翻页。
- 翻页「加载更多」在任意排序下都正确，不漏不重。
- 不破坏现有 e2e 契约：`kb-new-note` / `kb-upload` / `kb-new-folder` / `data-testid` 不变；`knowledge-list` 行结构（`kb-row`、删除菜单）不变。
- 只读 / 已归档知识库的只读语义不变（排序、默认预览对 viewer 同样可用，但不可写）。
- 前端 Chrome 109 兼容；颜色/间距引用 `--tk-*` token。

## 验收标准

1. 进入 `/kb` 选中某知识库后，若根目录有文档，自动预览第一篇；切进有文档的文件夹同样自动预览第一篇；空文件夹显示空态不跳转。
2. 「新建笔记」旁出现排序按钮，弹出菜单可选：文件夹优先/文件优先 × 上传时间/名称 × 升/降序，及「默认（手动排序）」。
3. 选「上传时间·降序」后列表按创建时间新到旧排列且文件夹/文件按所选分组；翻页加载更多顺序正确、不重不漏。
4. 排序选择刷新页面后保留；切回「默认」恢复 orderKey 顺序。
5. 默认预览不改变「用户手动关闭预览」的状态（本次会话内不再自动打开）。
6. `bun run lint`、`bun run test:unit` 通过；后端相关测试通过；浏览器实测桌面 + 窄屏（预览抽屉）两形态。
