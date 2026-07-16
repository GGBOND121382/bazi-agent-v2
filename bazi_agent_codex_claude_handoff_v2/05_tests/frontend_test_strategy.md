# 前端测试策略

## 单元

- ViewModel mapper 不产生新领域事实；
- 日期、数值和本地化格式；
- API 错误码映射；
- SSE reducer 和断线恢复；
- 报告块 renderer 的穷尽性。

## 组件

- BirthWizard 每一步验证与键盘操作；
- PillarCard、RelationshipBadge、EvidenceDrawer；
- DayunTimeline 选中、滚动和移动端列表；
- ReportRenderer 对所有 block_type；
- loading/empty/error/stale。

## E2E

- 新建普通命盘；
- 临界时间候选确认；
- 分析进度和 SSE 重连；
- 验证失败；
- 查看大运和流年；
- 导出 PDF；
- 删除命盘；
- 分享创建/撤销。

## 视觉回归

桌面 1440×1000、平板 834×1112、移动 390×844。固定字体、时区、动画、mock 和浏览器版本。

## 无障碍

- axe 自动检查；
- 完整键盘流程；
- 焦点可见；
- 图表文本替代；
- 对比度；
- `prefers-reduced-motion`。
