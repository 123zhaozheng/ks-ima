# Structure-aware chunking with heading paths and table preservation

## Problem

The product owner asked what the current chunking strategy is, having previously asked a
developer to "follow a suitable open-source project". The current implementation is a
plain character sliding window and nothing more.

`deterministic_chunks()` — `backend/src/ima/application/ingestion.py:153-172`:

```python
stop = start + size
boundary = text.rfind("\n", start, stop)
if boundary > start + size // 2:
    stop = boundary
content = text[start:stop].strip()
start = max(stop - overlap, start + 1)
```

Defaults (`backend/src/ima/config.py:79-83`): `chunk_size=1200`, `overlap=160`,
`max_chunks=10000`.

### Confirmed defects

1. **Size is Unicode code points, not tokens.** 1200 ≈ 1200 Chinese characters, which is
   far more information than 1200 English tokens. No tokenizer, no per-model context check.
2. **No semantic boundaries.** Only `\n` is considered, and only when it falls in the
   second half of the window; otherwise it hard-cuts mid-sentence.
3. **No structure awareness.** Markdown `#` headings build no hierarchy. A heading can
   land in the previous chunk while its body lands in the next, so a retrieved chunk does
   not know which section it belongs to.
4. **Tables get shredded.** DOCX tables are already flattened to `"a | b | c"` lines
   (`ingestion.py:125-131`) and XLSX rows likewise (`ingestion.py:133-145`); the chunker
   does not recognise table blocks, so long tables split across chunks and later chunks
   lose their header row.
5. **Page/sheet context is lost.** PDF page numbers are never persisted
   (`ingestion.py:117-123`); the XLSX `# sheet-name` marker only appears once at the top.
   Retrieval results therefore cannot cite a page or sheet.
6. **DOCX ordering is destroyed** — all paragraphs are walked first, then all tables, so
   the original interleaving is lost, and heading levels (Heading 1/2/3) are dropped.
7. **No chunk metadata at all.** `ingestion.py:248-263` persists only `text_content` and a
   digest.
8. **Chunk generation is pinned to 1** and inserts use
   `ON CONFLICT(document_id,version,generation,ordinal) DO NOTHING`
   (`ingestion.py:251`), so re-running after a chunker change silently keeps stale chunks.

Retrieval already supports hybrid keyword+vector with optional rerank
(`backend/src/ima/application/search.py:405-482`, `550-625`) over a `zhparser` tsvector
(`migrations/.../20260826_0007_search_conversations.py:23-44`) and pgvector HNSW, so
better chunks translate directly into better answers.

## Goal

Replace the blind character window with a structure-aware chunker that preserves document
structure, keeps tables intact, and records enough metadata for precise citations —
without breaking the existing durable ingestion pipeline.

## Requirements

### 1. Structured parse output

Parsing must emit an intermediate representation of blocks, not just a flat string:

- Markdown/text: heading tree (level + text), paragraphs, code fences, lists, tables.
- DOCX: walk the document body **in order** so paragraphs and tables interleave correctly;
  keep heading levels from paragraph styles.
- PDF: keep the page number for each extracted text block.
- XLSX: keep sheet name and row range; keep the header row for each sheet.

Persist this IR so the separate `chunk` stage can consume it after a worker restart
(parse and chunk are independent durable stages — see
`backend/src/ima/infrastructure/tasks/ingestion.py:129-280`).

### 2. Structure-aware chunking

- Split on structural boundaries first (heading sections → paragraphs → sentences),
  falling back to character splitting only inside an oversized atomic block.
- Keep tables atomic when they fit; when a table must be split, repeat the header row in
  each part.
- Prefix each chunk with its heading path (e.g. `一、整体运行情况 > (一) 数字化`) so a
  retrieved chunk carries its section context.
- Token-aware budget with a Chinese/English mixed estimator (no new heavy dependency
  required; a documented estimator is acceptable — CJK chars ≈ 1 token, latin ≈ 1/4 char).
- Overlap should be block-level, not a blind 160 characters.
- Record a `chunker_version` and config digest so future changes are detectable.

### 3. Chunk metadata

Add columns to `ima.document_chunks` via a new Alembic migration:

- `metadata jsonb NOT NULL DEFAULT '{}'`
- `heading_path text[]` (or inside metadata — pick one and be consistent)
- `page_start int` / `page_end int` (PDF), `sheet_name text` (XLSX)
- `chunk_type text` (prose/table/code/heading)
- `token_count int`
- `chunker_version text`

Handle re-chunking properly: bump `generation` when the chunker version or config digest
changes instead of relying on `DO NOTHING` against stale rows.

### 4. Embedding batching (related, low-risk)

`EmbeddingConfig.batch_size` (32) and `max_tokens` (8192) are defined
(`backend/src/ima/domain/model_governance.py:136-144`) but **not used**: the embed stage
sends every chunk of a document in one request
(`backend/src/ima/infrastructure/tasks/ingestion.py:296-339`). Respect `batch_size` and
keep partial progress so a large document does not fail as a whole.

## Non-goals

- OCR, image, audio ingestion; `.pptx`/`.xls` support.
- Swapping the embedding provider or the retrieval fusion algorithm.
- Parent-child / small-to-big retrieval (a follow-up; metadata added here enables it).
- Adding RAGFlow/Dify/LlamaIndex as dependencies — take the *ideas*, not the packages.

## Acceptance criteria

- New unit tests in `backend/tests/unit/test_ingestion.py` covering: Markdown heading
  hierarchy and heading-path prefixes; a table staying intact (and header repetition when
  split); DOCX paragraph/table ordering; PDF page metadata; XLSX sheet metadata; the
  Chinese token estimator; oversized-block fallback.
- Existing ingestion tests still pass.
- The Alembic migration applies cleanly, and re-running ingestion after a chunker version
  change produces a new generation rather than silently keeping old chunks.
- `uv run pytest` (backend) passes; `uv run ruff check` / type checks pass if configured.

## Key files

- `backend/src/ima/application/ingestion.py` — parser + `deterministic_chunks`
- `backend/src/ima/infrastructure/tasks/ingestion.py` — parse/chunk/embed stages
- `backend/src/ima/config.py` — chunk settings
- `backend/migrations/versions/` — new migration
- `backend/src/ima/domain/model_governance.py` — `EmbeddingConfig`
- `backend/tests/unit/test_ingestion.py`
