# 前端文件级实施清单

## 基线

- `src/styles/tokens.css` 从 design_tokens 生成；
- `src/layouts/AppShell.vue`；
- `src/router/index.ts`；
- `src/api/client.ts` 和 generated types；
- `src/components/feedback/*`；
- `src/pages/NotFoundPage.vue` / `FatalErrorPage.vue`。

## 录入

- `features/birth/BirthWizard.vue`；
- 四个 step 组件；
- `useBirthDraft.ts`（仅最小非敏感草稿）；
- `CandidateChartCompare.vue`；
- 表单和 E2E。

## 命盘

- `PillarCard.vue`、`FourPillarsGrid.vue`；
- `FiveElementChart.vue` + table；
- `RelationshipList.vue`；
- `CalculationProfileSheet.vue`；
- overview mapper/test。

## 时间

- `QiyunSummary.vue`；
- `DayunTimeline.vue` desktop/mobile variants；
- `TemporalBreadcrumb.vue`；
- Year/Month/Day pages。

## 分析与报告

- `useJobEvents.ts`；
- `AnalysisStageStepper.vue`；
- `ClaimCard.vue`；
- `EvidenceDrawer.vue`；
- typed `ReportRenderer`；
- print components。

## 历史与设置

- cursor pagination；
- delete confirmation with scope；
- export list；
- preferences。

每个条目必须配类型、组件测试、至少一个 E2E 覆盖和状态故事。
