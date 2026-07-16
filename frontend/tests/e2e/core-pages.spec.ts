import { expect, test, type Page, type TestInfo } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const overview = {
  schema_version: 'chart-overview-view-v1', chart_id: 'chart_demo', display_name: '演示命盘', status: 'calculated',
  pillars: [
    { position: 'year', stem: '乙', branch: '亥', ten_god: '偏印', hidden_stems: [{ stem: '壬', ten_god: '正官' }, { stem: '甲', ten_god: '正印' }], nayin: '山头火', growth_stage: '胎', fact_ids: ['F1'] },
    { position: 'month', stem: '戊', branch: '子', ten_god: '伤官', hidden_stems: [{ stem: '癸', ten_god: '七杀' }], nayin: '霹雳火', growth_stage: '绝', fact_ids: ['F2'] },
    { position: 'day', stem: '丁', branch: '亥', ten_god: '日主', hidden_stems: [{ stem: '壬', ten_god: '正官' }, { stem: '甲', ten_god: '正印' }], nayin: '屋上土', growth_stage: '胎', fact_ids: ['F3'] },
    { position: 'hour', stem: '戊', branch: '申', ten_god: '伤官', hidden_stems: [{ stem: '庚', ten_god: '正财' }, { stem: '壬', ten_god: '正官' }, { stem: '戊', ten_god: '伤官' }], nayin: '大驿土', growth_stage: '沐浴', fact_ids: ['F4'] },
  ], assumptions: [{ label: '计算口径', value: 'ziping_standard_v1' }], warnings: [], relationships: [{ type: 'harm', label: '六害', participants: ['亥', '申'], rule_id: 'REL-HARM' }], five_elements: [{ element: '木', explicit: 1, hidden: 2, total: 3 }],
}

const chart = {
  schema_version: 'chart-result-v1', chart_id: 'chart_demo', calculation_status: 'passed', calculation_profile_id: 'ziping_standard_v1',
  normalized_time: { utc: '1995-12-22T08:00:00Z', calculation_time: '1995-12-22T16:00:00+08:00', time_basis: 'true_solar_time' },
  calendar: { deterministic_details: {
    basic: {
      solar_datetime: '1995-12-22 16:00:00', lunar_date: '一九九五年冬月初一 申时', true_solar_time: '1995-12-22T15:46:00+08:00',
      birthplace: { province: '北京', city: '北京', longitude: 116.42, latitude: 39.93 }, ren_yuan_commander: '癸水用事',
      birth_solar_terms: '出生于大雪后14天17小时，小寒前14天17小时', zodiac: '猪', western_zodiac: '摩羯座', lunar_mansion: '亢金龙',
      tai_yuan: '己卯', tai_yuan_nayin: '城头土', tai_xi: '壬寅', tai_xi_nayin: '金箔金', ming_gong: '乙酉', ming_gong_nayin: '泉中水',
      shen_gong: '乙酉', shen_gong_nayin: '泉中水', ming_gua: '坤卦（西四命）',
    },
    pillars: [
      { position: 'year', ganzhi: '乙亥', stem: '乙', branch: '亥', major_star: '偏印', hidden_stems: [{ stem: '壬', ten_god: '正官' }, { stem: '甲', ten_god: '正印' }], secondary_stars: ['正官', '正印'], growth_stage: '胎', self_seat: '死', void: '申酉', nayin: '山头火', five_elements: '木水', shensha: ['天乙贵人'] },
      { position: 'month', ganzhi: '戊子', stem: '戊', branch: '子', major_star: '伤官', hidden_stems: [{ stem: '癸', ten_god: '七杀' }], secondary_stars: ['七杀'], growth_stage: '绝', self_seat: '胎', void: '午未', nayin: '霹雳火', five_elements: '土水', shensha: ['太极贵人'] },
      { position: 'day', ganzhi: '丁亥', stem: '丁', branch: '亥', major_star: '日主', hidden_stems: [{ stem: '壬', ten_god: '正官' }, { stem: '甲', ten_god: '正印' }], secondary_stars: ['正官', '正印'], growth_stage: '胎', self_seat: '胎', void: '午未', nayin: '屋上土', five_elements: '火水', shensha: ['福星贵人'] },
      { position: 'hour', ganzhi: '戊申', stem: '戊', branch: '申', major_star: '伤官', hidden_stems: [{ stem: '庚', ten_god: '正财' }, { stem: '壬', ten_god: '正官' }, { stem: '戊', ten_god: '伤官' }], secondary_stars: ['正财', '正官', '伤官'], growth_stage: '沐浴', self_seat: '病', void: '寅卯', nayin: '大驿土', five_elements: '土金', shensha: ['德秀贵人'] },
    ],
    five_elements: [
      { element: '木', explicit: 1, hidden: 2, total: 3 }, { element: '火', explicit: 1, hidden: 0, total: 1 },
      { element: '土', explicit: 2, hidden: 1, total: 3 }, { element: '金', explicit: 1, hidden: 1, total: 2 },
      { element: '水', explicit: 3, hidden: 4, total: 7 },
    ],
  } },
  pillars: overview.pillars.map((item) => ({ ...item, ganzhi: `${item.stem}${item.branch}`, ten_god_of_stem: item.ten_god })),
  day_master: '丁', facts: [], engine_versions: [{ engine: 'lunar_python', version: '1.4', took_ms: 1 }], warnings: [],
}

const report = {
  schema_version: 'report-view-v1', report_id: 'report_demo', chart_id: 'chart_demo', title: '结构化命理分析报告', generated_at: '2026-07-16T00:00:00Z',
  toc: [{ anchor: 'structure', title: '命局结构', level: 1 }],
  blocks: [
    { block_id: 'h', block_type: 'heading', anchor: 'structure', text: '命局结构', level: 1 },
    { block_id: 'c', block_type: 'claim', title: '命局与事业财运', summary: '丁火日主生于子月，结合原局与大运，事业宜以专业积累和阶段性主动争取并行。', confidence: .78, fact_ids: ['F1'], rule_ids: ['R1'], evidence_ids: ['E1'], counterevidence: ['若现实行业环境变化，具体节奏需随之调整。'] },
  ],
  citations: [{ evidence_id: 'E1', title: '命理规则资料', source_label: 'RAG 语料', locator: 'SRC#E1' }], limitations: [],
}

async function mockApi(page: Page) {
  // Register the exact chart route first; Playwright checks routes in reverse
  // order, so more specific sub-resources registered below take precedence.
  await page.route(/\/api\/v1\/charts\/chart_demo$/, (route) => route.fulfill({ json: chart }))
  await page.route('**/api/v1/charts/chart_demo/overview-view', (route) => route.fulfill({ json: overview }))
  await page.route('**/api/v1/charts/chart_demo/temporal/2026', (route) => route.fulfill({ json: {
    schema_version: 'temporal-context-view-v1', chart_id: 'chart_demo', target_year: 2026,
    breadcrumb: [{ level: 'natal', label: '原局', ganzhi: '丁亥' }, { level: 'dayun', label: '大运', ganzhi: '辛卯' }, { level: 'year', label: '流年', ganzhi: '丙午' }],
    active_dayun: { ganzhi: '辛卯' }, year: { ganzhi: '丙午', stem: '丙', branch: '午', fact_id: 'Y2026', rule_id: 'LY' },
    months: Array.from({ length: 12 }, (_, index) => ({ index: index + 1, label: `节气月 ${index + 1}`, ganzhi: '庚寅', stem: '庚', branch: '寅', fact_id: `M${index + 1}`, rule_id: 'LM' })),
  } }))
  await page.route('**/api/v1/charts/chart_demo/chat', async (route) => route.fulfill({ json: {
    answer: '今年事业宜主动争取可量化成果，财务上先稳住现金流，感情沟通避免把工作压力带入关系。',
    sections: [{ title: '事业与财运', content: '结合辛卯大运与丙午流年，行动力增强，但支出节奏需要控制。', opportunities: ['争取负责核心项目'], cautions: ['避免高杠杆支出'], timing: ['春末与秋初重点复盘'] }],
    citations: [{ evidence_id: 'E1', title: '流年分析规则', source_id: 'SRC', locator: 'SRC#E1' }], scope: 'year', target_date: '2026-07-17', deterministic_context: {}, model_id: 'mock', prompt_version: 'fortune-chat-v1',
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

async function capture(page: Page, testInfo: TestInfo, name: string) {
  await page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage: true })
}

test.beforeEach(async ({ page }) => { await mockApi(page) })

test('landing', async ({ page }, testInfo) => { await page.goto('/'); await expect(page.getByRole('heading', { level: 1 })).toBeVisible(); await assertAccessible(page); await capture(page, testInfo, 'landing') })
test('redesigned birth form', async ({ page }, testInfo) => { await page.goto('/charts/new'); await expect(page.getByRole('heading', { name: '建立命盘' })).toBeVisible(); await expect(page.getByTestId('submit')).toBeVisible(); await assertAccessible(page); await capture(page, testInfo, 'wizard') })
test('detailed chart overview', async ({ page }, testInfo) => { await page.goto('/charts/chart_demo'); await expect(page.getByLabel('四柱排盘')).toBeVisible(); await expect(page.getByText('癸水用事')).toBeVisible(); await assertAccessible(page); await capture(page, testInfo, 'overview') })
test('temporal context', async ({ page }, testInfo) => { await page.goto('/charts/chart_demo/temporal'); await expect(page.getByText('2026 流年')).toBeVisible(); await assertAccessible(page); await capture(page, testInfo, 'temporal') })
test('chart-aware fortune chat', async ({ page }, testInfo) => { await page.goto('/charts/chart_demo/chat'); await page.getByPlaceholder(/今年哪几个月/).fill('今年事业和财运怎么样？'); await page.getByRole('button', { name: '发送问题' }).click(); await expect(page.getByText(/今年事业宜主动争取/)).toBeVisible(); await assertAccessible(page); await capture(page, testInfo, 'chat') })
test('analysis progress hides chain of thought', async ({ page }, testInfo) => { await page.goto('/jobs/job_demo'); await expect(page.getByText('不展示模型内部思维链')).toBeVisible(); await assertAccessible(page); await capture(page, testInfo, 'progress') })
test('report and evidence drawer', async ({ page }, testInfo) => { await page.goto('/reports/report_demo'); await page.getByRole('button', { name: '查看命盘事实与参考资料' }).click(); await expect(page.getByRole('dialog')).toBeVisible(); await assertAccessible(page); await capture(page, testInfo, 'report-evidence') })
test('history and settings', async ({ page }, testInfo) => { await page.goto('/history'); await expect(page.getByRole('button', { name: '用户列表' })).toBeVisible(); await assertAccessible(page); await capture(page, testInfo, 'history'); await page.goto('/settings'); await expect(page.getByText('系统配置（只读）')).toBeVisible(); await assertAccessible(page); await capture(page, testInfo, 'settings') })
