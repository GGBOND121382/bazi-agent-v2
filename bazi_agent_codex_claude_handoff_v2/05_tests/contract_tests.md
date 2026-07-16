# 关键契约测试

## CalendarEngineProtocol

- 返回字段完整；
- datetime 带时区；
- 第三方类型不泄露；
- engine_version 可读；
- 不支持配置时明确报错。

## LLM Provider

- JSON Schema 强校验；
- 超时和限流重试有上限；
- 不记录密钥；
- token 用量可追踪；
- 任意文本不能绕过 validator。

## Retriever

- `approved` 以外状态返回 0 条；
- evaluation hash 永远返回 0 条；
- 每条证据有 source_id、chunk_id 和 license；
- 流派过滤有效。

## ReportWriter

- validation failed 时抛错；
- 不存在 claim_id 时抛错；
- 引用编号稳定；
- HTML 转义用户文本。
