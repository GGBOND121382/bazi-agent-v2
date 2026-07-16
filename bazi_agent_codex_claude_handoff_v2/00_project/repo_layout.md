# 建议 Monorepo 结构

```text
bazi-agent/
├── README.md
├── AGENTS.md
├── CLAUDE.md
├── .env.example
├── compose.yaml
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   ├── src/bazi_agent/
│   │   │   ├── domain/
│   │   │   ├── calculation/
│   │   │   ├── rules/
│   │   │   ├── rag/
│   │   │   ├── agents/
│   │   │   ├── providers/
│   │   │   ├── storage/
│   │   │   ├── jobs/
│   │   │   ├── reports/
│   │   │   ├── api/
│   │   │   └── cli.py
│   │   └── tests/
│   └── web/
│       ├── package.json
│       ├── vite.config.ts
│       ├── playwright.config.ts
│       ├── src/
│       │   ├── api/
│       │   ├── assets/
│       │   ├── components/
│       │   │   ├── ui/
│       │   │   ├── chart/
│       │   │   ├── timeline/
│       │   │   ├── report/
│       │   │   └── feedback/
│       │   ├── composables/
│       │   ├── layouts/
│       │   ├── pages/
│       │   ├── router/
│       │   ├── stores/
│       │   ├── styles/
│       │   ├── types/generated/
│       │   ├── view-models/
│       │   └── main.ts
│       └── tests/
├── packages/
│   ├── contracts/
│   │   ├── openapi/
│   │   ├── json-schema/
│   │   └── generated-types/
│   ├── design-tokens/
│   └── test-fixtures/
├── config/
│   ├── calculation_profiles/
│   ├── rule_sets/
│   ├── prompts/
│   └── logging.yaml
├── data/
│   ├── raw/
│   ├── quarantine/
│   ├── approved/
│   ├── evaluation_only/
│   └── indexes/
├── infra/
│   ├── docker/
│   ├── migrations/
│   └── reverse-proxy/
├── docs/
│   ├── IMPLEMENTATION_STATUS.md
│   ├── DECISION_LOG.md
│   ├── API_CONTRACT_DIFF.md
│   ├── product/
│   ├── architecture/
│   └── runbooks/
└── scripts/
    ├── generate_types.*
    ├── validate_contracts.*
    ├── download_rag_sources.*
    └── check_eval_contamination.*
```

## 边界

- `apps/api/domain` 为纯领域层；
- `packages/contracts` 是前后端唯一共享事实契约；
- `apps/web` 不复制计算规则；
- `packages/design-tokens` 可生成 CSS variables 和 JSON，但不包含业务组件；
- test fixture 与生产数据隔离；
- PDF 打印页面属于 `apps/web` 的专用路由，导出编排属于 `apps/api/reports`。
