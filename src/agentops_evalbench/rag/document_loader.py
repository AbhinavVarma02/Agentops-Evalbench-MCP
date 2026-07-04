"""Document loading and chunking.

Supports Markdown, plain text, and (optionally) PDF via ``pypdf``. Chunking is
paragraph-aware so context is not cut mid-sentence; very long paragraphs fall back
to a character sliding window with overlap.

No heavy dependencies are required for text/markdown — only PDF loading lazily
imports ``pypdf`` and degrades gracefully if it is missing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..config import PROJECT_ROOT

SAMPLE_DOCS_DIR = PROJECT_ROOT / "data" / "sample_docs"

# extension -> source_type label stored on the Document row
SUPPORTED_EXTS: dict[str, str] = {".md": "markdown", ".txt": "text", ".pdf": "pdf"}


@dataclass
class LoadedDocument:
    """A raw document read from disk."""

    filename: str
    source_type: str
    text: str


@dataclass
class Chunk:
    """A chunk of a document, ready to embed/index."""

    source: str  # originating filename
    index: int  # position within the document
    text: str


def preview(text: str, n: int = 280) -> str:
    """Return a short single-line preview of ``text`` (for the DB/content_preview)."""
    flat = " ".join(text.split())
    return flat[:n] + ("…" if len(flat) > n else "")


def _read_pdf(path: Path) -> str:
    """Extract text from a PDF using pypdf. Returns '' if pypdf is unavailable."""
    try:
        from pypdf import PdfReader  # lazy import; optional dependency
    except Exception:
        return ""
    try:
        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def load_documents(directory: str | Path = SAMPLE_DOCS_DIR) -> list[LoadedDocument]:
    """Load every supported document in ``directory`` (non-recursive)."""
    directory = Path(directory)
    docs: list[LoadedDocument] = []
    if not directory.exists():
        return docs

    for path in sorted(directory.iterdir()):
        ext = path.suffix.lower()
        if not path.is_file() or ext not in SUPPORTED_EXTS:
            continue
        source_type = SUPPORTED_EXTS[ext]
        if source_type == "pdf":
            text = _read_pdf(path)
        else:
            text = path.read_text(encoding="utf-8", errors="ignore")
        if text.strip():
            docs.append(LoadedDocument(filename=path.name, source_type=source_type, text=text))
    return docs


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Split ``text`` into chunks of ~``chunk_size`` characters.

    Strategy: pack whole paragraphs together up to ``chunk_size``. If a single
    paragraph is larger than ``chunk_size``, slide a window over it with
    ``overlap`` characters of carry-over so sentences are not cut abruptly.
    """
    text = text.strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(para) > chunk_size:
            if current:
                chunks.append(current.strip())
                current = ""
            start = 0
            step = max(1, chunk_size - overlap)
            while start < len(para):
                chunks.append(para[start : start + chunk_size].strip())
                start += step
            continue

        if not current:
            current = para
        elif len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}"
        else:
            chunks.append(current.strip())
            current = para

    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]


def load_and_chunk(
    directory: str | Path = SAMPLE_DOCS_DIR,
    chunk_size: int = 800,
    overlap: int = 100,
) -> list[Chunk]:
    """Load all documents in ``directory`` and return a flat list of ``Chunk``."""
    chunks: list[Chunk] = []
    for doc in load_documents(directory):
        for i, piece in enumerate(chunk_text(doc.text, chunk_size, overlap)):
            chunks.append(Chunk(source=doc.filename, index=i, text=piece))
    return chunks
