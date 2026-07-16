# 端到端数据流 v2

## 1. 输入与草稿

前端在本地仅保存最小草稿。完整出生信息提交到服务端后生成规范化哈希和 `chart_id`。分析埋点不得包含出生时间和精确地点。

## 2. 计算

`BirthRequest → NormalizedBirthTime → BoundaryRisk → 双历法结果 → ReconciledCalendar → DerivedFacts → Qiyun/Dayun/TemporalContext`

当有候选命盘时，状态为 `needs_user_resolution`，不得自动进入分析。

## 3. 前端计算视图

服务端返回领域 DTO。前端通过纯函数 mapper 生成：

```text
ChartResult → ChartOverviewVM
DayunResult → DayunTimelineVM
TemporalContext → TemporalCalendarVM
```

Mapper 只排序、格式化和组合字段，不计算命理规则。

## 4. 分析任务

前端创建 AnalysisJob，服务端发布阶段事件：

```text
queued → retrieving → interpreting → verifying → report_building → completed
```

失败时附稳定 `error_code`、`retryable` 和用户安全消息。SSE 不发送 Prompt、CoT、原始 API 响应或密钥。

## 5. RAG 与分析

检索器只接收已验证事实和用户主题。模型返回结构化 claim：

```text
claim → fact_ids → rule_ids → evidence_ids → counterevidence → confidence
```

验证器重算事实引用并核对引用。

## 6. 报告

验证通过的 claim 转为 ReportBlock。Web 和 PDF 使用同一 ReportView 数据，采用不同 renderer，不分别调用模型。

## 7. 历史与删除

Chart、Analysis、Report、ShareToken 和模型调用 trace 均通过父级 ID 关联。删除命盘触发级联删除和向量/缓存清理任务，并保留不含个人内容的审计记录。
