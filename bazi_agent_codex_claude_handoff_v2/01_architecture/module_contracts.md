# 模块契约 v2

## TimeNormalizer

```text
normalize(BirthRequest, CalculationProfile) -> NormalizedBirthTime
```

返回 aware datetime；原始值和每项修正可追踪。

## BoundaryAnalyzer

```text
analyze(NormalizedBirthTime, SolarTermWindow, CalculationProfile) -> BoundaryRisk
```

输出节气、换日、时辰边界距离和候选方案。

## CalendarEngineProtocol

```text
calculate(NormalizedBirthTime, CalculationProfile) -> CalendarEngineResult
```

第三方对象在 adapter 内转换。

## CalendarReconciler

```text
reconcile(primary, secondary, tolerance) -> ReconciledCalendarResult
```

关键字段冲突不得静默采用主引擎。

## RuleEngine

```text
derive(ReconciledCalendarResult, RuleSetVersion) -> list[DerivedFact]
```

纯函数、可重复、无 LLM。

## QiyunStrategy / TemporalEngine

```text
calculate_qiyun(chart, solar_terms, profile) -> QiyunResult
calculate_temporal(chart, target_range, profile) -> TemporalContext
```

输出全部中间量；流月流日按需。

## ChartApplicationService

```text
create_chart(request, idempotency_key) -> ChartResource
resolve_candidate(chart_id, candidate_id) -> ChartResource
get_chart(chart_id) -> ChartResource
```

## AnalysisJobService

```text
start(chart_id, analysis_request) -> AnalysisJob
cancel(job_id) -> AnalysisJob
stream(job_id, last_event_id?) -> EventStream
```

事件不包含 CoT 或原始 Provider 响应。

## Retriever

```text
retrieve(RetrievalPlan, approved_corpus_version) -> EvidenceBundle
```

执行状态、流派、许可和等级过滤。

## Interpreter / Verifier

```text
analyze(AnalysisContext) -> StructuredAnalysis
verify(chart, evidence, analysis) -> ValidationResult
```

事实或引用错误返回 failed。

## ReportAssembler

```text
assemble(ValidatedAnalysis) -> ReportDocument
```

不得新增命理结论，只选择结构化块。

## FrontendApiClient

```text
createChart(request) -> ChartResource
createAnalysis(chartId, request) -> AnalysisJob
subscribeJob(jobId, lastEventId?) -> AsyncIterable<JobEvent>
getReport(reportId) -> ReportView
```

由 OpenAPI 生成类型和基础客户端。

## ViewModelMapper

```text
toChartOverviewVM(chart) -> ChartOverviewVM
toDayunTimelineVM(dayun) -> DayunTimelineVM
toReportVM(report) -> ReportVM
```

只做展示转换，不产生新的领域事实。
