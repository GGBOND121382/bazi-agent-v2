# 前端技术栈来源记录

以下链接仅用于实现时核对官方用法，版本由 lockfile 固定：

- Vue TypeScript：https://vuejs.org/guide/typescript/overview
- Vue Tooling / Vite：https://vuejs.org/guide/scaling-up/tooling
- Vite：https://vite.dev/guide/
- Pinia：https://pinia.vuejs.org/
- Vue Router：https://router.vuejs.org/
- TanStack Query Vue：https://tanstack.com/query/latest/docs/framework/vue/overview
- Tailwind CSS + Vite：https://tailwindcss.com/docs/installation/using-vite
- Reka UI：https://reka-ui.com/docs/overview/introduction
- shadcn-vue：https://www.shadcn-vue.com/docs/introduction
- Apache ECharts：https://echarts.apache.org/en/index.html
- Playwright 视觉比较：https://playwright.dev/docs/test-snapshots
- Playwright aria snapshots：https://playwright.dev/docs/aria-snapshots

## 选型原则

- Vue 3 + TypeScript + Vite 与用户已有 Vue 3 技术栈一致；
- Pinia 只管客户端 UI/session 状态，避免与服务器缓存重复；
- TanStack Query 管理请求、缓存、失效和恢复；
- Reka/shadcn-vue 提供可访问的无样式/可复制组件基础，视觉由本项目 Token 控制；
- ECharts 只用于确有信息价值的结构图和时间可视化；
- Playwright 同时负责 E2E、视觉和打印页面验证。
