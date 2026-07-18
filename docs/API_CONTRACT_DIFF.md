# API CONTRACT DIFF

## 2026-07-18

- `analysis-output-v1.kinship_assessment.items` 从开放对象收紧为 `relationship`、`evaluation`、`fact_refs` 必填，`star`、`palace`、`confidence` 可选。
- `analysis-output-v1.dayun_assessment.items` 从开放对象收紧为 `order`、`period`、`gan_zhi`、`analysis`、`fact_refs` 必填，并允许年龄、年份、时序关系引用及确定性兜底状态字段。
- 这是同版本的缺陷修复：服务端读取仍兼容既有报告使用的 `relation/conclusion/fact_ids`、`stage/ganzhi` 字段；新生成内容和局部修复统一使用新版字段。
- `POST /api/v1/charts/{chart_id}/chat` 的上游模型失败不再泄漏为非 JSON 500；现在返回 `api-error-v1`、`error_code=MODEL_PROVIDER_ERROR`、HTTP 502 且 `retryable=true`，`safe_details.provider_error` 保留具体安全错误码。

## 2026-07-17

- `ChartResultDTO.calendar` 增加 `deterministic_details` 运行时对象，承载截图所需的确定性展示字段：农历、节气前后时长、生肖、星座、星宿、胎元、胎息、命宫、身宫、人元司令、四柱十神、藏干、十二长生、自坐、空亡、纳音、神煞和五行统计。现有 Schema 中 `calendar` 为开放对象，因此版本仍为 `chart-result-v1`。
- 新增 `POST /api/v1/charts/{chart_id}/chat`：输入问题、`general/year/month/day` 时间范围、目标日期和最近对话；输出综合回答、分节建议、RAG 引用和确定性流运上下文。
- 前端 TypeScript 新增 `DeterministicDetails`、`FortuneChatRequestDTO`、`FortuneChatResponseDTO` 等类型，并与新接口同步。
- OpenAPI 版本更新为 `0.3.0`。

## 2026-07-16

- 原 13 个 Schema 保持字段不变。
- 新增 `temporal-context-view-v1`：后端计算并返回流年、12 个节气月、当前大运与时间 breadcrumb；前端只展示。
- OpenAPI 修正 `birth_request` 相对路径，并补充：overview view、按年 temporal、history、note、settings configuration。
- 已有 outline 路径落地：analysis job、job snapshot、SSE、cancel、analysis read、report read、export、share/revoke、settings。
- Pydantic DTO 与前端 TypeScript 类型同步新增 Temporal/Job/Report/History/Configuration view types。
