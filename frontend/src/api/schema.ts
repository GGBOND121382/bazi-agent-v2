export type BirthRequest = {
  schema_version: 'birth-request-v1'
  gender: 'male' | 'female' | 'unspecified'
  birth_datetime_local: string
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

export type DeterministicPillarDetail = {
  position: 'year' | 'month' | 'day' | 'hour'
  ganzhi: string
  stem: string
  branch: string
  major_star?: string
  hidden_stems?: { stem: string; ten_god?: string }[]
  secondary_stars?: string[]
  growth_stage?: string
  self_seat?: string
  void?: string
  nayin?: string
  five_elements?: string
  shensha?: string[]
}

export type DeterministicDetails = {
  basic?: Record<string, unknown>
  pillars?: DeterministicPillarDetail[]
  five_elements?: { element: string; explicit: number; hidden: number; total?: number }[]
  shensha?: Record<string, unknown>[]
  [key: string]: unknown
}

export type ChartResultDTO = {
  schema_version: 'chart-result-v1'
  chart_id: string
  calculation_status: 'passed' | 'needs_review' | 'ambiguous' | 'failed'
  calculation_profile_id: string
  normalized_time: { utc?: string; calculation_time?: string; time_basis?: string }
  calendar: { engine_versions?: EngineVersionDTO[]; deterministic_details?: DeterministicDetails }
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
  relationships: {
    type: string
    label: string
    participants: string[]
    rule_id: string
    element?: string | null
    positions?: string[]
    direction?: string | null
    basis?: string[]
    variant?: string
  }[]
  five_elements?: { element: string; explicit: number; hidden: number; total?: number }[]
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

export type ChatScope = 'general' | 'dayun' | 'lifecycle' | 'year' | 'month' | 'day'
export type ChatTurnDTO = { role: 'user' | 'assistant'; content: string }
export type FortuneChatRequestDTO = {
  question: string
  scope: ChatScope
  target_date: string
  history?: ChatTurnDTO[]
  school?: string
  thread_id?: string
  target_dayun_index?: number
}
export type FortuneChatSectionDTO = {
  title: string
  content: string
  opportunities?: string[]
  cautions?: string[]
  timing?: string[]
}
export type FortuneChatResponseDTO = {
  answer: string
  sections: FortuneChatSectionDTO[]
  citations: { evidence_id: string; title?: string; source_id?: string; locator?: string }[]
  scope: ChatScope
  target_date: string
  target_dayun_index?: number | null
  deterministic_context: Record<string, unknown>
  model_id: string
  prompt_version: string
  thread_id: string
  generation_trace: Record<string, unknown>
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

export type TemporalShenshaDTO = {
  name: string
  rule_id: string
  reference?: string
  anchor?: string
  anchor_position?: string | null
  target?: string
  source_title?: string
  source_locator?: string
  rule_version?: string
  variant?: string
}

export type TemporalPillarDetailDTO = {
  ganzhi: string
  stem: string
  branch: string
  stem_ten_god: string
  branch_ten_god: string
  hidden_stems: { stem: string; ten_god: string }[]
  growth_stage: string
  self_seat: string
  xunkong: string
  nayin: string
  shensha: TemporalShenshaDTO[]
  relations: TemporalRelationDTO[]
  relation_summary?: Record<string, unknown>
  temporal_interactions?: TemporalRelationDTO[]
  interaction_summary?: Record<string, unknown>
}

export type TemporalRelationDTO = {
  fact_id?: string
  type: string
  label: string
  participants: string[]
  participant_positions?: { position: string; ganzhi: string; stem?: string; branch?: string }[]
  natal_position?: string
  natal_positions?: string[]
  temporal_positions?: string[]
  element?: string | null
  direction?: string | null
  basis?: string[]
  rule_id: string
  attention?: 'contextual' | 'attention' | 'high_attention'
  requires_interpretation?: boolean
}

export type TemporalDayunDTO = TemporalPillarDetailDTO & {
  index: number
  start_year: number
  end_year: number
  start_age: number
  end_age: number
  fact_id: string
  rule_id: string
}

export type TemporalMonthDTO = TemporalPillarDetailDTO & {
  index: number
  label: string
  jie_name: string
  start_datetime: string
  end_datetime: string
  fact_id: string
  rule_id: string
}

export type TemporalContextViewDTO = {
  schema_version: 'temporal-context-view-v1'
  chart_id: string
  target_year: number
  breadcrumb: { level: string; label: string; ganzhi?: string | null }[]
  qiyun?: {
    direction?: string
    start_years?: number
    start_months?: number
    start_days?: number
    start_hours?: number
    start_datetime?: string
    rule_id?: string
  } | null
  dayuns: TemporalDayunDTO[]
  active_dayun?: TemporalDayunDTO | null
  year: TemporalPillarDetailDTO & {
    year: number
    civil_target_year?: number
    lichun_year?: number
    age: number
    xiaoyun?: string | null
    fact_id: string
    rule_id: string
  }
  months: TemporalMonthDTO[]
  selected_month?: TemporalMonthDTO | null
  selected_day?: TemporalPillarDetailDTO & {
    date: string
    lunar_date: string
    month_ganzhi: string
    fact_id: string
    rule_id: string
  }
  interactions: TemporalRelationDTO[]
  interaction_summary: Record<string, unknown>
  seasonal_strength: Record<string, string>
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

export type CurrentUserDTO = {
  user_id: string
  username: string
  role: 'admin' | 'user'
  enabled: boolean
  must_change_password: boolean
}

export type ChatThreadSummaryDTO = {
  thread_id: string
  chart_id: string
  title: string
  scope: ChatScope
  created_at: string
  updated_at: string
}

export type ChatThreadDTO = {
  thread: ChatThreadSummaryDTO & { owner_id?: string }
  messages: {
    role: 'user' | 'assistant'
    content: string
    payload?: {
      sections?: FortuneChatSectionDTO[]
      citations?: FortuneChatResponseDTO['citations']
      generation_trace?: Record<string, unknown>
    } | null
    created_at: string
  }[]
}
