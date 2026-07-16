# 部署拓扑

## MVP

```text
Reverse Proxy
├── /           → Web static assets
├── /api        → FastAPI
├── /events     → FastAPI SSE（禁用代理缓冲）
└── /downloads  → 受权 PDF/object storage

FastAPI
├── PostgreSQL + pgvector
├── background worker
├── model provider
└── geocoding provider（可选）
```

## 要求

- Web 与 API 同站优先，降低 CORS 和 CSRF 复杂度；
- SSE 路径关闭中间层缓冲并配置 keep-alive；
- PDF 为短期签名 URL；
- API key 仅注入 worker/API；
- 日志字段脱敏；
- 开发环境可用 compose，生产环境不依赖本地文件持久化。
