# Agent 化提问与范围指定（父任务）

来源：2026-09-12 用户提议——「快速引入 PydanticAI 实现 agent 化提问；用户要能
指定询问指定篇章或指定目录」。

## 背景事实（2026-09-12 代码核实）

- ask 现为固定单轮管线（`application/search.py::ask`）：检索 → 引用组装 →
  prompt → `managed_chat_stream` 流式生成；安全不变量：生成前第二次授权检索
  复核（ACCESS_REVOKED）、引用按 chunk digest + 文档版本落库、无结果走
  knowledge_gap。
- 可复用工具已存在：`application/mcp.py` 的 `list_knowledge_bases` / `list_dir` /
  `search` / `ask`，均带逐次授权与并发租约。
- 模型网关 `managed_chat_stream(..., tools=None)` 已支持 OpenAI 风格 tools 参数。
- **断链**：composer 已有目录范围选择器（`ask-scope-chip` + FolderPickerList），
  但 `AskRequest` 仅 `question`/`conversationId`，AskHome 调用未传 scope。
- `pydantic-ai` 当前不是项目依赖。

## Goal

提问升级为双轨：默认单轮管线（快）+ agent 模式（多跳/自然语言范围）；显式范围
（目录/篇章）在全链路真实生效。

## 任务地图

| 子任务 | 交付物 | 依赖 |
|---|---|---|
| `09-12-ask-scope-wire`（P1） | 显式 scope 端到端接通 | 无 |
| `09-12-ask-agent-loop`（P2） | agent 模式提问 | P1 的 scope 过滤基础 |

## 跨子任务验收标准

- [ ] 引用/权限不变量不回归：引用仅来自授权检索结果、最终复核保留、落库字段不变。
- [ ] 默认单轮行为（不传 scope、非 agent）与现状完全一致（延迟、事件序列、文案）。
- [ ] 后端 pytest + 前端 lint/test:unit/vue-tsc/build 全绿。
- [ ] OpenAPI 契约同步更新（`frontend/generated/openapi.json` + 前端 schema 重新生成）。
