"""Report assembler selecting only deterministically approved claims."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from ...api.dto import ChartResultDTO, StructuredAnalysisDTO, ValidationResultDTO
from ..rag.models import RetrievedEvidence


def _text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=("，", "："))


def _report_block(
    *,
    block_id: str,
    topic: str,
    statement: str,
    confidence: float,
    fact_ids: list[str] | None = None,
    rule_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    counterevidence: list[str] | None = None,
    temporal_scope: str = "natal",
) -> dict[str, Any]:
    return {
        "block_type": "claim",
        "claim_id": block_id,
        "topic": topic,
        "statement": statement,
        "fact_ids": fact_ids or [],
        "rule_ids": rule_ids or [],
        "evidence_ids": evidence_ids or [],
        "counterevidence": counterevidence or [],
        "confidence": confidence,
        "temporal_scope": temporal_scope,
    }


class ReportAssembler:
    def assemble(
        self,
        *,
        chart: ChartResultDTO,
        analysis: StructuredAnalysisDTO,
        validation: ValidationResultDTO,
        evidence: tuple[RetrievedEvidence, ...],
        prompt_version: str,
        model_id: str,
        retrieval_trace_id: str,
    ) -> dict[str, Any]:
        if validation.status != "passed" or validation.analysis_id != analysis.analysis_id:
            raise ValueError("formal report requires validation_status=passed")
        allowed = set(validation.approved_claim_ids)
        if allowed != {claim.claim_id for claim in analysis.claims}:
            raise ValueError("formal report requires every claim to be approved")

        evidence_index = {item.chunk_id: item for item in evidence}
        sections: list[dict[str, Any]] = []
        if analysis.executive_summary:
            sections.append(
                {
                    "section_id": "summary",
                    "title": "命局总论",
                    "content_blocks": [
                        _report_block(
                            block_id="SUMMARY",
                            topic="命局总论",
                            statement=analysis.executive_summary,
                            confidence=0.8,
                        )
                    ],
                }
            )

        structure_blocks: list[dict[str, Any]] = []
        if analysis.structure_assessment:
            structure_blocks.append(
                _report_block(
                    block_id="STRUCTURE-ASSESSMENT",
                    topic="结构判断总表",
                    statement=_text(analysis.structure_assessment),
                    confidence=0.75,
                )
            )
        structure_blocks.extend(
            _report_block(
                block_id=f"REASONING-{index:02d}",
                topic=step.dimension,
                statement=step.conclusion,
                confidence=step.confidence,
                fact_ids=step.fact_ids,
                rule_ids=step.rule_ids,
                evidence_ids=step.evidence_ids,
                counterevidence=step.counterpoints,
            )
            for index, step in enumerate(analysis.reasoning_summary, start=1)
        )
        if structure_blocks:
            sections.append(
                {
                    "section_id": "structure",
                    "title": "旺衰、格局与喜用",
                    "content_blocks": structure_blocks,
                }
            )

        if analysis.temporal_assessment:
            sections.append(
                {
                    "section_id": "temporal",
                    "title": "大运流年流月流日",
                    "content_blocks": [
                        _report_block(
                            block_id=f"TEMPORAL-{index:02d}",
                            topic=str(item.get("level") or item.get("title") or "岁运判断"),
                            statement=str(item.get("conclusion") or item.get("summary") or _text(item)),
                            confidence=float(item.get("confidence", 0.7)),
                            fact_ids=[str(value) for value in item.get("fact_ids", [])],
                            rule_ids=[str(value) for value in item.get("rule_ids", [])],
                            evidence_ids=[str(value) for value in item.get("evidence_ids", [])],
                            counterevidence=[str(value) for value in item.get("counterpoints", [])],
                            temporal_scope=str(item.get("temporal_scope", "temporal")),
                        )
                        for index, item in enumerate(analysis.temporal_assessment, start=1)
                    ],
                }
            )

        sections.append(
            {
                "section_id": "analysis",
                "title": "主题综合分析",
                "content_blocks": [
                    _report_block(
                        block_id=claim.claim_id,
                        topic=claim.topic,
                        statement=claim.statement,
                        confidence=claim.confidence,
                        fact_ids=claim.fact_ids,
                        rule_ids=claim.rule_ids,
                        evidence_ids=claim.evidence_ids,
                        counterevidence=claim.counterevidence,
                        temporal_scope=claim.temporal_scope,
                    )
                    for claim in analysis.claims
                ],
            }
        )

        if analysis.reflection is not None:
            reflection = analysis.reflection
            statement = "；".join(
                [
                    f"状态：{reflection.status}",
                    f"已检查：{'、'.join(reflection.checked_dimensions) or '未列出'}",
                    f"待补充：{'、'.join(reflection.missing_dimensions) or '无'}",
                    f"矛盾：{'、'.join(reflection.contradictions) or '无'}",
                ]
            )
            sections.append(
                {
                    "section_id": "quality",
                    "title": "分析完整性检查",
                    "content_blocks": [
                        _report_block(
                            block_id="REFLECTION",
                            topic="Reflection 自检",
                            statement=statement,
                            confidence=1.0 if reflection.status == "pass" else 0.5,
                            counterevidence=reflection.revision_instructions,
                        )
                    ],
                }
            )

        used_evidence = {
            eid for claim in analysis.claims for eid in claim.evidence_ids
        }
        used_evidence.update(
            eid for step in analysis.reasoning_summary for eid in step.evidence_ids
        )
        for item in analysis.temporal_assessment:
            used_evidence.update(str(eid) for eid in item.get("evidence_ids", []))
        return {
            "schema_version": "report-v1",
            "report_id": f"report_{uuid.uuid4().hex[:12]}",
            "chart_id": chart.chart_id,
            "validation_id": validation.validation_id,
            "metadata": {
                "generated_at": datetime.now(UTC).isoformat(),
                "model_id": model_id,
                "prompt_version": prompt_version,
                "schema_version": analysis.schema_version,
                "retrieval_trace_id": retrieval_trace_id,
            },
            "calculation_assumptions": {
                "calculation_profile_id": chart.calculation_profile_id,
                "calculation_status": chart.calculation_status,
                "warning_codes": [warning.code for warning in chart.warnings],
            },
            "sections": sections,
            "citations": [
                {
                    "evidence_id": evidence_id,
                    "title": evidence_index[evidence_id].title,
                    "source_id": evidence_index[evidence_id].source_id,
                    "locator": evidence_index[evidence_id].citation,
                    "channel": evidence_index[evidence_id].channel.value,
                    "trust_tier": evidence_index[evidence_id].trust_tier,
                }
                for evidence_id in sorted(used_evidence)
                if evidence_id in evidence_index
            ],
            "limitations": list(analysis.limitations),
        }
