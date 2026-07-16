"""Document-type-aware chunking that preserves semantic boundaries."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DraftChunk:
    title: str
    content: str
    metadata: dict[str, object]


def chunk_document(
    *, document_type: str, title: str, text: str, max_chars: int = 800, overlap: int = 80
) -> tuple[DraftChunk, ...]:
    """Split rules/classics while keeping cases and conversations atomic.

    Overlap is applied only between chunks in the same classic section.  This
    avoids joining unrelated passages and preserves citation granularity.
    """
    if max_chars < 100 or overlap < 0 or overlap >= max_chars:
        raise ValueError("invalid chunk size or overlap")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ()
    if document_type in {"case", "counterexample", "conversation"}:
        return (
            DraftChunk(
                title=title,
                content=normalized,
                metadata={"document_type": document_type, "atomic": True},
            ),
        )
    if document_type == "rule":
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
        return tuple(
            DraftChunk(
                title=f"{title} · {index}",
                content=paragraph,
                metadata={"document_type": "rule", "rule_index": index},
            )
            for index, paragraph in enumerate(paragraphs, start=1)
        )
    if document_type != "classic":
        raise ValueError(f"unsupported document type: {document_type}")

    sections: list[tuple[str, list[str]]] = []
    section_title = title
    section_lines: list[str] = []
    for line in normalized.splitlines():
        stripped = line.strip()
        if re.match(r"^(?:#{1,4}\s+|第[^\s]{1,12}[卷章节篇]|卷[^\s]{1,12})", stripped):
            if section_lines:
                sections.append((section_title, section_lines))
            section_title = stripped.lstrip("# ")
            section_lines = []
        elif stripped:
            section_lines.append(stripped)
    if section_lines:
        sections.append((section_title, section_lines))

    chunks: list[DraftChunk] = []
    for current_title, lines in sections:
        section_text = "\n".join(lines)
        start = 0
        part = 1
        while start < len(section_text):
            end = min(start + max_chars, len(section_text))
            content = section_text[start:end]
            chunks.append(
                DraftChunk(
                    title=f"{current_title} · {part}",
                    content=content,
                    metadata={
                        "document_type": "classic",
                        "section": current_title,
                        "part": part,
                    },
                )
            )
            if end == len(section_text):
                break
            start = end - overlap
            part += 1
    return tuple(chunks)
