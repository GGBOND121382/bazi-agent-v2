/**
 * Hand-mirrored TS types corresponding to contracts/schemas/json_schema/*.json
 * and contracts/openapi.yaml.
 *
 * If the schema files change, regenerate this file by running:
 *     npm run gen:api
 * (requires openapi-typescript + a reachable contracts/openapi.yaml).
 *
 * Until then, keep this file in sync with the schemas by hand. Contract
 * tests in backend assert the equivalent Pydantic models accept the same
 * JSON, so a frontend bug will surface as a runtime validation error, not a
 * silent shape mismatch.
 */

export type BirthRequest = {
  schema_version: 'birth-request-v1'
  gender: 'male' | 'female' | 'unspecified'
  birth_datetime_local: string // ISO 8601
  timezone: string
  fold?: 0 | 1
  birthplace: {
    country: string
    province?: string
    city: string
    longitude?: number
    latitude?: number
  }
  time_precision?: 'second' | 'minute' | 'hour' | 'unknown'
  uncertainty_minutes?: number
  calculation_profile_id: string
  user_focus?: string[]
  analysis_range?: { start?: string; end?: string }
}

export type PillarDTO = {
  position: 'year' | 'month' | 'day' | 'hour'
  ganzhi: string
  stem: string
  branch: string
  nayin?: string
  hidden_stems?: { stem: string; ten_god?: string }[]
  ten_god_of_stem?: string
}

export type FactDTO = {
  fact_id: string
  fact_type: string
  value?: unknown
  rule_id: string
  inputs?: unknown[]
}

export type EngineVersionDTO = {
  engine: string
  version: string
  took_ms: number
}

export type WarningDTO = {
  severity: 'info' | 'warning' | 'error'
  code: string
  message: string
}

export type ChartResultDTO = {
  schema_version: 'chart-result-v1'
  chart_id: string
  calculation_status: 'passed' | 'needs_review' | 'ambiguous' | 'failed'
  calculation_profile_id: string
  normalized_time: { utc?: string }
  calendar: { engine_versions?: EngineVersionDTO[] }
  pillars: PillarDTO[]
  day_master: string
  facts: FactDTO[]
  qiyun?: Record<string, unknown>
  dayun?: Record<string, unknown>[]
  temporal_context?: Record<string, unknown>[]
  engine_versions: EngineVersionDTO[]
  warnings: WarningDTO[]
}

export type PillarViewDTO = {
  position: 'year' | 'month' | 'day' | 'hour'
  stem: string
  branch: string
  ten_god: string | null
  hidden_stems: { stem: string; ten_god?: string }[]
  nayin: string | null
  growth_stage: string | null
  fact_ids: string[]
}

export type ChartOverviewViewDTO = {
  schema_version: 'chart-overview-view-v1'
  chart_id: string
  display_name: string
  status: 'calculated' | 'needs_user_resolution' | 'needs_review'
  pillars: PillarViewDTO[]
  assumptions: { label: string; value: string }[]
  warnings: { severity: string; message: string }[]
  relationships: { type: string; label: string; participants: string[]; rule_id: string }[]
  five_elements?: { element: string; explicit: number; hidden: number }[]
}

export type JobEventDTO = {
  schema_version: 'job-event-v1'
  event_id: string
  job_id: string
  stage:
    | 'queued'
    | 'calculating'
    | 'needs_user_resolution'
    | 'retrieving'
    | 'interpreting'
    | 'verifying'
    | 'revision_pending'
    | 'report_building'
    | 'completed'
    | 'failed'
    | 'cancelled'
  progress: number
  message_key: string
  occurred_at: string
  retryable: boolean
  safe_details?: Record<string, unknown>
  result_ref?: string | null
  error_code?: string | null
}

export type AnalysisJobDTO = {
  job_id: string
  chart_id: string
  stage: JobEventDTO['stage']
  progress: number
  created_at: string
  result_ref?: string | null
  error_code?: string | null
}

export type ApiErrorDTO = {
  schema_version: 'api-error-v1'
  request_id: string
  error_code: string
  message_key: string
  retryable: boolean
  field_errors?: { loc: (string | number)[]; msg: string; type: string }[]
  safe_details?: Record<string, unknown>
}

export type UserPreferencesDTO = {
  schema_version: 'user-preferences-v1'
  language: 'zh-CN' | 'zh-TW'
  detail_level: 'concise' | 'professional'
  theme: 'light' | 'dark' | 'system'
  reduce_motion?: boolean
  default_analysis_topics?: string[]
}

export type TemporalContextViewDTO = {
  schema_version: 'temporal-context-view-v1'
  chart_id: string
  target_year: number
  breadcrumb: { level: string; label: string; ganzhi?: string | null }[]
  active_dayun?: Record<string, unknown> | null
  year: { ganzhi: string; stem: string; branch: string; fact_id: string; rule_id: string }
  months: {
    index: number
    label: string
    ganzhi: string
    stem: string
    branch: string
    fact_id: string
    rule_id: string
  }[]
}

export type ReportBlockDTO = {
  block_id: string
  block_type: 'heading' | 'paragraph' | 'fact_grid' | 'table' | 'timeline' | 'chart' | 'claim' | 'callout' | 'evidence_list'
  anchor?: string | null
  text?: string
  title?: string
  summary?: string
  level?: number
  tone?: 'info' | 'warning' | 'limitation'
  confidence?: number
  fact_ids?: string[]
  rule_ids?: string[]
  evidence_ids?: string[]
  counterevidence?: string[]
  citation_ids?: string[]
  items?: Record<string, unknown>[]
  columns?: Record<string, unknown>[]
  rows?: Record<string, unknown>[]
  chart_kind?: string
  data?: Record<string, unknown>
  text_alternative?: string
}

export type ReportViewDTO = {
  schema_version: 'report-view-v1'
  report_id: string
  chart_id: string
  title: string
  generated_at: string
  calculation_profile_label?: string
  toc: { anchor: string; title: string; level?: number }[]
  blocks: ReportBlockDTO[]
  citations: { evidence_id: string; title?: string; source_label?: string; locator?: string }[]
  limitations: string[]
}

export type HistoryDTO = {
  charts: { chart_id: string; calculation_status: string; created_at: string; note: string }[]
  reports: { report_id: string; chart_id: string; title: string; generated_at: string }[]
}

export type ConfigurationDTO = {
  calculation_profile_id: string
  calculation_profile_read_only: boolean
  model_provider: string
  model_configuration_read_only: boolean
  sharing_enabled: boolean
}
