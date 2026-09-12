# 设计：Agent 化提问与范围指定

## A. P1 显式 scope（ask-scope-wire）

### 数据流

```
composer scope (PickedFolder | 未来 PickedDocument)
  → AskRequest.scope { folderId | documentId }
  → search.py::ask 初检 + 复核两次 search 均带过滤
  → 引用天然落在 scope 内
```

### 关键决策点（实现前与用户确认）

1. **会话级 scope 延续**：conversation 落库是否加 scope 列？
   - 方案 a：加列，追问/重试自动沿用（体验好，要迁移）
   - 方案 b：不落库，前端每次请求都带（无迁移，但换设备丢失）
   - 倾向：a（一次加列迁移，retry/追问语义最干净）
2. **documentId 过滤落点**：search 服务现支持 folderId；documentId 过滤加在
   chunk 检索 SQL（document_id = :doc）即可，不动索引。
3. **knowledge_gap 文案**：scope 下用「该范围下未找到相关内容」。

## B. P2 agent 模式（ask-agent-loop）

### 选型对比（实现前调研落实，此为预研框架）

| 维度 | PydanticAI | 最小自研 loop |
|---|---|---|
| 依赖 | 新增 pydantic-ai（pin 版本，Python 3.13 OK） | 零新依赖 |
| 工具 schema | 从函数签名自动生成 | 手写 OpenAI tools JSON（3 个工具，量小） |
| 流式 | 自带 stream 抽象，需映射到现有 SSE 事件 | 直接复用现有 `_deltas` 解析 |
| 与网关契合 | 需自定义 provider 指向 managed gateway（base_url+key） | 直接调 `managed_chat_stream(tools=...)` |
| 重试/观测 | 内建 | 自己写（循环上限 + 计数即可） |
| 与项目风格 | 项目 MCP/SSE 均自研 | 一致 |

**预倾向**：最小自研 loop（网关已支持 tools、项目风格一致、无新依赖），
PydanticAI 的结构化输出留作后续需要复杂结构化时再评估。最终以调研报告为准。

### Agent loop 骨架（自研方案）

```
messages = [system(带 scope 过滤说明), user(question)]
for round in 1..=6:
    stream = managed_chat_stream(kb, GROUNDED_ASK, messages, tools=TOOLS)
    若产出 tool_calls:
        逐个执行（authorize_tool + 租约 + scope 强制过滤）
        结果追加进 messages（role=tool）
        yield sse("tool_call", {name, argsSummary, hits})
    否则:
        流式产出 delta → completed，结束
超上限 → 以已检索内容收尾或 knowledge_gap
```

### 不变量（硬性）

- 引用只来自工具返回的 chunk（rank 重编号后落库，字段同现有 message_citations）
- 生成结束后一次授权复核检索，失败 → cancelled/ACCESS_REVOKED（同单轮）
- 工具内复用 `authorize_tool` 语义；POLICY_DENIED（非人类账户）规则不变
- agent=false 路径零改动

### SSE 协议扩展

- 新事件 `tool_call`：`{ name, argsSummary, hits, round }`；前端渲染为可折叠
  「检索过程」区（默认折叠，展开看每步）
- 现有 conversation/message/citations/delta/completed/knowledge_gap/cancelled/error
  事件序列与字段不变

### 回退

- agent 模式由请求级开关控制，出问题用户侧不勾即可回到单轮；后端无 schema
  破坏性变更（P1 的 scope 列可保留，不回滚）。
