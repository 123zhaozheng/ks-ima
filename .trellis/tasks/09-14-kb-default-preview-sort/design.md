# 设计：知识库默认预览首文件 + 列表排序

## 总览

两个独立但同区域的改动：A 默认预览（纯前端）、B 列表排序（全栈）。B 是主体，涉及后端 SQL/契约/游标与前端 UI/数据层。

## B. 列表排序（全栈）

### 排序模型

引入排序参数 `sort`，取值（前端下拉选项一一对应）：

| sort 值 | 含义 | SQL ORDER BY |
|---|---|---|
| `manual`（默认） | 手动排序，保持现状 | `order_key, lower(title), id` |
| `name_asc` | 名称升序 | `lower(title), id` |
| `name_desc` | 名称降序 | `lower(title) DESC, id DESC` |
| `created_desc` | 上传时间新→旧 | `created_at DESC, id DESC` |
| `created_asc` | 上传时间旧→新 | `created_at, id` |

分组（文件夹/文件优先）单独一个参数 `group`：
- `folders_first`（默认）：`kind='folder'` 排前。
- `files_first`：文档排前。
- 实现为 ORDER BY 前缀 `(CASE WHEN kind='folder' THEN 0 ELSE 1 END)` 升/降。对 `manual` 也生效。

### 后端改动

1. **`contents` 接口**（`backend/src/ima/api/v1/knowledge.py:175`）：新增 query 参数
   - `sort: pattern ^(manual|name_asc|name_desc|created_asc|created_desc)$`，默认 `manual`
   - `group: pattern ^(folders_first|files_first)$`，默认 `folders_first`
   透传给 service。

2. **`ContentRow` 契约**（`knowledge_contracts.py:86`）：新增 `created_at: datetime = Field(alias="createdAt")`。folders 与 documents 表均已有 `created_at timestamptz NOT NULL`（迁移 0003/0005 确认），SQL 直接取出。

3. **`list_contents` SQL**（`application/knowledge.py:149`）：
   - CTE 两臂（folders / documents）都补选 `created_at`。
   - 按 `sort`/`group` 生成动态 `ORDER BY` 与 `WHERE` 翻页条件。排序键白名单化（防注入），非 `manual` 时不依赖 `order_key`。
   - 翻页「在某值之后」用所选排序键的行值比较（keyset pagination），与现有 `(order_key,title,id)` 三段式同思路，改为所选键 + `id` 收尾。

4. **游标 `ListingCursor`**（`domain/knowledge.py:25`）：扩展载荷，把排序上下文纳入，防止跨排序复用：
   - 新增字段 `sort`、`group`，以及当前排序键的最后值（manual→order_key；name→name；created→created_at 的 ISO 串）。
   - `decode` 校验 `sort`/`group` 与本次请求一致，不一致抛 `LISTING_CHANGED`（409），前端据此重取首页。版本号 `v` 升至 `2`，旧 `v1` 游标视为失效（decode 失败 → 已有 `INVALID_CURSOR`/重取路径）。

### 前端改动

1. **schema 重新生成**：`bun run generate:api` 更新 `ContentRow.createdAt` 与 `contents` 新参数。

2. **`knowledgeClient.contents`**（`knowledge-client.ts:33`）：options 增加 `sort`、`group`，拼进 query string。

3. **`useFolderContents`**（`use-knowledge.ts:46`）：options 增加 `sort`/`group`，纳入 `queryKey`（排序变了自动重取，不复用旧缓存）。

4. **排序状态**：新增轻量 composable / store（如 `useKbListSort`），读写 localStorage 键（如 `kb-list-sort`），值为 `{ sort, group }`，默认 `{ manual, folders_first }`。

5. **`KnowledgeBase.vue`**：在「新建笔记」按钮旁加排序 `q-btn`（icon `sym_o_swap_vert`，`data-testid="kb-sort"`）+ `q-menu`：
   - 分组两段：文件夹优先 / 文件优先（radio 或勾选态）。
   - 排序字段 + 方向：默认（手动）/ 名称↑↓ / 上传时间↓↑。
   - 选中态勾选，改动即写入 store → 触发列表重取。
   - 把 `sort`/`group` 透传给 `KnowledgeList`。

6. **`KnowledgeList.vue`**：接收 `sort`/`group` props 传给 `useFolderContents`；`loadMore` 沿用「游标失效→重取首页」逻辑（后端排序变化返回 LISTING_CHANGED 时已有处理）。

## A. 默认预览第一篇（纯前端）

`KnowledgeBase.vue`：
- 监听「当前文件夹内容首屏加载完成且无 `?doc=`」：取当前排序结果中第一篇 `kind !== 'folder'` 的文档，若存在则 `router.replace({ query: { ...route.query, doc: firstDocId } })`。
- 需要拿到列表数据：让 `KnowledgeList` 通过 `defineExpose` 暴露首屏 items，或把 contents query 提升到 `KnowledgeBase` 共享（倾向后者：用 `useFolderContents` 同一 queryKey 在父级读取缓存，零额外请求）。
- **不强制重开**：增加会话级标记，用户点「关闭预览」（`previewCollapsed=true`）后，本次挂载内不再自动 replace；仅当 `?doc=` 缺失且用户未手动关闭时才自动选中。
- 空文件夹 / 仅含子文件夹：不跳转，保持空态。

## 兼容性 / 风险

- **游标破坏性变更**：`ListingCursor` 升到 v2，旧 v1 游标全部失效 → 影响仅在翻页中排序/会话瞬间，前端重取首页即可，无持久影响。接受。
- **排序与手动 orderKey 共存**：`manual` 路径 SQL 完全不变，回归风险集中在新增分支；用参数化测试覆盖各排序。
- **kind 过滤与排序组合**：`kind=file|note` 时无文件夹臂，group 参数无影响，逻辑天然兼容。
- **大数据量**：keyset 分页不随排序键改变而退化；`created_at` 有索引可依（documents 表 `ix_documents_folder` 含 order_key，如需可为 created_at 加索引——初版数据量小可不加，记为后续优化）。

## 不做（Out of scope）

- 拖拽手动排序 UI（orderKey 仍由后端/既有逻辑维护）。
- 跨文件夹全局排序、搜索内排序。
- 文件夹树排序。
