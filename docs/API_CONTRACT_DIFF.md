# API CONTRACT DIFF

## 2026-07-16

- 原 13 个 Schema 保持字段不变。
- 新增 `temporal-context-view-v1`：后端计算并返回流年、12 个节气月、当前大运与时间 breadcrumb；前端只展示。
- OpenAPI 修正 `birth_request` 相对路径，并补充：overview view、按年 temporal、history、note、settings configuration。
- 已有 outline 路径落地：analysis job、job snapshot、SSE、cancel、analysis read、report read、export、share/revoke、settings。
- Pydantic DTO 与前端 TypeScript 类型同步新增 Temporal/Job/Report/History/Configuration view types。

