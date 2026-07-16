# 前端安全与隐私

- API key 绝不进入 Vite 环境变量；`VITE_*` 会暴露给浏览器；
- 禁止 `v-html` 渲染模型输出；
- 报告只渲染已知 block_type 和纯文本字段；
- 分享 token 放路径或专用 cookie，不放分析埋点；
- 精确出生信息不写 localStorage，草稿只保存用户明确允许的最小字段；
- Sentry/日志过滤日期、时间、地点、命盘和模型内容；
- 对下载 URL 使用短期签名；
- 退出或删除后清理 Query cache、Pinia 和 session storage；
- CSP 禁止任意脚本；
- 同站 cookie 使用 Secure、HttpOnly、SameSite；
- 管理路由不只靠前端隐藏，后端强制鉴权。
