# Claude Code 主提示

阅读 README、HANDOFF、FIRST_RUN_CHECKLIST、PRD、里程碑、Schema 和前端目录。先产出仓库审计与实施计划，再逐 Gate 修改。

每轮工作：
1. 指出当前 Gate；
2. 读取相关母版文件；
3. 实施最小完整切片；
4. 运行 formatter/lint/typecheck/test；
5. 前端还需运行 Playwright/视觉/axe；
6. 更新 IMPLEMENTATION_STATUS 和 API_CONTRACT_DIFF；
7. 自查是否把命理算法写进前端或 LLM；
8. 给出证据路径。

不得用通用后台模板替代设计系统，不得把 mock 数据硬编码进生产组件。
