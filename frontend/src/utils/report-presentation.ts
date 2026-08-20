import type { ChartResultDTO } from '@/api/schema'

export type StructuredSummary = Record<string, unknown> | unknown[]

export type DayunDisplayMeta = {
  stageLabel: string
  periodLabel: string
  ageLabel: string
  isPreQiyun: boolean
}

const FIELD_LABELS: Record<string, string> = {
  day_master: '日主',
  strength: '旺衰',
  pattern: '格局',
  pattern_candidates: '格局候选',
  pattern_success: '成格判断',
  deity: '是否得令',
  support: '是否得助',
  authority: '是否得势',
  overall: '总体判断',
  yong_shen: '用神',
  xi_shen: '喜神',
  ji_shen: '忌神',
  chou_shen: '仇神',
  tiao_hou: '调候',
  climate_adjustment: '调候',
  favoured_elements: '喜用五行',
  unfavoured_elements: '忌讳五行',
  tones: '方位与环境提示',
  system: '关注系统',
  five_element: '对应五行',
  zang_fu: '传统脏腑象义',
  evaluation: '分析判断',
  conclusion: '分析判断',
  analysis: '分析判断',
  finding: '主要发现',
  risk: '注意倾向',
  vulnerability: '易感倾向',
  precaution: '调养建议',
  protection: '保护因素',
  advice: '生活建议',
  fact_refs: '命盘事实',
  fact_ids: '命盘事实',
  trel_refs: '岁运关系',
}

const REFERENCE_KEYS = new Set(['fact_refs', 'fact_ids', 'trel_refs', 'rule_ids', 'evidence_ids'])

function numeric(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function parseStructuredSummary(summary?: string): StructuredSummary | null {
  const candidate = summary?.trim()
  if (!candidate || (!candidate.startsWith('{') && !candidate.startsWith('['))) return null
  try {
    const parsed: unknown = JSON.parse(candidate.replaceAll('：', ':').replaceAll('，', ','))
    if (Array.isArray(parsed)) return parsed
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key.replaceAll('_', ' ')
}

export function structuredEntries(summary: StructuredSummary): [string, unknown][] {
  if (Array.isArray(summary)) return summary.map((value, index) => [`item_${index + 1}`, value])
  return Object.entries(summary).filter(([key]) => !REFERENCE_KEYS.has(key))
}

export function structuredReferences(summary: StructuredSummary): string[] {
  if (Array.isArray(summary)) return []
  return [...REFERENCE_KEYS].flatMap((key) => {
    const value = summary[key]
    return Array.isArray(value) ? value.map(String) : []
  })
}

export function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未提供'
  if (Array.isArray(value)) return value.map(displayValue).join('、')
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, child]) => `${fieldLabel(key)}：${displayValue(child)}`)
      .join('；')
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

export function isWideStructuredField(key: string, value: unknown): boolean {
  return ['evaluation', 'conclusion', 'analysis', 'advice', 'finding'].includes(key)
    || displayValue(value).length > 42
}

export function buildDayunDisplayMeta(
  title: string,
  ordinal: number,
  chart: ChartResultDTO | null,
): DayunDisplayMeta {
  const dayun = chart?.dayun ?? []
  const match = dayun.find((item) => {
    const ganzhi = text(item.ganzhi) || text(item.gan_zhi)
    return ganzhi !== '' && title.includes(ganzhi)
  })
  const preQiyun = ordinal === 0 || /起运前|出生至起运|月柱|代运/.test(title)

  if (preQiyun) {
    const qiyun = chart?.qiyun ?? {}
    const years = numeric(qiyun.start_years)
    const months = numeric(qiyun.start_months)
    const days = numeric(qiyun.start_days)
    const ageParts = [
      years !== null ? `${years}岁` : '',
      months ? `${months}个月` : '',
      days ? `${days}天` : '',
    ].filter(Boolean)
    const birthDate = text(chart?.normalized_time.calculation_time) || text(chart?.normalized_time.utc)
    const birthYear = birthDate ? new Date(birthDate).getFullYear() : null
    const firstStartYear = numeric(dayun[0]?.start_year)
    return {
      stageLabel: '起运前',
      periodLabel: birthYear && firstStartYear ? `${birthYear}—${firstStartYear}年` : '出生至正式起运',
      ageLabel: ageParts.length ? `0—${ageParts.join('')}` : '出生至起运年龄',
      isPreQiyun: true,
    }
  }

  const index = numeric(match?.index) ?? ordinal
  const startYear = numeric(match?.start_year)
  const endYear = numeric(match?.end_year)
  const startAge = numeric(match?.start_age)
  const endAge = numeric(match?.end_age)
  return {
    stageLabel: `第 ${index} 步大运`,
    periodLabel: startYear !== null && endYear !== null ? `${startYear}—${endYear}年` : '年份待命盘补充',
    ageLabel: startAge !== null && endAge !== null ? `${startAge}—${endAge}岁` : '年龄待命盘补充',
    isPreQiyun: false,
  }
}
