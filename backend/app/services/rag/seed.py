"""Audited seed importer.  Only production rag_seed paths are accepted."""
from __future__ import annotations

import json
from pathlib import Path

from .governance import CorpusGovernance, ReviewDecision, assert_not_evaluation_path


def import_approved_seed(governance: CorpusGovernance, path: Path) -> tuple[str, ...]:
    assert_not_evaluation_path(path)
    imported: list[str] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("status") != "approved_seed":
                continue
            chunk = governance.ingest_text(
                source_id=item["source_id"],
                chunk_id=item["chunk_id"],
                content=item["content"],
                provenance={
                    "path": str(path),
                    "line": line_number,
                    "title": item["title"],
                    "version": "rules-seed-v1",
                },
                school=item["school"],
                task_type=item["task_type"],
                metadata={
                    "title": item["title"],
                    "conditions": item.get("conditions", []),
                    "exceptions": item.get("exceptions", []),
                    "document_type": "rule",
                },
            )
            governance.review(
                chunk.chunk_id,
                ReviewDecision(
                    reviewer_id="seed-catalog-v1",
                    license_verified=True,
                    language_verified=True,
                    provenance_verified=True,
                ),
            )
            governance.approve(chunk.chunk_id)
            imported.append(chunk.chunk_id)
    return tuple(imported)
