# API 集成

## 客户端

- 从 OpenAPI 生成类型和基础函数；
- 统一封装 request_id、认证、超时和错误码；
- mutation 使用 Idempotency-Key；
- Query key 包含 schema/profile 版本相关 ID，不缓存敏感输入。

## SSE

- 单独 `useJobEvents(jobId)` composable；
- 记录 lastEventId；
- 指数退避；
- 心跳超时回退轮询；
- terminal 状态停止连接；
- 收到 completed 后使 report/chart query 失效并重新拉取。

## 错误呈现

前端根据 `error_code` 映射用户文本：

- `BIRTH_TIME_INVALID`
- `TIMEZONE_AMBIGUOUS`
- `CALENDAR_ENGINE_CONFLICT`
- `BOUNDARY_RESOLUTION_REQUIRED`
- `ANALYSIS_VALIDATION_FAILED`
- `RAG_NO_APPROVED_EVIDENCE`
- `MODEL_PROVIDER_UNAVAILABLE`
- `EXPORT_FAILED`
- `CLIENT_SCHEMA_UNSUPPORTED`

不得直接显示后端堆栈或 Provider 原始错误。
