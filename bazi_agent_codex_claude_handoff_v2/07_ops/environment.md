# 环境与配置

## 环境变量建议

```text
DATABASE_URL
OPENAI_API_KEY
ANTHROPIC_API_KEY
LLM_PROVIDER
LLM_MODEL
EMBEDDING_PROVIDER
EMBEDDING_MODEL
REPORT_STORAGE_PATH
LOG_LEVEL
```

`.env.example` 只放变量名和占位符。生产密钥使用 secrets manager。

## 依赖原则

- 锁定版本和哈希；
- 历法库升级必须触发全部 golden test；
- `tzdata` 版本写入计算结果；
- 模型和 Prompt 版本写入每次调用；
- 不在领域层读取环境变量。
