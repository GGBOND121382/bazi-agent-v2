"""Report assembler selecting only deterministically approved claims."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from ...api.dto import ChartResultDTO, StructuredAnalysisDTO, ValidationResultDTO
from ..rag.models import RetrievedEvidence


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
        claim_blocks = [
            {
                "block_type": "claim",
                "claim_id": claim.claim_id,
                "topic": claim.topic,
                "statement": claim.statement,
                "fact_ids": claim.fact_ids,
                "rule_ids": claim.rule_ids,
                "evidence_ids": claim.evidence_ids,
                "counterevidence": claim.counterevidence or [],
                "confidence": claim.confidence,
                "temporal_scope": claim.temporal_scope,
            }
            for claim in analysis.claims
        ]
        sections: list[dict[str, Any]] = []
        if analysis.executive_summary:
            sections.append(
                {
                    "section_id": "summary",
                    "title": "命局总论",
                    "content_blocks": [
                        {"block_type": "summary", "content": analysis.executive_summary}
                    ],
                }
            )
        if analysis.reasoning_summary or analysis.structure_assessment:
            sections.append(
                {
                    "section_id": "structure",
                    "title": "旺衰、格局与喜用",
                    "content_blocks": [
                        {
                            "block_type": "structure_assessment",
                            "content": analysis.structure_assessment or {},
                        },
                        *[
                            {
                                "block_type": "reasoning_step",
                                **step.model_dump(mode="json"),
                            }
                            for step in analysis.reasoning_summary
                        ],
                    ],
                }
            )
        if analysis.temporal_assessment:
            sections.append(
                {
                    "section_id": "temporal",
                    "title": "大运流年流月流日",
                    "content_blocks": [
                        {"block_type": "temporal_assessment", "content": item}
                        for item in analysis.temporal_assessment
                    ],
                }
            )
        sections.append(
            {
                "section_id": "analysis",
                "title": "主题综合分析",
                "content_blocks": claim_blocks,
            }
        )
        if analysis.reflection is not None:
            sections.append(
                {
                    "section_id": "quality",
                    "title": "分析完整性检查",
                    "content_blocks": [
                        {
                            "block_type": "reflection_summary",
                            "content": analysis.reflection.model_dump(mode="json"),
                        }
                    ],
                }
            )

        used_evidence = sorted({eid for claim in analysis.claims for eid in claim.evidence_ids})
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
                for evidence_id in used_evidence
                if evidence_id in evidence_index
            ],
            "limitations": list(analysis.limitations),
        }
