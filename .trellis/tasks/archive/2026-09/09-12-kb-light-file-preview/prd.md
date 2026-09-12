# P10：轻量文件预览（PDF/图片/DOCX/XLSX/PPTX）

## 背景与诊断

老师反馈文档「无法预览」。诊断结论：前端 `DocPreview.vue` 是裸 `<iframe>`
套后端预签名 URL，没有用任何预览库；后端
`backend/src/ima/application/storage.py` 的预览白名单只放行
`text/plain`、`text/markdown`、`application/json`，PDF/DOCX/XLSX 一律
`409 PREVIEW_UNAVAILABLE` → 前端显示「暂不支持预览」。

上传支持的格式（`.txt,.md,.json,.pdf,.docx,.xlsx,.xls`）与白名单严重不匹配，
这是产品缺陷而非偶发 bug。

## 选型决策（轻量路线，2026-09-12 GitHub+npm 实测）

| 格式 | 方案 | 体积(unpacked) | License | 备注 |
| --- | --- | --- | --- | --- |
| PDF / 图片 | **零依赖**：白名单放行 + iframe 原生渲染 | 0 | — | Chrome 内置 PDF viewer；预签名已带 `Content-Disposition: inline` |
| DOCX | `docx-preview` v0.4.0 | 952KB，1 dep | Apache-2.0 | 2026-07 更新；保真度优于 mammoth |
| XLSX/XLS | `xlsx`(SheetJS CE) v0.18.5 | 7.3MB | Apache-2.0 | 懒加载分包，仅预览表格时加载；npm 版冻结但仍是标准 |
| PPTX | `pptx-preview` v1.0.7 | 1.7MB，5 deps | ISC | 纯前端唯一轻量选项，保真中等 |
| TXT/MD/JSON | 维持现状（白名单内） | — | — | 已有路径 |

**被淘汰方案**：`@vue-office/*`（excel 13.5MB/pdf 16.4MB unpacked 且
2024-12 停更）；`flyfish-dev/file-viewer`、`open-file-viewer`（全格式 SDK
含 WASM/CAD/3D 管线，超出「轻量」要求）；kkFileView/OnlyOffice（服务端
Java/LibreOffice，运维成本高，OnlyOffice 为 AGPL）。

调研证据：`.trellis/.runtime/gh-preview-search.jsonl`、
`.trellis/.runtime/gh-readmes/`（归档至本任务 research/）。

## 技术方案

### 后端（storage.py）

预览白名单扩展为：`text/plain`、`text/markdown`、`application/json`、
`application/pdf`、`image/*`（前缀匹配）。DOCX/XLSX/PPTX **不进白名单**——
它们的 `preview` 请求仍返回 `PREVIEW_UNAVAILABLE`，由前端识别后改走
「授权下载 → 浏览器内解析」路径（下载走 `KbAction.DOWNLOAD` 授权，语义正确）。

### 前端（DocPreview.vue）

1. 新增格式分发：`document.mimeType`（或文件名后缀兜底）决定渲染器：
   - `pdf`/`image/*`/文本类 → 现有 iframe 路径不变；
   - `docx` → `docx-preview` 渲染进容器 div；
   - `xlsx`/`xls` → `xlsx` 解析首个 sheet 转 HTML 表格；
   - `pptx` → `pptx-preview` 渲染进容器 div。
2. 三个渲染器全部 `import()` 动态引入（懒加载分包），主包体积不变。
3. 文件字节获取：先尝试 `fetch(预签名下载 URL)` → `ArrayBuffer`
   （MinIO 预签名 GET 默认允许跨域；接入时在 dev 环境实测验证，若被 CORS
   拦截则降级为后端新增同源流式代理端点——列为实现期验证项）。
4. 渲染状态机：loading / unsupported / error 复用现有 `PaneEmptyState` 与
   `previewFailure` 语义；所有既有 testid 保持不变。

### 安全不变量

- 预览/下载授权判定不变（`VIEW_CONTENT`/`DOWNLOAD` 双动作语义保持）。
- 不引入任何服务端转换组件；文件字节不离开内网。
- 渲染产物一律走既有 `v-html` 消毒或库自身的 DOM 构建（docx-preview 直接
  构建 DOM；xlsx 输出 HTML 需经 DOMPurify 消毒后注入）。

## 验收标准

1. PDF 与 PNG/JPG 在 `/kb` 右侧预览面板直接可见（iframe 原生）。
2. DOCX/XLSX/PPTX 样本文件在浏览器内渲染出可读内容；失败时有明确空态与
   下载回退按钮。
3. `bun run build` 产物中三个渲染器为独立懒加载 chunk。
4. 质量门：前端 lint/vitest(79+)/vue-tsc 全绿；后端单测全绿，白名单新增
   MIME 有对应测试（含 `image/*` 前缀匹配与 docx 仍走 PREVIEW_UNAVAILABLE
   的断言）。
5. 视觉验证由用户在浏览器进行。

## 范围外

- OFD/CAD/音视频/3D 等长尾格式；PPTX 动画级保真（真出现投诉再评估
  kkFileView 服务端兜底）。
- 不改上传格式集合、不改存储与授权模型。
