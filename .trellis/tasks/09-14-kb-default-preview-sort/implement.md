# 执行计划：知识库默认预览首文件 + 列表排序

按序执行；每步带验证命令。B（排序）先行，A（默认预览）依赖列表数据层就绪。

## 1. 后端：契约 + 游标
- [ ] `knowledge_contracts.py` `ContentRow` 增加 `created_at: datetime = Field(alias="createdAt")`
- [ ] `domain/knowledge.py` `ListingCursor` 扩展为 v2：载荷加 `sort`、`group`、`lastValue`（当前排序键最后值）；`decode` 校验版本与必填键
- 验证：`cd backend && uv run pytest tests/ -k listing -q`（或相关游标测试）

## 2. 后端：contents 接口 + SQL
- [ ] `api/v1/knowledge.py:175 contents` 增加 `sort`、`group` query 参数（白名单 pattern），透传 service
- [ ] `application/knowledge.py:149 list_contents`：
  - CTE 两臂补 `created_at`
  - 按 sort/group 生成白名单化 ORDER BY + keyset 翻页 WHERE
  - 游标写入/校验 sort+group，不一致抛 LISTING_CHANGED
  - 返回 items 带 `createdAt`
- [ ] 后端单测：参数化覆盖 5 种 sort × 2 种 group 的排序正确性与翻页不重不漏、跨排序游标报 LISTING_CHANGED
- 验证：`cd backend && uv run pytest tests/ -k contents -q`

## 3. 前端：schema + 数据层
- [ ] `bun run generate:api` 重新生成 schema（确认 `ContentRow.createdAt` 与 contents 新参数）
- [ ] `knowledge-client.ts:33 contents` options 加 `sort`/`group`
- [ ] `use-knowledge.ts:46 useFolderContents` options 加 `sort`/`group`，纳入 queryKey
- 验证：`bun run lint`

## 4. 前端：排序状态 + 排序按钮 UI
- [ ] 新增 `useKbListSort`（localStorage `kb-list-sort`，默认 `{ sort:'manual', group:'folders_first' }`）
- [ ] `KnowledgeBase.vue`：新建笔记旁加排序 `q-btn`（`data-testid="kb-sort"`，icon `sym_o_swap_vert`）+ `q-menu`（分组 / 字段 / 方向 / 默认），改动写入 store
- [ ] 透传 `sort`/`group` 给 `KnowledgeList` → `useFolderContents`
- 验证：浏览器实测切排序后列表重排、翻页正确、刷新保留

## 5. 前端：默认预览第一篇
- [ ] `KnowledgeBase.vue`：父级共享 `useFolderContents`（同 queryKey）读取首屏 items
- [ ] 无 `?doc=` 且首屏有非 folder 文档 → `router.replace` 写入 `doc=首篇id`
- [ ] 会话级「用户已手动关闭」标记：关闭后本次挂载不再自动选中
- [ ] 空/仅文件夹不跳转
- 验证：浏览器实测进 KB、切文件夹、空文件夹、手动关闭四场景

## 6. 质量关卡
- [ ] `bun run lint` 通过
- [ ] `bun run test:unit` 通过
- [ ] `cd backend && uv run pytest -q` 相关测试通过
- [ ] 浏览器实测：桌面 + 窄屏（预览抽屉）两形态；viewer/已归档只读语义不破
- [ ] dist 构建无 Chrome 109 禁用语法（如涉及构建）：`color-mix|oklch|@container` 零命中

## 回滚
- 后端排序为新增可选参数（默认 manual=现状），前端不传即旧行为；游标 v2 与 v1 不兼容但仅影响翻页瞬间，回滚恢复旧 SQL 分支即可。
- 默认预览为纯前端增量的 `router.replace`，回滚删除该 watch 即可。

## 关键文件
- `backend/src/ima/api/v1/knowledge_contracts.py`、`knowledge.py`
- `backend/src/ima/application/knowledge.py`、`domain/knowledge.py`
- `src/api/knowledge-client.ts`、`src/composables/use-knowledge.ts`
- `src/pages/KnowledgeBase.vue`、`src/components/KnowledgeList.vue`
