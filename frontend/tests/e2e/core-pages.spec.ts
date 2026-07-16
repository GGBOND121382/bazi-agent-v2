import { expect, test, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const overview = {
  schema_version: 'chart-overview-view-v1', chart_id: 'chart_demo', display_name: '演示命盘', status: 'calculated',
  pillars: [
    { position: 'year', stem: '庚', branch: '午', ten_god: '伤官', hidden_stems: [], nayin: '路旁土', growth_stage: null, fact_ids: ['F1'] },
    { position: 'month', stem: '壬', branch: '午', ten_god: '食神', hidden_stems: [], nayin: '杨柳木', growth_stage: null, fact_ids: ['F2'] },
    { position: 'day', stem: '辛', branch: '亥', ten_god: null, hidden_stems: [], nayin: '钗钏金', growth_stage: null, fact_ids: ['F3'] },
    { position: 'hour', stem: '庚', branch: '寅', ten_god: '劫财', hidden_stems: [], nayin: '松柏木', growth_stage: null, fact_ids: ['F4'] },
  ], assumptions: [{ label: '计算口径', value: 'ziping_standard_v1' }], warnings: [], relationships: [], five_elements: [],
}

const report = {
  schema_version: 'report-view-v1', report_id: 'report_demo', chart_id: 'chart_demo', title: '结构化分析报告', generated_at: '2026-07-16T00:00:00Z',
  toc: [{ anchor: 'structure', title: '命局结构', level: 1 }],
  blocks: [
    { block_id: 'h', block_type: 'heading', anchor: 'structure', text: '命局结构', level: 1 },
    { block_id: 'c', block_type: 'claim', title: '可追溯解释', summary: '在本规则体系下，解释可能保持可追溯。', confidence: .7, fact_ids: ['F1'], rule_ids: ['R1'], evidence_ids: ['E1'], counterevidence: ['存在其他解释路径。'] },
  ],
  citations: [{ evidence_id: 'E1', title: '审核证据', source_label: '项目规则', locator: 'SRC#E1' }],
  limitations: ['传统命理解释不构成专业建议。'],
}

async function mockApi(page: Page) {
  await page.route('**/api/v1/charts/chart_demo/overview-view', (route) => route.fulfill({ json: overview }))
  await page.route('**/api/v1/charts/chart_demo/temporal/2026', (route) => route.fulfill({ json: {
    schema_version: 'temporal-context-view-v1', chart_id: 'chart_demo', target_year: 2026,
    breadcrumb: [{ level: 'natal', label: '原局', ganzhi: '辛亥' }, { level: 'dayun', label: '大运', ganzhi: '乙酉' }, { level: 'year', label: '流年', ganzhi: '丙午' }],
    active_dayun: { ganzhi: '乙酉' }, year: { ganzhi: '丙午', stem: '丙', branch: '午', fact_id: 'Y2026', rule_id: 'LY' },
    months: Array.from({ length: 12 }, (_, index) => ({ index: index + 1, label: `节气月 ${index + 1}`, ganzhi: '庚寅', stem: '庚', branch: '寅', fact_id: `M${index + 1}`, rule_id: 'LM' })),
  } }))
  await page.route('**/api/v1/reports/report_demo', (route) => route.fulfill({ json: report }))
  await page.route('**/api/v1/history', (route) => route.fulfill({ json: { charts: [{ chart_id: 'chart_demo', calculation_status: 'passed', created_at: '2026-07-16T00:00:00Z', note: '演示' }], reports: [{ report_id: 'report_demo', chart_id: 'chart_demo', title: '报告', generated_at: '2026-07-16T00:00:00Z' }] } }))
  await page.route('**/api/v1/settings/profile', (route) => route.fulfill({ json: { schema_version: 'user-preferences-v1', language: 'zh-CN', detail_level: 'concise', theme: 'system', reduce_motion: false } }))
  await page.route('**/api/v1/settings/configuration', (route) => route.fulfill({ json: { calculation_profile_id: 'ziping_standard_v1', calculation_profile_read_only: true, model_provider: 'deepseek', model_configuration_read_only: true, sharing_enabled: false } }))
  await page.route('**/api/v1/jobs/job_demo/events*', (route) => route.fulfill({ contentType: 'text/event-stream', body: 'id: 1\nevent: job\ndata: {"schema_version":"job-event-v1","event_id":"1","job_id":"job_demo","stage":"completed","progress":100,"message_key":"job.completed","occurred_at":"2026-07-16T00:00:00Z","retryable":false,"result_ref":"report_demo"}\n\n' }))
}

async function assertAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter((item) => ['serious', 'critical'].includes(item.impact ?? ''))).toEqual([])
}

test.beforeEach(async ({ page }) => { await mockApi(page) })

test('landing', async ({ page }) => { await page.goto('/'); await expect(page.getByRole('heading', { level: 1 })).toBeVisible(); await assertAccessible(page); await expect(page).toHaveScreenshot('landing.png', { fullPage: true }) })
test('wizard restores its current flow', async ({ page }) => { await page.goto('/charts/new'); await page.getByTestId('next').click(); await expect(page.getByText('第 2 / 4 步')).toBeVisible(); await assertAccessible(page); await expect(page).toHaveScreenshot('wizard.png', { fullPage: true }) })
test('chart overview', async ({ page }) => { await page.goto('/charts/chart_demo'); await expect(page.getByRole('table', { name: '四柱' })).toBeVisible(); await assertAccessible(page); await expect(page).toHaveScreenshot('overview.png', { fullPage: true }) })
test('temporal context', async ({ page }) => { await page.goto('/charts/chart_demo/temporal'); await expect(page.getByText('当前流年')).toBeVisible(); await assertAccessible(page); await expect(page).toHaveScreenshot('temporal.png', { fullPage: true }) })
test('analysis progress hides chain of thought', async ({ page }) => { await page.goto('/jobs/job_demo'); await expect(page.getByText('不展示模型内部思维链')).toBeVisible(); await assertAccessible(page); await expect(page).toHaveScreenshot('progress.png', { fullPage: true }) })
test('report and evidence drawer', async ({ page }) => { await page.goto('/reports/report_demo'); await page.getByRole('button', { name: '查看事实、规则与证据' }).click(); await expect(page.getByRole('dialog')).toBeVisible(); await assertAccessible(page); await expect(page).toHaveScreenshot('report-evidence.png', { fullPage: true }) })
test('history and settings', async ({ page }) => { await page.goto('/history'); await expect(page.getByText('匿名备注')).toBeVisible(); await assertAccessible(page); await expect(page).toHaveScreenshot('history.png', { fullPage: true }); await page.goto('/settings'); await expect(page.getByText('系统配置（只读）')).toBeVisible(); await assertAccessible(page); await expect(page).toHaveScreenshot('settings.png', { fullPage: true }) })
