/** Typed HTTP client for the Bazi backend. */
import type {
  ApiErrorDTO,
  BirthRequest,
  ChartOverviewViewDTO,
  ChartResultDTO,
  UserPreferencesDTO,
  TemporalContextViewDTO,
  ReportViewDTO,
  AnalysisJobDTO,
  HistoryDTO,
  ConfigurationDTO,
  FortuneChatRequestDTO,
  FortuneChatResponseDTO,
  CurrentUserDTO,
  ChatThreadSummaryDTO,
  ChatThreadDTO,
} from './schema'

const REQUEST_ID_HEADER = 'X-Request-ID'
const IDEMPOTENCY_HEADER = 'Idempotency-Key'
const DEFAULT_API_BASE = `${import.meta.env.BASE_URL.replace(/\/$/, '')}/api`

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return 'r-' + Math.random().toString(36).slice(2) + Date.now().toString(36)
}

export class ApiError extends Error {
  constructor(public readonly detail: ApiErrorDTO, public readonly httpStatus: number) {
    super(`${detail.error_code}: ${detail.message_key}`)
    this.name = 'ApiError'
  }
}

export interface ClientOptions {
  baseUrl?: string
  fetcher?: typeof fetch
}

export class BaziClient {
  private readonly baseUrl: string
  private readonly fetcher: typeof fetch

  constructor(opts: ClientOptions = {}) {
    this.baseUrl = (opts.baseUrl ?? DEFAULT_API_BASE).replace(/\/$/, '')
    this.fetcher = opts.fetcher ?? globalThis.fetch.bind(globalThis)
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    extraHeaders: Record<string, string> = {},
  ): Promise<T> {
    const url = `${this.baseUrl}${path.startsWith('/') ? path : `/${path}`}`
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      [REQUEST_ID_HEADER]: `req_${uuid()}`,
      ...extraHeaders,
    }
    const init: RequestInit = { method, headers, credentials: 'same-origin' }
    if (body !== undefined) init.body = JSON.stringify(body)

    const response = await this.fetcher(url, init)
    if (!response.ok) {
      let detail: ApiErrorDTO
      try {
        const payload = await response.json() as ApiErrorDTO & { detail?: string }
        detail = payload.error_code ? payload : {
          schema_version: 'api-error-v1',
          request_id: 'req_unknown',
          error_code: response.status === 403 ? 'FORBIDDEN' : 'INVALID_INPUT',
          message_key: payload.detail ?? 'request.failed',
          retryable: false,
        }
      } catch {
        detail = {
          schema_version: 'api-error-v1',
          request_id: 'req_unknown',
          error_code: 'INTERNAL_ERROR',
          message_key: 'error.unparseable',
          retryable: response.status >= 500,
        }
      }
      throw new ApiError(detail, response.status)
    }
    if (response.status === 204) return undefined as unknown as T
    return (await response.json()) as T
  }


  register(username: string, password: string): Promise<CurrentUserDTO> {
    return this.request<CurrentUserDTO>('POST', '/v1/auth/register', { username, password })
  }

  login(username: string, password: string): Promise<CurrentUserDTO> {
    return this.request<CurrentUserDTO>('POST', '/v1/auth/login', { username, password })
  }

  logout(): Promise<void> {
    return this.request<void>('POST', '/v1/auth/logout')
  }

  getCurrentUser(): Promise<CurrentUserDTO> {
    return this.request<CurrentUserDTO>('GET', '/v1/auth/me')
  }

  changePassword(currentPassword: string, newPassword: string): Promise<void> {
    return this.request<void>('POST', '/v1/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
  }

  listUsers(): Promise<CurrentUserDTO[]> {
    return this.request<CurrentUserDTO[]>('GET', '/v1/admin/users')
  }

  createUser(username: string, password: string): Promise<CurrentUserDTO> {
    return this.request<CurrentUserDTO>('POST', '/v1/admin/users', { username, password })
  }

  approveUser(userId: string): Promise<CurrentUserDTO> {
    return this.request<CurrentUserDTO>('POST', `/v1/admin/users/${encodeURIComponent(userId)}/approve`)
  }

  rejectUser(userId: string): Promise<CurrentUserDTO> {
    return this.request<CurrentUserDTO>('POST', `/v1/admin/users/${encodeURIComponent(userId)}/reject`)
  }

  resetUserPassword(userId: string, password?: string): Promise<void> {
    return this.request<void>('POST', `/v1/admin/users/${encodeURIComponent(userId)}/reset-password`, password ? { password } : {})
  }

  getAdminUserData(userId: string): Promise<{ charts: HistoryDTO['charts']; reports: HistoryDTO['reports']; threads: ChatThreadSummaryDTO[] }> {
    return this.request('GET', `/v1/admin/users/${encodeURIComponent(userId)}/data`)
  }

  createChart(req: BirthRequest): Promise<ChartResultDTO> {
    return this.request<ChartResultDTO>('POST', '/v1/charts', req, {
      [IDEMPOTENCY_HEADER]: `idem_${uuid()}`,
    })
  }

  getChart(chartId: string): Promise<ChartResultDTO> {
    return this.request<ChartResultDTO>('GET', `/v1/charts/${encodeURIComponent(chartId)}`)
  }

  listCharts(): Promise<ChartResultDTO[]> {
    return this.request<ChartResultDTO[]>('GET', '/v1/charts')
  }

  deleteChart(chartId: string): Promise<void> {
    return this.request<void>('DELETE', `/v1/charts/${encodeURIComponent(chartId)}`)
  }

  getChartOverviewView(chartId: string): Promise<ChartOverviewViewDTO> {
    return this.request<ChartOverviewViewDTO>(
      'GET',
      `/v1/charts/${encodeURIComponent(chartId)}/overview-view`,
    )
  }

  getTemporalContext(
    chartId: string,
    year: number,
    targetDate?: string,
  ): Promise<TemporalContextViewDTO> {
    const query = targetDate ? `?target_date=${encodeURIComponent(targetDate)}` : ''
    return this.request<TemporalContextViewDTO>(
      'GET',
      `/v1/charts/${encodeURIComponent(chartId)}/temporal/${year}${query}`,
    )
  }

  getReport(reportId: string): Promise<ReportViewDTO> {
    return this.request<ReportViewDTO>('GET', `/v1/reports/${encodeURIComponent(reportId)}`)
  }

  getReportGenerationTrace(reportId: string): Promise<Record<string, unknown>> {
    return this.request('GET', `/v1/reports/${encodeURIComponent(reportId)}/generation-trace`)
  }

  listChatThreads(chartId: string): Promise<ChatThreadSummaryDTO[]> {
    return this.request('GET', `/v1/charts/${encodeURIComponent(chartId)}/chat/threads`)
  }

  getChatThread(threadId: string): Promise<ChatThreadDTO> {
    return this.request('GET', `/v1/chat/threads/${encodeURIComponent(threadId)}`)
  }

  startAnalysis(chartId: string, userFocus: string[]): Promise<AnalysisJobDTO> {
    return this.request<AnalysisJobDTO>(
      'POST',
      `/v1/charts/${encodeURIComponent(chartId)}/analyses`,
      { user_focus: userFocus, school: 'engineering_policy' },
      { [IDEMPOTENCY_HEADER]: `analysis_${uuid()}` },
    )
  }

  chatAboutChart(chartId: string, request: FortuneChatRequestDTO): Promise<FortuneChatResponseDTO> {
    return this.request<FortuneChatResponseDTO>(
      'POST',
      `/v1/charts/${encodeURIComponent(chartId)}/chat`,
      request,
    )
  }

  getJob(jobId: string): Promise<AnalysisJobDTO> {
    return this.request<AnalysisJobDTO>('GET', `/v1/jobs/${encodeURIComponent(jobId)}`)
  }

  cancelJob(jobId: string): Promise<AnalysisJobDTO> {
    return this.request<AnalysisJobDTO>('POST', `/v1/jobs/${encodeURIComponent(jobId)}/cancel`)
  }

  jobEventsUrl(jobId: string, lastEventId?: string): string {
    const path = `${this.baseUrl}/v1/jobs/${encodeURIComponent(jobId)}/events`
    return lastEventId ? `${path}?last_event_id=${encodeURIComponent(lastEventId)}` : path
  }

  getHistory(): Promise<HistoryDTO> {
    return this.request<HistoryDTO>('GET', '/v1/history')
  }

  setChartNote(chartId: string, note: string): Promise<void> {
    return this.request<void>('PATCH', `/v1/charts/${encodeURIComponent(chartId)}/note`, { note })
  }

  getConfiguration(): Promise<ConfigurationDTO> {
    return this.request<ConfigurationDTO>('GET', '/v1/settings/configuration')
  }

  updatePreferences(patch: Partial<UserPreferencesDTO>): Promise<UserPreferencesDTO> {
    const body = { ...patch }
    delete body.schema_version
    return this.request<UserPreferencesDTO>('PATCH', '/v1/settings/profile', body)
  }

  createExport(reportId: string): Promise<{ export_id: string; status: string; print_route: string }> {
    return this.request('POST', `/v1/reports/${encodeURIComponent(reportId)}/exports`, undefined, {
      [IDEMPOTENCY_HEADER]: `export_${uuid()}`,
    })
  }

  createShare(reportId: string, expiresInHours = 24): Promise<{ share_id: string; share_token: string; expires_at: string }> {
    return this.request('POST', `/v1/reports/${encodeURIComponent(reportId)}/shares`, { expires_in_hours: expiresInHours })
  }

  revokeShare(shareId: string): Promise<void> {
    return this.request<void>('DELETE', `/v1/shares/${encodeURIComponent(shareId)}`)
  }

  getUserPreferences(): Promise<UserPreferencesDTO> {
    return this.request<UserPreferencesDTO>('GET', '/v1/settings/profile')
  }
}
