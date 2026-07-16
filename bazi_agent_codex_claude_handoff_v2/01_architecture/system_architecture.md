# 完整系统架构

```mermaid
flowchart TD
  U[Web / Mobile Browser] --> FE[Vue Web App]
  FE --> API[FastAPI BFF/API]
  FE <-->|SSE| JOB[Job Event Stream]

  API --> AUTH[Auth / Session]
  API --> CHART[Chart Application Service]
  API --> ANALYSIS[Analysis Job Service]
  API --> REPORT[Report Service]

  CHART --> TIME[Time Normalizer]
  TIME --> BOUNDARY[Boundary Analyzer]
  BOUNDARY --> C1[Primary Calendar Adapter]
  BOUNDARY --> C2[Secondary Calendar Adapter]
  C1 --> RECON[Calendar Reconciler]
  C2 --> RECON
  RECON --> RULES[Deterministic Rule Engine]
  RULES --> LUCK[Qiyun / Dayun / Temporal Engine]

  ANALYSIS --> ORCH[Agent Orchestrator]
  ORCH --> RET[RAG Retrieval + Rerank]
  RET --> LLM[Structured Interpreter]
  LLM --> VERIFY[Fact & Citation Verifier]
  VERIFY --> BLOCKS[Validated Report Blocks]

  REPORT --> PRINT[Print Route / PDF Worker]

  CHART --> DB[(PostgreSQL)]
  ANALYSIS --> DB
  BLOCKS --> DB
  RET --> VDB[(Approved Corpus + pgvector)]
  JOB --> FE
```

## 前端内部

```mermaid
flowchart LR
  Route[Vue Router] --> Page[Page Containers]
  Page --> Query[TanStack Query]
  Page --> VM[View Model Mappers]
  VM --> Component[Presentational Components]
  Pinia[Pinia Session/UI State] --> Page
  Tokens[Design Tokens] --> Component
  APIClient[Generated API Client] --> Query
  SSEClient[SSE Client] --> Query
```

## 信任层级

### 高信任

- 版本化计算配置；
- 经过测试的确定性规则；
- 双引擎一致结果；
- approved 且可追溯的知识块。

### 中信任

- 单一历法库结果；
- 专家审核案例；
- 经程序校验的合成数据。

### 低信任

- 模型生成文本；
- 未审核网络语料；
- OCR；
- 原始自由文本 CoT；
- 用户提供的现实经历。

低信任信息不得覆盖高信任事实。前端必须在视觉上体现层级，而不是把全部内容显示成同一种“结论卡”。
