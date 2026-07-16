# Codex 主提示

解压本包并将其视为母版需求。首先执行 `FIRST_RUN_CHECKLIST.md`，然后严格按 `00_project/milestone_plan.md` 实施。

要求：
- 不擅自改变 calculation profile；
- 不让 LLM 或前端计算命理事实；
- 使用 OpenAPI/Schema 驱动前后端；
- 前端必须参考静态原型，但重写为生产 Vue 组件；
- 每完成一个 Gate，运行完整测试并更新 IMPLEMENTATION_STATUS；
- 在真实 API 未完成前使用本包 mock，不虚构字段；
- 发现矛盾时先记录到 DECISION_LOG，再采用最小变更；
- 不联网搜索已在包内给出的设计和伪代码，第三方 API 变化除外；
- 不以“页面能打开”作为完成，必须提供桌面/移动截图、E2E、视觉和 axe 结果。
