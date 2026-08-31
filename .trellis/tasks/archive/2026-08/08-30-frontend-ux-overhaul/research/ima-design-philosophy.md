# Research: Tencent ima — Design Philosophy Reference for Knowledge-Assistant UX

- **Query**: Product/IA, layout & visual language, chat/citation UX, notes/files UX, distilled design principles, and public screenshots/articles of Tencent's public "ima" product (ima.qq.com / ima.copilot), as a design-philosophy reference for an intranet knowledge-assistant redesign.
- **Scope**: external (web research, Chinese + English sources)
- **Date**: 2025-08-30

> Note: ima iterates fast (features/UI changed notably between v1.0 late-2024 and the 2025 web/app versions). Where a detail is version-specific or evidence is thin, this is stated explicitly. No UI detail below is invented; everything is sourced, and gaps are flagged in "Caveats".

---

## 1. Product / IA Overview

### What ima is
- **ima (ima.copilot)** — Tencent's "AI 知识管家 / AI intelligent workbench", launched Oct 25 2024 (Mac) / announced Nov 15 2024 (Windows). Official tagline: "以知识库为基础的AI知识管家，提供'搜-读-写'一站式体验" (a knowledge-base-centric AI butler offering an integrated **search–read–write** experience).
- Positioning per the product team (GeekPark interview): "ima 是一款效率工具，我们将它定位为基于 AI 能力的「搜、读、写」工作台" — an efficiency workbench for search, reading, and writing on top of AI.
- Powered by a **dual-model architecture**: Tencent Hunyuan (general QA) + DeepSeek-R1 (deep reasoning), user-switchable. Built on RAG; the knowledge base exists precisely to ground answers and reduce hallucination.
- **Platform strategy (intentional per-endpoint role split)**: PC client = deep content-creation workbench; mobile app = fragment capture in/out; WeChat mini-program "ima知识库" = high-frequency file import from WeChat; web version (launched July 2025) + browser extension (May 2025) extend reach. PC-first because "PC is where people process the most information daily".

### Primary surfaces
| Surface | Chinese label | Role |
|---|---|---|
| Copilot chat / home | 新对话 / 问问ima | The default hero surface: one composer for asking, creating, interpreting |
| Knowledge base | 知识库 (个人/共享) | The product's core: files/articles/notes/web pages the AI can ground answers in |
| Knowledge plaza / discovery | 知识库广场 / 发现广场, 知识号 | Public shared knowledge bases; browse, join, publish |
| Notes | 笔记 | Personal authored content; rich editor; feedable into the knowledge base |
| Q&A history | 问答历史 | Conversation history, revisit/reuse |
| Document interpretation | 文档解读 / AI解读 | Upload a doc → summary, mind map, podcast, quiz |
| Smart writing | 智能写作 | Scenario-based generation (paper, report, Xiaohongshu copy…) with reference uploads |
| (Newer) Task mode / copilot agent | 任务模式 | Agent mode that plans multi-step tasks across tools |

### Navigation organization
- **Web version (ima.qq.com, current)**: two-part layout = **left sidebar + main pane**. Sidebar contains four core modules: **新对话 (New chat), 知识库 (My knowledge base), 发现广场 (Discovery plaza), 问答历史 (Q&A history)**, plus footer items 关于ima / 登录 / 打开电脑版. Source: QQ Reading book 《AI知识库极简入门》 §2.1, which includes a full screenshot (Figure 2-1), and the live ima.qq.com page (extracted labels: 新对话 / 知识库 / 发现广场 / 问答历史).
- **Desktop client (launch-era v1.x)**: home screen = user avatar top-left + "四个按钮与一个搜索框" (four buttons and one search box): search/ask box (accepts text, docs, screenshots, even a pasted URL), buttons for 文档解读 (document interpretation) and 智能写作 (smart writing), plus attach (paperclip) upload; **left side rail holds 知识库 and 笔记**, with quick actions to upload local files to the knowledge base, create a note, and view history. The knowledge-base icon is described as a **lightbulb ("灯泡") icon**.
- In the knowledge base area, personal vs shared libraries are split views; the plaza/discovery ("发现") lives as a tab to the right of shared libraries, plus a home-page "知识库广场" entry added in 2025.

### Primary user journey: open app → grounded answer with citations
1. **Open app** → land on a minimal home dominated by a single composer ("提出问题或输入网址" — ask a question or paste a URL). Login is WeChat QR scan (one tap).
2. **Build/import knowledge**: drag files into the client (dragging a desktop file auto-launches ima), upload via "+" (PDF/Word/PPT/images/Markdown/TXT/audio…), import WeChat chat files or 公众号 articles via the mini-program, or save web pages. Content is **auto-parsed, indexed, and summarized** by the model.
3. **Scope the question**: choose "基于全网" (whole web) vs "基于知识库" (my knowledge base); optionally target precisely via `@知识库名称 问题` mention, `#标签` tag, or by opening a specific folder before asking. In-composer model picker (e.g. 混元快速/深度思考, DeepSeek) sits at the composer's bottom-left; file attach sits left of the send button.
4. **Get a grounded answer**: structured response with **numbered citation marks (角标/数字标)**; clicking a mark jumps to the source passage — since the Nov 2025 update it **deep-links into the original PDF/web page and highlights the cited paragraph**. Answers from public knowledge bases link back to the published source paragraph.
5. **Close the loop**: save any answer to a note (记笔记 button), save an entire Q&A/web page to the knowledge base (lightbulb button top-right), add notes back into the knowledge base → the "搜-读-写-存" (search–read–write–store) flywheel, described by the team as "边问边看，边搜边记" (ask while reading, record while searching).

---

## 2. Layout & Visual Language

### Layout skeleton
- **Two-region skeleton**: narrow left navigation rail + large main content pane. This holds for both the web app (sidebar + chat/content area) and the client. It is NOT a three-pane layout; the second pane changes purpose by context (chat stream, file list, document reader, note editor).
- When reading content (article/web/PDF), AI enters contextually: a "问问ima" (Ask ima) entry appears at the **top-right of the reader**, offering summary/Q&A/mind-map without leaving the reading surface.
- Composer layout (web, current): model switcher **bottom-left inside the input box**, attach/upload button **immediately left of the send button** at bottom-right.

### Density & tone
- Repeated reviewer language: "界面非常简洁" (very concise), "干净的搜索框" (clean search box), "外观直观简洁" (intuitive and simple appearance), "像传统搜索引擎的主页" (home page resembles a traditional search engine's). The deliberate impression is **calm, airy, low-chrome**: avatar + one box + a few buttons.
- Exact palette/typography tokens are NOT documented in text sources (see Caveats). Screenshots show a light UI with soft neutral backgrounds and a friendly mascot-style logo (app icon described as panda-like). Treat visual styling as "light, minimal, content-first" only at the level of reviewer descriptions.

### Lists / trees of knowledge items
- Knowledge base renders as a **list of items with AI-generated summaries** (uploaded docs get auto-parsed summaries). Early versions lacked a dense list mode ("一屏难以浏览太多项") — a documented user pain point; multi-level **folders** were added in April 2025 after explicit user demand, plus sort-by-upload-time and tag filtering (#标签, batch or single).
- Shared library cards include name, cover image, member counts, and (for 知识号) curated "recommended questions" that owners configure (typically 3) so newcomers immediately know what the library answers.
- Discovery plaza: card grid of public knowledge bases with titles, cover images, join counts, category browsing (finance, law, medical, education…), plus "问问知识库" recommendations driven by user history.

### Empty states / onboarding
- **Composer-as-onboarding**: the home is essentially an inviting empty state — one big input box with suggestive placeholder ("提出问题或输入网址") and in-box smart question hints (提问框内智能提问指引).
- The current web home fills the empty canvas with **curated example cards** ("精选示例") showing generated reports/PPTs/podcasts with usage counts, tabbed by output type (全部/生成报告/生成PPT/生成播客) — learn-by-example rather than a tour.
- Onboarding friction minimized: WeChat QR login ("扫码视为已阅读并同意…"), no setup wizard documented; the product teaches via drag-and-drop ("把有价值的信息放进去，像建文件夹存东西，就很简单").

---

## 3. Chat / Citation UX

### Answer presentation
- Answers are **structured** (structured language, clear sections); for document QA, ima **auto-matches relevant charts/figures** from the source into the answer ("图文并茂：针对文档问答，自动匹配相关图表").
- Deep-research mode produces a multi-angle breakdown **with a visible research outline** (研究大纲).
- Think-mode models show a **visible thinking process** before output (e.g. "Tencent HY 2.0 Think", "DeepSeek V3.2 Think").
- Streaming is implied by product type (chat composer) but no source documents the exact streaming animation; do not assume specifics.

### Citations / sources (the trust layer)
- Answers carry **numbered superscript citation marks**; clicking one **jumps to and locates the source passage**. Since 2025-11-04: "原文索引跳转" — click jumps into the original PDF or web article at the cited position **and highlights the cited paragraph**, explicitly solving "where did this number come from".
- For answers synthesized from public/shared knowledge bases, the trailing number marks auto-link to the published content and "直接定位到原文段落" (position directly at the original paragraph).
- KB-scoped answers stay faithful to the corpus (tested: answers over a 120k-word personal corpus did not leak outside it; out-of-scope questions get refused).

### Knowledge scope selection (first-class control)
- Global toggle: **基于全网 vs 基于知识库** — switchable before or after asking (ask on home → get web answer → manually switch to "基于知识库"; or inside a KB use "AI 搜索" → click "基于知识库回答…" instead of pressing Enter).
- Precision targeting inside the composer: **`@知识库名称`** mentions (single or multiple libraries in one question), **`#标签`** tag scoping, or open a folder then ask.
- Model selection is also in-composer (bottom-left): quick vs think variants.
- Note (documented criticism): these multiple scoping paths were historically inconsistent/confusing (see hub.baai PM review) — a redesign lesson as much as a pattern.

### Follow-ups & continuity
- Follow-up questions continue in-context; after interpreting a document, ima **proactively proposes extension questions** ("延伸问题") to deepen exploration.
- Every Q&A can be persisted: per-answer "记笔记", whole-conversation save to KB, session history sidebar (问答历史) with search (added in recent versions).

---

## 4. Notes / Files UX

### Notes (笔记)
- **Creation**: sidebar → 笔记 → 新建; or AI answers saved as notes; notes live in a flat list (right-click delete).
- **Editor**: a full document editor ("类似腾讯文档/Word"), not a lightweight memo pad. Supports Markdown: headings, lists, code blocks, tables, formulas, blockquotes.
- **AI-in-editor**: type **"/"** to summon AI (pick model + prompt); select text → contextual actions: 扩写 (expand), 缩写 (shrink), 翻译 (translate), 润色 (polish), extract key points; one-click image generation for illustrations.
- **Bridge to knowledge**: a top-right icon adds any note into a knowledge base — notes are authored content; the KB is collected content (a deliberate, if sometimes confusing, distinction).

### Files / knowledge items
- **Intake everywhere**: "+" in KB page, paperclip on home composer, drag-and-drop onto the client (auto-launches ima when dragging a file), WeChat mini-program import (chat files, 公众号 articles via "更多打开方式"), URL/web-page save, browser extension, Tencent Docs one-click import (Nov 2025). 19+ formats incl. PDF, Office family, Markdown, TXT, images (OCR), audio (2h 录音纪要 with auto transcript), xmind.
- **Auto-processing on ingest**: parsing + indexing + AI summary; one-click 思维导图 (mind map), 有声播客 (audio podcast), 知识小测验 (quiz) from any document.
- **Organization**: tags (batch/single), multi-level folders (added 2025-04 by user demand), sort by upload time, per-library capacity ~1GB (30GB total free cloud as of 2025), shared-library permissions (approval on/off, view/edit rights, member removal), publish-to-plaza with cover + recommended questions.
- **Reading**: opening a saved article/PDF shows a reader with "问问ima" top-right; text selection inside readers offers an "解读" (interpret) button that explains terms, links related material, and can produce a mind map.

---

## 5. Design Philosophy — 10 Principles for the Redesign

Distilled from the ima team's own statements (GeekPark/极客公园 interview, BAAI hub) plus consistent reviewer observations. Each is actionable for an intranet knowledge assistant with folders + markdown notes + files + RAG copilot + MCP connectors + centralized admin.

1. **One composer is the home page.** The default surface is a single, generous input box (text, file, screenshot, even URL) — search-engine level of calm. All other powers are reachable but not shouting. Onboarding = an inviting empty composer + curated example cards, not a tour.
2. **Left rail = nouns, main pane = verbs.** Persistent narrow sidebar holds the durable objects (New chat, Knowledge base, Discovery, Notes, History); the main pane morphs by task. Two regions, not a busy dashboard.
3. **Knowledge scope is a first-class, always-visible control.** "Answer from the whole web" vs "answer from my knowledge base" is an explicit toggle, with precision targeting (`@library` mention, `#tag`, ask-inside-folder) adjacent to the composer. For our app: scope selector (folder/library/connector) must sit next to the composer, never buried in settings.
4. **Citations are clickable deep links, not footnotes.** Numbered marks in the answer that jump into the original document and **highlight the exact passage**. Traceability is the trust mechanism; make "where did this come from" one click.
5. **The knowledge base is a visible, browsable object — a "second brain", not an agent.** The team deliberately exposes the corpus ("把整个'知识大脑'放出来"): users can open it, read items without asking anything, and manage it like folders. RAG's technical concept is elevated into an interactive surface. A KB is "a simpler agent" — but never call it an agent.
6. **AI meets users where they are.** Contextual AI entries everywhere: "问问ima" on every reader top-right, "/" inside the note editor, selection → interpret/expand/translate, drag-a-file auto-invokes the app. The copilot is not confined to the chat tab.
7. **Everything flows into everything: close the loop.** Answer → note → knowledge base → better answers ("搜-读-写-存", "边问边看，边搜边记"). Any AI output must be one-click persistable back into the corpus; that flywheel is the retention engine.
8. **Low floor by metaphor, not by explanation.** "Putting info in should feel like making a folder" — use familiar file/folder metaphors, QR-code login, drag-and-drop; hide model/agent complexity behind scenario language (quick / deep-think) instead of jargon.
9. **Knowledge becomes publishable, social capital.** Shared libraries with permission gates, a public plaza with covers/join-counts/recommended questions, certified "知识号" accounts, analytics for creators. Even intranet-internal: make sharing/publishing a first-class flow with owner-configured recommended questions.
10. **Stay calm; iterate from user pain.** Reviewers consistently praise the minimal chrome and criticize inconsistency (multiple divergent paths to "ask the KB"; notes vs KB conceptual split). Lesson: minimal surface area is the brand, but every capability needs exactly ONE obvious path; ship small fixes from user feedback (folders, list density, sorting all arrived via user requests).

---

## 6. Public Screenshots, Articles & Reviews

### Official
- Official site (product gallery images hosted at img.ima.qq.com): https://ima.qq.com
- Web app (live sidebar labels visible): https://ima.qq.com/chat
- App Store listing (official screenshots, feature bullets, changelog): https://apps.apple.com/hk/app/ima-%E8%85%BE%E8%AE%AFai%E7%9F%A5%E8%AF%86%E7%AE%A1%E5%AE%B6/id6737188438

### UI walkthroughs with screenshots
- 《AI知识库极简入门》 §2.1 — definitive web-UI anatomy with full screenshot (Figure 2-1): https://m.molobook.qq.com/read/1059480554/12
  - Screenshot URL: `https://epubservercos.yuewen.com/84CEA4/36029873407571706/epubprivate/OEBPS/Images/26_01.jpg`
- 智东西 (zhidx) deep 3-day review, incl. ima home-page screenshot ("1个搜索框、4个按钮"): https://zhidx.com/p/455808.html
  - Home screenshot: `https://oss.zhidx.com/uploads/2024/11/673f08f142a12_673f08f13f379_673f08f13f359_WX20241121-162859@2x.jpg` ; launch-era UI: `https://oss.zhidx.com/uploads/2024/11/673d92b8135c5_673d92b80c91b_673d92b80c8f5_WX20241120-154137@2x.png/_zdx`
- 设计达人 step-by-step build guide (16+ labeled screenshots of KB, sharing, notes, `/` AI): https://www.shejidaren.com/ima-coplit-teng-xun-mian-fei-ai-zhi-shi-ku-tai-niu-le-5-fen.html
- 腾讯云开发者社区 "3分钟教会你腾讯ima" (client home + mini-program screenshots): https://cloud.tencent.com/developer/article/2498271
- 53AI 高阶用法解析 (WeChat import triptych, @-mention QA screenshots): https://www.53ai.com/news/zhishiguanli/2025071526940.html

### Reviews / analysis (incl. critical UX takes)
- 人人都是产品经理 深度测评: https://www.woshipm.com/ai/6266704.html
- 智源社区 (BAAI) PM-perspective critical review — best source on UX inconsistencies (KB vs notes split, scoping paths, lightbulb button discoverability): https://hub.baai.ac.cn/view/41554
- 智源社区 (BAAI) 极客公园 interview with the ima product team — primary source on design philosophy: https://hub.baai.ac.cn/view/45807
- 百度百科 entry (timeline, plaza/知识号 operations, team, storage decisions): https://baike.baidu.com/item/ima/65111768 (English: https://baike.baidu.com/en/item/ima/1501962)
- 知乎 "如何看待腾讯推出ima.Copilot" (practitioner answers incl. UI): https://www.zhihu.com/question/4541284317/answer/1937222551131649068
- 知乎 知识库广场升级走读 (discovery tab location): https://zhuanlan.zhihu.com/p/29275623727
- Release-notes garden (citation deep-link + Tencent Docs import, 2025-11-04; web launch 2025-07-22): https://weqoocu.com/3105.html
- 腾讯云 乐享×ima enterprise overview (enterprise framing, quick/think/research modes, analytics dashboards): https://cloud.tencent.com/developer/article/2679634
- English news: https://en.tmtpost.com/news/7339647 ; https://news.aibase.com/news/13263 ; https://www.waytoagi.com/sites/2031

---

## Caveats / Not Found

- **No authoritative color/typography spec exists publicly.** "Calm, light, minimal" is reviewer consensus; exact palette, type scale, spacing, dark-mode behavior are undocumented. The redesign team should sample directly from the screenshots above (or install the client) before committing visual tokens.
- **UI varies by version and endpoint.** The launch-era Mac/Windows client (search-box home + lightbulb KB icon) differs from the 2025 web app (sidebar: 新对话/知识库/发现广场/问答历史). Details here are a composite; cite a version when reusing a specific control.
- **Streaming/typing-indicator specifics**: no source documents the exact streaming treatment; only that answers are chat-style and think-modes show reasoning first.
- **Empty-state copy**: only the composer placeholder ("提出问题或输入网址") and curated example cards are evidenced; no documented empty states for notes/KB lists.
- Some screenshot URLs (qcloudimg/shejidaren) are hotlink-protected or tokenized and may expire.
- "ima.copilot" branding also covers a newer agent/task-mode layer (2025-2026); most UI evidence predates or lightly covers that mode.
- Competing/critical sources (hub.baai PM review) describe early-version quirks that may since be fixed; treat as historical UX lessons.
