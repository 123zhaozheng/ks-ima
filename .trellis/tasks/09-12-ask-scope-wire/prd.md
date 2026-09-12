# P1 接通提问范围指定（目录/篇章断链修复）

父任务：`09-12-ask-scope-agent`。

## Goal

composer 已有的范围选择器真正生效：用户可指定「整个知识库 / 某目录 / 某篇文档」
提问，检索与引用严格限定在范围内。

## Requirements

- 后端：`AskRequest` 增加可选 `scope`：`{ folderId?: string, documentId?: string }`
  （二者互斥；缺省=整库，行为与现状完全一致）。`retry` 端点同样接受并沿用 scope。
- 检索过滤：ask 内两次 `search` 调用（初检 + 复核）都按 scope 过滤；`search` 已
  支持 `folderId`，补 `documentId` 过滤（若缺失）。scope 目标必须属于当前 kb 且
  用户对之有权限，否则 422/404（沿用现有错误码风格）。
- 引用不变量：引用仍只来自授权检索结果；scope 下复核同样生效。
- 前端：AskHome/ConversationView 把 composer `scope` 传入 ask/retry 请求体；
  `ask-scope-chip` testid 不变；scope 在会话创建后作为会话属性延续（重试/追问
  沿用，或 UI 明确提示——实现时在 design 中定）。
- knowledge_gap：scope 内无结果时提示语体现范围（如「该目录下未找到相关内容」）。
- OpenAPI：更新 `frontend/generated/openapi.json`，重新生成 `src/api/generated/schema.ts`。

## Acceptance Criteria

- [ ] 指定目录提问：引用全部落在该目录（含子目录）文档内；指定文档：仅该文档。
- [ ] 不传 scope 的提问与现状逐字节一致（事件序列、文案、落库）。
- [ ] 无权限/跨库 scope 返回明确错误码，不产生半完成消息。
- [ ] 后端相关 pytest（scope 过滤、越权、互斥校验）+ 前端 `bun run lint` /
      `test:unit` / `vue-tsc` 通过。
