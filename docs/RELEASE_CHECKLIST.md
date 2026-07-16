# 发布检查表

## 发布前

- 后端 `pytest`、contract、golden、security、performance 全绿。
- 前端 lint、typecheck、Vitest、Playwright（desktop + mobile）与 production build 全绿。
- `DEEPSEEK_API_KEY` 仅通过部署 Secret 注入；日志与错误响应抽查无生日、地点、key。
- `ENABLE_REPORT_SHARING=false` 为默认值；启用时验证到期与撤销。
- 运行 `py data/bazi_rag_dataset_v2_1/scripts/validate_dataset.py`；确认生产库为 7,637 条且只有三个允许集合。
- 生产 RAG 以只读方式装载 `data/bazi_rag_dataset_v2_1/import/sqlite/bazi_rag.sqlite`；隔离、低可信与评测目录不在生产检索路径。
- 数据库备份完成，并用隔离环境执行恢复校验。
- OpenAPI、Schema、前后端类型及 `API_CONTRACT_DIFF.md` 同步。

## 发布后

- `/api/v1/health`、创建命盘、任务 SSE、报告打印路由烟测。
- 观察错误率、Provider 超时率、验证失败率和 p95；不记录请求正文。
- 分享功能仍为预期状态；随机抽查撤销 token 无法使用。

## 回滚

1. 停止新分析任务并等待当前任务进入终态。
2. 将流量切回上一个应用镜像；Schema 不做破坏性降级。
3. 若有数据迁移，按迁移对应的 down/forward-fix 策略执行，先恢复到隔离库验证。
4. 撤销本版本新建的所有外部分享，轮换可能受影响的 Provider secret。
5. 记录故障时间线、影响面、恢复证据和再次发布 Gate。
