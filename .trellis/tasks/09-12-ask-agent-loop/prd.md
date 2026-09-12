# P2 agent 模式提问（PydanticAI 评估与落地）

父任务：`09-12-ask-scope-agent`（design.md §B）。依赖：P1 的 scope 过滤。

## Goal

ask 增加 agent 模式：模型通过工具循环自主检索（多跳、自然语言指定目录/篇章），
过程对用户可见，引用与权限不变量不回归。

## Requirements

- **选型先行**：实现前完成 PydanticAI vs 最小自研 tool-call loop 的对比调研
  （落 `research/agent-loop-options.md`），经用户确认后落地。网关
  `managed_chat_stream` 已支持 tools 参数，自研 loop 无需改协议层。
- 工具集：复用 `application/mcp.py` 的授权检索函数封装为 agent 工具：
  `search_knowledge(query, folderId?, documentId?)`、`list_dir(folderId?)`、
  `get_document_outline(documentId?)`；每个工具逐次做 kb 授权（与 MCP 同一套
  `authorize_tool` 语义），工具调用走并发租约。
- 模式开关：`AskRequest.agent: bool`（缺省 false=现有单轮管线，逐字节不变）；
  agent=true 且模型无 tool_call 能力时返回明确错误码（复用能力检测体系，
  参考 rerank 能力识别任务的做法）。
- SSE 扩展：新增 `tool_call` 事件（工具名 + 参数摘要 + 结果条数），前端在回复
  上方渲染可折叠的「检索过程」区；现有事件序列不变。
- 引用不变量：引用仅采信 agent 工具返回的 chunk；生成结束后仍执行一次授权复核
  检索（与单轮相同的 ACCESS_REVOKED 语义）；落库字段不变。
- 限额：工具循环硬上限（如 6 轮）+ 总 token 上限，超限优雅收尾为当前答案或
  knowledge_gap。
- P1 的显式 scope 与 agent 模式可叠加：scope 作为工具参数的强制过滤器注入。

## Acceptance Criteria

- [ ] 调研报告经用户确认，选型结论与理由落盘 research/。
- [ ] agent 模式可回答多跳问题（如「对比 A 目录和 B 文档的说法」），过程事件可见。
- [ ] 引用全部可追溯且经授权复核；越权内容不进入上下文。
- [ ] agent=false 路径回归无损；tool_call 能力缺失时报明确错误而非 500。
- [ ] 后端 pytest（工具授权、循环上限、引用复核、能力缺失）+ 前端质量门全绿。
