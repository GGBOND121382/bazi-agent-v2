# API_CONTRACT_DIFF

本文件记录 `contracts/schemas/` 与 `contracts/openapi.yaml` 的所有变更。
任何 PR 涉及 schema/openapi 改动都必须在本文件追加一行；空变更也需写“no change”。

## 2026-07-16 — v2 启动
- 状态：基线冻结。无变更。
- 基线：
  - 13 个 JSON Schema（`contracts/schemas/*.json`）
  - 1 个 OpenAPI outline（`contracts/openapi.yaml`）
  - 1 个 CalculationProfile（`contracts/calculation_profile_v1.yaml`）
- 后续所有变更条目格式：
  ```
  YYYY-MM-DD | <schema_id> | <before> → <after> | 原因 | 影响面
  ```