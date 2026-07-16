# 交给 Codex / Claude Code 的主开发指令（v2）

你正在实现一个包含后端计算、RAG、智能体、Web 前端和报告导出的八字命理产品。当前目录中的文档、Schema、基础表、Prompt、前端设计和伪代码是项目母版约束。除非发现明确矛盾，不得自行改变计算口径、信任边界、评测隔离或 UI 的事实展示规则。

## 第一次启动

1. 完整阅读 `10_agent_prompts/FIRST_RUN_CHECKLIST.md`。
2. 阅读 `00_project/product_requirements.md`、`00_project/milestone_plan.md` 和 `00_project/repo_layout.md`。
3. 阅读 `01_architecture/calculation_profile_v1.yaml`、`01_architecture/module_contracts.md` 和 `01_architecture/frontend_backend_boundary.md`。
4. 打开 `09_frontend/prototype/index.html`，将其作为视觉方向而非可直接复制的生产代码。
5. 在新仓库创建：
   - `docs/IMPLEMENTATION_STATUS.md`
   - `docs/DECISION_LOG.md`
   - `docs/API_CONTRACT_DIFF.md`
6. 先生成实施清单和依赖图，再开始编码。

## 不可违反的边界

- 领域层不依赖 Web、数据库、LLM SDK、前端或第三方历法对象。
- 第三方历法库只存在于 adapter 层。
- 前端不得实现或兜底任何命理计算。
- 大模型不得重新排盘、纠正或补全工具事实。
- 正式报告只能读取 `validation_status=passed` 的结构化分析。
- 未批准语料、评测集和模型原始长 CoT 不得进入生产检索。
- 出生信息、地点和 API key 不进入普通日志、分析埋点或前端错误上报。

## 推荐工作方式：三条并行工作流

### Backend Core

完成领域对象、时间标准化、历法双引擎、四柱、规则、起运、大运、流运、CLI 和计算 API。

### Frontend Product

在 OpenAPI 和 mock 数据冻结后即可并行完成设计 Token、路由壳、出生信息向导、进度页、命盘总览、大运时间轴、报告阅读和历史记录。没有真实 API 时必须使用 `03_specs/examples/` 下的 mock，不能虚构字段。

### AI / RAG

在计算事实 Schema 稳定后完成数据治理、检索、分析、验证和报告内容块。不得阻塞前端对确定性数据页面的开发。

三条工作流只能通过 `03_specs/` 中的版本化契约交互。

## 第一批必须交付

1. Monorepo 和质量基线；
2. 计算 Profile 加载与领域 Schema；
3. OpenAPI 生成 TypeScript 类型的流水线；
4. 前端设计 Token、应用壳和静态路由；
5. 不调用 LLM 的计算 CLI；
6. 使用 mock 数据可完整浏览的前端骨架；
7. 单元、契约和基础视觉回归测试。

## 编码约束

- Python 和 TypeScript 开启严格类型检查；
- 不硬编码绝对路径、域名、端口或 API key；
- 所有公共函数和组件写明输入、输出、异常和口径；
- API 错误使用稳定错误码，不依赖自然语言判断；
- 时间均为带时区的 ISO 8601；
- 页面组件不直接拼接后端 DTO，先经过 view-model mapper；
- 服务端状态使用 TanStack Query，Pinia 不复制缓存；
- 异步分析通过任务状态和 SSE 事件呈现，不展示内部 CoT；
- 所有图表提供表格或文本替代视图；
- PDF 使用专用打印路由，不截图拼接长页面；
- 每个模型调用记录 `model_id/prompt_version/schema_version/retrieval_trace_id`；
- 每个页面在 loading、empty、partial、error、stale 五种状态下均有明确表现。

## 每个里程碑结束时必须提供证据

1. 运行 formatter、lint、类型检查、单元测试、契约测试；
2. 前端里程碑还要运行组件测试、Playwright E2E、视觉截图和 axe 检查；
3. 将命令、结果、失败项和样例输出路径写入 `docs/IMPLEMENTATION_STATUS.md`；
4. 更新 `docs/API_CONTRACT_DIFF.md`，确认未擅自修改 Schema；
5. 对关键页面提供桌面和移动截图；
6. 不得只声称“已完成”。

## 禁止做法

- 先写一个巨型“八字大师”Prompt 再补工具；
- 让模型根据生日直接生成四柱；
- 在 Vue 组件中计算十神或刑冲合害；
- 使用通用后台管理模板作为最终视觉；
- 把所有状态塞进一个 Pinia store；
- 只做一个旋转 loading，不展示真实任务阶段；
- 将“吉/凶”做成绝对化红绿灯；
- 为了通过测试而硬编码样例输出；
- 未审计数据直接建向量索引。
