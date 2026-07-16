# IMPLEMENTATION STATUS

更新日期：2026-07-16

## 当前 Gate

| 阶段 | 状态 | 证据 / 说明 |
|---|---|---|
| S0/S1/B1/F1/B2/F2/B3/F3/I1 | 完成（本地/进程内） | 确定性计算、契约、API、应用壳、向导、overview；全量测试见下方 |
| A1 RAG 治理与检索内核 | 完成（正式语料已接入） | `bazi_rag_dataset_v2_1` 哈希/自带校验通过；SQLite FTS5 三通道多查询融合，A/B 规则证据与 C 级解释/历史类比严格隔离 |
| A2 分析/验证/报告块 | 完成（mock + live E2E） | DeepSeek adapter 环境变量失败关闭；结构化分析、确定性验证、正式报告 Gate；合成命盘完整在线链路通过 |
| F4 流运/证据/报告阅读 | 完成 | 后端 temporal view；三层 EvidenceDrawer；白名单 Report block renderer |
| I2 完整分析流水线 | 完成（进程内 worker） | 幂等 job、合法状态迁移、SSE replay、重试、取消、报告引用；不展示 CoT |
| R1 历史/打印/分享/设置 | 完成（进程内存储） | 匿名备注、重分析、print/PDF CSS、分享默认关闭/过期/撤销、配置只读 |
| Golden | 完成 | 精确节令、顺逆排、60 甲子：4/4 |
| H1 安全/性能/E2E | 完成（本地 Gate） | security/performance 4/4；evaluation JSON 6/6；Playwright+axe+visual 14/14 |

## 最新证据

```text
正式 RAG 数据：7637 条（A/B 权威 234、C 级解释 7203、C 级历史案例 200）
数据包校验：27 个清单哈希一致；自带 validate_dataset.py passed
RAG / Agent 专项：21 collected；包含三通道、多查询融合、引用与修订 Gate
后端全量：128 passed
Golden：4 passed
Security + performance：4 passed
Playwright desktop/mobile + axe + visual：14 passed；无更新快照复跑 14 passed
前端 unit：7 passed
前端 vue-tsc：0 errors
前端 production build：passed
后端 ruff：All checks passed
后端 mypy strict：Success（55 source files，mypy 2.3.0）
DeepSeek 完整在线 E2E：passed（正式 RAG 8 条权威 + 4 条解释；validation passed；报告生成；key 未回显/落盘）
```

最终全量命令与结果以 `docs/evidence/final/README.md` 为准。

## 尚需部署环境完成

- 将 `ChartStore` / `InMemoryAnalysisStore` 替换为 PostgreSQL + 对象存储并执行迁移/备份恢复演练。
- 多用户上线前接入身份认证、owner 隔离、CSRF 策略与速率限制；当前工作区为 anonymous 单用户模式。
- 部署环境继续通过 Secret 注入 `DEEPSEEK_API_KEY`，并配置 Provider 超时率、验证失败率和费用监控。
