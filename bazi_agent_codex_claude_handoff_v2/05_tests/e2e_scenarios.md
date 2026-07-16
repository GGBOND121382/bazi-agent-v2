# Playwright E2E 场景

1. `birth-happy-path`：填写出生信息 → 计算 → 命盘总览。
2. `boundary-resolution`：临近节气 → 比较两个候选 → 选择 → 重新计算。
3. `analysis-progress-reconnect`：SSE 中断 → Last-Event-ID 恢复 → 报告完成。
4. `analysis-validation-failed`：显示安全错误，不渲染正式报告。
5. `dayun-to-year-navigation`：选择大运 → 跳转指定流年 → 上下文一致。
6. `month-day-context`：流月进入流日，顶部保留大运/流年/流月路径。
7. `report-evidence`：展开 claim → 证据抽屉 → 来源 locator。
8. `pdf-export`：创建导出 → 状态完成 → 下载 URL。
9. `delete-cascade`：删除命盘 → 历史消失 → 旧路由 404。
10. `mobile-core-flow`：390px 完成录入、查看命盘和报告。
