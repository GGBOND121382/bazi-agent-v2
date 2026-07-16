# 前端专项实施提示

目标：实现一个现代、克制、精美、可访问的 Vue 3 Web 产品。

输入：`09_frontend/`、`03_specs/`、`03_specs/examples/` 和静态原型。

步骤：
1. 搭建 Vue 3 + TS + Vite，启用严格类型；
2. 从 OpenAPI 生成类型；
3. 导入 design tokens，不在组件散落 hex；
4. 实现 AppShell、响应式导航和状态组件；
5. 先用 mock 实现 BirthWizard、Progress、ChartOverview、Dayun、Report；
6. 实现 DTO → ViewModel mapper 并测试其“不产生领域事实”；
7. 实现 SSE 恢复；
8. 实现所有 block_type renderer；
9. 添加移动变体、键盘操作和图表文本替代；
10. 建立 Playwright 截图基线。

禁止：在前端计算十神、四柱、起运、关系；直接渲染模型 HTML；使用红绿吉凶评分；只做桌面版。
