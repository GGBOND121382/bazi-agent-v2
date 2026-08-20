"""JSON Schema contract tests — S1 Gate.

Validates that every example file in contracts/examples/ satisfies its
corresponding JSON Schema in contracts/schemas/. This is the spec-level
contract that both backend and frontend must satisfy.

If you change a schema, you must also update this test (or the snapshots).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

# Resolve contracts/ relative to repo root, not cwd.
_REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = _REPO_ROOT / "contracts"
SCHEMAS = CONTRACTS / "schemas"
EXAMPLES = CONTRACTS / "examples"


def _load_validator(schema_file: Path) -> Draft202012Validator:
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


@pytest.mark.contract
class TestChartResultSchema:
    def test_chart_overview_view_mock_validates(self):
        v = _load_validator(SCHEMAS / "chart_overview_view.schema.json")
        data = json.loads((EXAMPLES / "chart_overview.mock.json").read_text(encoding="utf-8"))
        errors = list(v.iter_errors(data))
        assert errors == [], f"chart_overview_view schema errors: {[e.message for e in errors]}"

    def test_report_view_mock_validates(self):
        v = _load_validator(SCHEMAS / "report_view.schema.json")
        data = json.loads((EXAMPLES / "report_view.mock.json").read_text(encoding="utf-8"))
        errors = list(v.iter_errors(data))
        assert errors == [], f"report_view schema errors: {[e.message for e in errors]}"


@pytest.mark.contract
class TestApiErrorSchema:
    def test_minimal_error_validates(self):
        v = _load_validator(SCHEMAS / "api_error.schema.json")
        data = {
            "schema_version": "api-error-v1",
            "request_id": "req_test",
            "error_code": "INVALID_INPUT",
            "message_key": "test.error",
            "retryable": False,
        }
        errors = list(v.iter_errors(data))
        assert errors == [], f"api_error schema errors: {[e.message for e in errors]}"

    def test_full_error_validates(self):
        v = _load_validator(SCHEMAS / "api_error.schema.json")
        data = {
            "schema_version": "api-error-v1",
            "request_id": "req_full",
            "error_code": "CHART_CROSS_ENGINE_CONFLICT",
            "message_key": "chart.cross_engine_conflict",
            "retryable": False,
            "field_errors": [{"field": "birth_datetime_local", "issue": "out of range"}],
            "safe_details": {"drifted": ["year"]},
        }
        errors = list(v.iter_errors(data))
        assert errors == [], f"api_error schema errors: {[e.message for e in errors]}"


@pytest.mark.contract
class TestJobEventSchema:
    def test_event_lines_validates(self):
        v = _load_validator(SCHEMAS / "job_event.schema.json")
        for line in (EXAMPLES / "job_events.mock.jsonl").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            errors = list(v.iter_errors(data))
            assert errors == [], f"job_event schema errors: {[e.message for e in errors]} for {line!r}"


@pytest.mark.contract
class TestCalculationProfileSchema:
    def test_yaml_profile_validates_against_schema(self):
        v = _load_validator(SCHEMAS / "calculation_profile.schema.json")
        import yaml

        data = yaml.safe_load((CONTRACTS / "calculation_profile_v1.yaml").read_text(encoding="utf-8"))
        errors = list(v.iter_errors(data))
        assert errors == [], f"profile schema errors: {[e.message for e in errors]}"


@pytest.mark.contract
class TestAnalysisAndReport:
    def test_analysis_output_minimal_validates(self):
        v = _load_validator(SCHEMAS / "analysis_output.schema.json")
        data = {
            "schema_version": "analysis-output-v1",
            "analysis_id": "ana_1",
            "chart_id": "chart_1",
            "school": "ziping_standard",
            "kinship_assessment": [
                {"relationship": name, "evaluation": "示例", "fact_refs": ["FACT-D-1"]}
                for name in ["父亲", "母亲", "兄弟姐妹", "配偶婚恋", "子女", "家庭互动"]
            ],
            "health_assessment": [
                {"dimension": name, "conclusion": "示例"}
                for name in ["五行偏性", "寒暖燥湿", "传统脏腑", "保护因素", "大运变化", "生活建议"]
            ],
            "dayun_assessment": [
                {
                    "order": 0,
                    "period": "出生至起运",
                    "gan_zhi": "月柱代运",
                    "analysis": "示例",
                    "fact_refs": [],
                }
            ],
            "claims": [
                {
                    "claim_id": "c1",
                    "topic": "strength",
                    "statement": "示例",
                    "fact_ids": ["FACT-D-1"],
                    "rule_ids": ["RULE-DAY-MASTER"],
                    "evidence_ids": ["EVID-1"],
                    "confidence": 0.7,
                    "temporal_scope": "natal",
                }
            ],
            "limitations": ["示例限制"],
        }
        errors = list(v.iter_errors(data))
        assert errors == [], f"analysis_output errors: {[e.message for e in errors]}"

    def test_validation_result_minimal_validates(self):
        v = _load_validator(SCHEMAS / "validation_result.schema.json")
        data = {
            "schema_version": "validation-result-v1",
            "validation_id": "val_1",
            "analysis_id": "ana_1",
            "status": "passed",
            "errors": [],
            "warnings": [],
            "approved_claim_ids": ["c1"],
            "required_revisions": [],
        }
        errors = list(v.iter_errors(data))
        assert errors == [], f"validation_result errors: {[e.message for e in errors]}"

    def test_report_minimal_validates(self):
        v = _load_validator(SCHEMAS / "report.schema.json")
        data = {
            "schema_version": "report-v1",
            "report_id": "rpt_1",
            "chart_id": "chart_1",
            "validation_id": "val_1",
            "metadata": {},
            "calculation_assumptions": {},
            "sections": [{"section_id": "s1", "title": "示例", "content_blocks": []}],
            "citations": [],
            "limitations": [],
        }
        errors = list(v.iter_errors(data))
        assert errors == [], f"report errors: {[e.message for e in errors]}"
