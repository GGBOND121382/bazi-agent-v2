import { describe, expect, it } from 'vitest'
import type { ChartResultDTO } from '@/api/schema'
import {
  buildDayunDisplayMeta,
  displayValue,
  parseStructuredSummary,
  structuredEntries,
  structuredReferences,
} from '@/utils/report-presentation'

const chart = {
  schema_version: 'chart-result-v1',
  chart_id: 'chart-test',
  calculation_status: 'passed',
  calculation_profile_id: 'ziping_standard_v1',
  normalized_time: { calculation_time: '1995-12-22T15:00:00+08:00' },
  calendar: {},
  pillars: [],
  day_master: '丁',
  facts: [],
  qiyun: { start_years: 4, start_months: 10, start_days: 23 },
  dayun: [
    { index: 1, ganzhi: '丁亥', start_year: 2000, end_year: 2009, start_age: 6, end_age: 15 },
    { index: 2, ganzhi: '丙戌', start_year: 2010, end_year: 2019, start_age: 16, end_age: 25 },
  ],
  engine_versions: [],
  warnings: [],
} satisfies ChartResultDTO

describe('report presentation', () => {
  it('turns full-width pseudo JSON into dashboard fields', () => {
    const parsed = parseStructuredSummary(
      '{"day_master"："丁"，"strength"："身弱"，"pattern_candidates"：["伤官驾杀"]，"fact_refs"：["FACT-DM-1"]}',
    )
    expect(parsed).not.toBeNull()
    expect(structuredEntries(parsed!)).toEqual([
      ['day_master', '丁'],
      ['strength', '身弱'],
      ['pattern_candidates', ['伤官驾杀']],
    ])
    expect(structuredReferences(parsed!)).toEqual(['FACT-DM-1'])
    expect(displayValue(['木', '火'])).toBe('木、火')
  })

  it('labels pre-qiyun and deterministic dayun periods with ages and years', () => {
    expect(buildDayunDisplayMeta('戊子（月柱）', 0, chart)).toEqual({
      stageLabel: '起运前',
      periodLabel: '1995—2000年',
      ageLabel: '0—4岁10个月23天',
      isPreQiyun: true,
    })
    expect(buildDayunDisplayMeta('丁亥', 1, chart)).toEqual({
      stageLabel: '第 1 步大运',
      periodLabel: '2000—2009年',
      ageLabel: '6—15岁',
      isPreQiyun: false,
    })
  })

  it('keeps ordinary prose as prose', () => {
    expect(parseStructuredSummary('日主偏弱，喜木火。')).toBeNull()
  })
})
