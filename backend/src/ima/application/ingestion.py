"""Bounded text extraction for approved ingestion formats."""

# ruff: noqa: E501

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from docx import Document
from openpyxl import load_workbook  # type: ignore[import-untyped]
from pypdf import PdfReader

from ima.config import Settings

SUPPORTED_MIME_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "application/json",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
)


class ParseError(Exception):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class ParsedText:
    parser: str
    parser_version: str
    text: str
    digest: str


def validate_upload_type(filename: str, mime_type: str) -> None:
    suffix = PurePosixPath(filename).suffix.lower()
    allowed = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".json": "application/json",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    if mime_type.lower() not in SUPPORTED_MIME_TYPES or allowed.get(suffix) != mime_type.lower():
        raise ParseError("UNSUPPORTED_FILE_TYPE")


class Parser:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def parse(self, data: bytes, filename: str, mime_type: str) -> ParsedText:
        if len(data) > self.settings.storage_max_object_bytes:
            raise ParseError("OBJECT_TOO_LARGE")
        validate_upload_type(filename, mime_type)
        suffix = PurePosixPath(filename).suffix.lower()
        try:
            if suffix in {".docx", ".xlsx"}:
                self._validate_archive(data)
            if suffix in {".txt", ".md"}:
                parser, value = "text", data.decode("utf-8")
            elif suffix == ".json":
                parser, value = (
                    "json",
                    json.dumps(json.loads(data.decode("utf-8")), ensure_ascii=False, indent=2),
                )
            elif suffix == ".pdf":
                parser, value = "pdf", self._pdf(data)
            elif suffix == ".docx":
                parser, value = "docx", self._docx(data)
            elif suffix == ".xlsx":
                parser, value = "spreadsheet", self._spreadsheet(data)
            else:
                raise ParseError("UNSUPPORTED_FILE_TYPE")
        except ParseError:
            raise
        except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
            raise ParseError("MALFORMED_DOCUMENT") from exc
        normalized = self._normalize(value)
        if not normalized:
            raise ParseError("EMPTY_DOCUMENT")
        encoded = normalized.encode("utf-8")
        if len(encoded) > self.settings.ingestion_max_text_bytes:
            raise ParseError("EXTRACTED_TEXT_TOO_LARGE")
        return ParsedText(parser, "1", normalized, sha256(encoded).hexdigest())

    def _validate_archive(self, data: bytes) -> None:
        try:
            with ZipFile(BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 1000:
                    raise ParseError("ARCHIVE_ENTRY_LIMIT")
                compressed = sum(entry.compress_size for entry in entries)
                unpacked = sum(entry.file_size for entry in entries)
                if unpacked > self.settings.ingestion_max_text_bytes * 20 or (
                    compressed and unpacked / compressed > 100
                ):
                    raise ParseError("ARCHIVE_LIMIT")
        except BadZipFile as exc:
            raise ParseError("MALFORMED_DOCUMENT") from exc

    def _pdf(self, data: bytes) -> str:
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ParseError("ENCRYPTED_DOCUMENT")
        if len(reader.pages) > 1000:
            raise ParseError("PDF_PAGE_LIMIT")
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)

    def _docx(self, data: bytes) -> str:
        document = Document(BytesIO(data))
        paragraphs = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
        for table in document.tables:
            for row in table.rows:
                paragraphs.append(" | ".join(cell.text.strip() for cell in row.cells))
        return "\n".join(paragraphs)

    def _spreadsheet(self, data: bytes) -> str:
        workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
        if len(workbook.sheetnames) > 100:
            raise ParseError("SHEET_LIMIT")
        values: list[str] = []
        for sheet in workbook.worksheets:
            values.append(f"# {sheet.title}")
            for row_number, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                if row_number > 100_000:
                    raise ParseError("SHEET_LIMIT")
                row_values = [str(value) for value in row if value is not None]
                if row_values:
                    values.append(" | ".join(row_values))
        return "\n".join(values)

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\n{3,}", "\n\n", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def deterministic_chunks(
    text: str, size: int, overlap: int, maximum: int
) -> tuple[tuple[int, str, str], ...]:
    chunks: list[tuple[int, str, str]] = []
    start = 0
    while start < len(text):
        stop = min(len(text), start + size)
        if stop < len(text):
            boundary = text.rfind("\n", start, stop)
            if boundary > start + size // 2:
                stop = boundary
        content = text[start:stop].strip()
        if content:
            chunks.append((len(chunks), content, sha256(content.encode("utf-8")).hexdigest()))
            if len(chunks) > maximum:
                raise ParseError("CHUNK_LIMIT")
        if stop >= len(text):
            break
        start = max(stop - overlap, start + 1)
    return tuple(chunks)
