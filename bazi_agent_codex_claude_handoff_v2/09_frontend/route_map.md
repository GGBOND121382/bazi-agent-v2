# 路由表

| 路由 | 页面 | 数据来源 |
|---|---|---|
| `/` | 首页 | 静态/配置 |
| `/charts/new` | 出生信息向导 | 本地草稿 + 地点 API |
| `/charts/:chartId/resolve` | 临界候选确认 | Chart candidates |
| `/jobs/:jobId` | 分析进度 | Job snapshot + SSE |
| `/charts/:chartId/overview` | 命盘总览 | ChartOverviewView |
| `/charts/:chartId/structure` | 五行与结构 | Chart + validated analysis |
| `/charts/:chartId/dayun` | 大运 | Qiyun/Dayun view |
| `/charts/:chartId/years/:year?` | 流年 | Temporal view |
| `/charts/:chartId/months/:year/:month?` | 流月/流日 | Temporal view |
| `/charts/:chartId/shensha` | 神煞 | Shensha facts |
| `/reports/:reportId` | 报告 | ReportView |
| `/reports/:reportId/print` | 打印 | ReportView + print layout |
| `/history` | 历史 | paginated charts |
| `/settings` | 设置 | preferences/profile summary |
| `/share/:token` | 分享报告 | public sanitized ReportView |
